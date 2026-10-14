"""Regime-conditioned BTCUSD perpetual research. Research-only; no exchange adapter/orders."""
from __future__ import annotations
import json, math, sqlite3, hashlib, time
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
CANDLES=ROOT/"data/processed/live_multi_timeframe_candles_v1.json"
TAPE=ROOT/"data/processed/live_microstructure_features_v1.jsonl"
STATE=ROOT/"data/live_microstructure_state.json"
OUT=ROOT/"data/processed/ofi_regime_experiment_v2_summary.json"
DB=ROOT/"data/processed/ofi_regime_paper_ledger_v2.sqlite3"
HORIZON=15
MIN_EVENTS=300
SEED=20261010
# Delta Exchange India official BTCUSD contract assumptions; verify account-specific charges before use.
TAKER_RATE=0.0005
MAKER_RATE=0.0002
GST_ON_FEES=0.18
MAKER_FEE_BPS=MAKER_RATE*10000*(1+GST_ON_FEES)
TAKER_FEE_BPS=TAKER_RATE*10000*(1+GST_ON_FEES)
SHOCK=0.05
MAX_EXPOSURE_BTC=0.001

def load_candles():
    raw=json.loads(CANDLES.read_text())
    arr=raw.get("candles",{}).get("1m",[])
    out=[]
    for r in arr:
        try:
            ts=float(r["timestamp"]); close=float(r["close"])
            high=float(r.get("high",close)); low=float(r.get("low",close)); vol=float(r.get("volume",r.get("vol",0)))
            if all(map(math.isfinite,[ts,close,high,low,vol])) and close>0 and high>0 and low>0:
                out.append((ts,close,high,low,max(0.,vol)))
        except (KeyError,TypeError,ValueError): pass
    ded={}
    for r in out: ded[r[0]]=r
    return [ded[k] for k in sorted(ded)]

def load_tape():
    if not TAPE.exists(): return []
    rows=[]
    with TAPE.open() as f:
        for line in f:
            try:
                r=json.loads(line); ts=float(r["ts"]); mid=float(r["mid"])
                if mid>0 and math.isfinite(ts) and math.isfinite(mid):
                    rows.append({"ts":ts,"mid":mid,"spread_bps":float(r.get("spread_bps",0)),
                      "trade_samples":int(r.get("trade_samples",0)),"state_age_s":float(r.get("state_age_s",r.get("fresh",999))),
                      "session_id":str(r.get("session_id","")),"delta30":float(r.get("delta30",0)),
                      "imb5":float(r.get("imb5",0))})
            except (ValueError,TypeError,KeyError): pass
    return sorted(rows,key=lambda x:x["ts"])

def add_tape_features(candles,tape):
    # Timestamp conventions vary; nearest observation only within 30s. Never fabricate OFI.
    features=[]
    for ts,close,high,low,vol in candles:
        t=ts/1000 if ts>1e11 else ts
        near=min(tape,key=lambda r:abs(r["ts"]-t)) if tape else None
        if near and abs(near["ts"]-t)<=30 and near["state_age_s"]<=2:
            intensity=max(0,near["trade_samples"])
            spread=max(0,near["spread_bps"])
            delta=near["delta30"]; imb=near["imb5"]
            micro_ok=True
        else:
            intensity=spread=delta=imb=0.0; micro_ok=False
        features.append((t,close,high,low,vol,spread,intensity,delta,imb,micro_ok))
    return features

def rolling_features(rows):
    close=np.array([r[1] for r in rows],float)
    n=len(rows); ret=np.full(n,np.nan); ret[1:]=np.diff(np.log(close))
    rv=np.full(n,np.nan); intensity=np.zeros(n); spread=np.full(n,np.nan)
    for i,r in enumerate(rows):
        if i>=5 and np.isfinite(ret[i-4:i+1]).all(): rv[i]=float(np.sqrt(np.sum(ret[i-4:i+1]**2)))
        spread[i]=r[5]; intensity[i]=r[6]
    X=np.column_stack([np.log(np.maximum(rv,1e-8)),np.log1p(intensity),np.log1p(np.maximum(spread,0))])
    return ret,rv,X

def logsumexp(a,axis=None):
    m=np.max(a,axis=axis,keepdims=True)
    z=m+np.log(np.sum(np.exp(a-m),axis=axis,keepdims=True)+1e-300)
    return np.squeeze(z,axis=axis) if axis is not None else float(z.ravel()[0])

def fit_hmm(X,K=3,iterations=8):
    """Small diagonal-Gaussian HMM via Baum-Welch; standardization must be train-only."""
    X=np.asarray(X,float); n,d=X.shape
    mu0=X.mean(axis=0); sd0=X.std(axis=0); sd0[sd0<1e-6]=1
    Z=np.clip((X-mu0)/sd0,-8,8)
    # Deterministic quantile initialization, no random seed dependence.
    order=np.argsort(Z[:,0]); means=np.array([Z[order[min(n-1,int((k+.5)*n/K))]] for k in range(K)])
    var=np.tile(np.maximum(Z.var(axis=0),.2),(K,1))
    trans=np.full((K,K),.08/(K-1)); np.fill_diagonal(trans,.92)
    pi=np.full(K,1/K)
    for _ in range(iterations):
        loge=np.empty((n,K))
        for k in range(K):
            loge[:,k]=-.5*np.sum(np.log(2*np.pi*var[k])+(Z-means[k])**2/var[k],axis=1)
        la=np.log(np.maximum(pi,1e-12)); lt=np.log(np.maximum(trans,1e-12))
        alpha=np.empty((n,K)); alpha[0]=la+loge[0]
        for t in range(1,n): alpha[t]=loge[t]+np.array([logsumexp(alpha[t-1]+lt[:,k]) for k in range(K)])
        beta=np.zeros((n,K))
        for t in range(n-2,-1,-1):
            for k in range(K): beta[t,k]=logsumexp(lt[k]+loge[t+1]+beta[t+1])
        gamma=np.exp(alpha+beta-np.array([logsumexp(alpha[t]+beta[t]) for t in range(n)])[:,None])
        xi_sum=np.zeros((K,K))
        for t in range(n-1):
            z=alpha[t][:,None]+lt+loge[t+1][None,:]+beta[t+1][None,:]
            xi_sum+=np.exp(z-logsumexp(z))
        pi=gamma[0]/gamma[0].sum()
        trans=xi_sum/np.maximum(xi_sum.sum(axis=1,keepdims=True),1e-12)
        for k in range(K):
            w=gamma[:,k]; den=max(w.sum(),1e-8)
            means[k]=(w[:,None]*Z).sum(axis=0)/den
            var[k]=(w[:,None]*(Z-means[k])**2).sum(axis=0)/den
            var[k]=np.maximum(var[k],.05)
    return {"mu":mu0,"sd":sd0,"means":means,"var":var,"trans":trans,"pi":pi}

def hmm_filter(model,X):
    Z=np.clip((np.asarray(X)-model["mu"])/model["sd"],-8,8)
    K=len(model["pi"]); out=np.empty((len(Z),K)); prev=model["pi"]
    for i,x in enumerate(Z):
        le=np.array([-.5*np.sum(np.log(2*np.pi*model["var"][k])+(x-model["means"][k])**2/model["var"][k]) for k in range(K)])
        q=(prev@model["trans"])*np.exp(le-np.max(le)); prev=q/max(q.sum(),1e-300); out[i]=prev
    return out

def fit_logistic(X,y,steps=1200,lr=.04,l2=.04):
    mu=X.mean(0); sd=X.std(0); sd[sd<1e-8]=1
    Z=(X-mu)/sd; rate=float(np.clip(y.mean(),.01,.99)); w=np.zeros(Z.shape[1]); b=math.log(rate/(1-rate))
    for _ in range(steps):
        p=1/(1+np.exp(-np.clip(Z@w+b,-30,30)))
        w-=lr*((Z.T@(p-y))/len(y)+l2*w); b-=lr*float(np.mean(p-y))
    return mu,sd,w,b

def pmetrics(y,p):
    p=np.clip(np.asarray(p),1e-6,1-1e-6); y=np.asarray(y,float)
    return {"n":len(y),"brier":float(np.mean((p-y)**2)),"log_loss":float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p)))}

def init_ledger():
    db=sqlite3.connect(DB)
    db.execute("PRAGMA journal_mode=WAL"); db.execute("PRAGMA synchronous=FULL")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS experiment_parent(
      parent_id TEXT PRIMARY KEY, created_ts REAL NOT NULL, state TEXT NOT NULL,
      hypothesis TEXT NOT NULL, risk_state TEXT NOT NULL, metadata_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS experiment_child(
      child_id TEXT PRIMARY KEY, parent_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
      side TEXT NOT NULL, limit_price REAL, qty_btc REAL NOT NULL, state TEXT NOT NULL,
      fill_probability REAL, ev_bps REAL, risk_state TEXT NOT NULL, created_ts REAL NOT NULL,
      FOREIGN KEY(parent_id) REFERENCES experiment_parent(parent_id));
    """)
    db.commit(); return db

def risk_fixture(mark,qty):
    # The account equity/anchors are absent from the read-only local data. Fail closed.
    # We can check exposure and shock arithmetic, but cannot approve simulated execution.
    post=abs(qty)
    stress_price=mark*(1-SHOCK if qty>0 else 1+SHOCK)
    return {"verdict":"BLOCKED_MISSING_AUTHORITATIVE_ACCOUNT_STATE",
      "current_position_btc":None,"post_trade_exposure_btc":post,
      "max_exposure_btc":MAX_EXPOSURE_BTC,"exposure_within_cap":post<=MAX_EXPOSURE_BTC,
      "adverse_shock_fraction":SHOCK,"stressed_mark_price":stress_price,
      "account_equity":None,"maintenance_margin":None,
      "simulated_execution_allowed":False}

def run():
    candles=load_candles(); tape=load_tape(); rows=add_tape_features(candles,tape)
    ret,rv,Xreg=rolling_features(rows)
    # 15-minute future close-to-close direction; features available at origin only.
    close=np.array([r[1] for r in rows],float); n=len(rows)
    yret=np.full(n,np.nan); yret[:-HORIZON]=close[HORIZON:]/close[:-HORIZON]-1
    eligible=np.where(np.isfinite(ret)&np.isfinite(yret)&np.isfinite(Xreg).all(axis=1))[0]
    # OFI requires consecutive book-level price/volume snapshots. Existing tape omitted bid/ask ladders,
    # so do not synthesize OFI from static imbalance. This run audits the data gap and trains only available features.
    has_ofi=False
    base_features=np.column_stack([ret,Xreg])
    folds=[]; all_brier=[]; all_logloss=[]; fold_predictions=[]
    # Three chronological folds, expanding train; purge 15 bars so labels mature.
    starts=[int(n*.4),int(n*.6),int(n*.8)]
    ends=[int(n*.6),int(n*.8),n]
    for k,(a,b) in enumerate(zip(starts,ends),1):
        test=np.arange(a,b); train=eligible[eligible+HORIZON<a]
        test=test[np.isfinite(yret[test]) & np.isfinite(base_features[test]).all(axis=1)]
        train=train[np.isfinite(base_features[train]).all(axis=1)]
        if len(train)<100 or len(test)<30:
            folds.append({"fold":k,"train_n":len(train),"test_n":len(test),"status":"NEED_MORE_DATA"}); continue
        # HMM fit strictly on train features; filter full chronological series without future smoothing.
        hmm=fit_hmm(Xreg[train],K=3)
        # For strict out-of-sample, infer state on chronological train then test sequentially.
        Xall=np.vstack([Xreg[train],Xreg[test]])
        post=hmm_filter(hmm,Xall)
        # one-hot posterior probabilities represent regime uncertainty, not hard labels
        regime=post[:,1:]
        modelX=np.column_stack([base_features[np.r_[train,test]],regime])
        trX=modelX[:len(train)]; teX=modelX[len(train):]
        yy=(yret[train]>0).astype(float); yt=(yret[test]>0).astype(float)
        mu,sd,w,bias=fit_logistic(trX,yy)
        p=1/(1+np.exp(-np.clip(((teX-mu)/sd)@w+bias,-30,30)))
        pm=pmetrics(yt,p); baseline=pmetrics(yt,np.full(len(yt),yy.mean()))
        # Passive maker EV: conditional fill probability not identifiable from snapshot-only data.
        # Store null EV and no-fill child state rather than inventing fill odds.
        folds.append({"fold":k,"train_n":len(train),"test_n":len(test),
          "test_start_ts":float(rows[test[0]][0]),"test_end_ts":float(rows[test[-1]][0]),
          "base_rate":float(yy.mean()),"baseline":baseline,"regime_conditioned_model":pm,
          "brier_improvement_vs_base_rate":baseline["brier"]-pm["brier"],
          "passive_maker_ev":"NOT_ESTIMABLE_MISSING_QUEUE/FILL_LABELS",
          "ofi_model":"NOT_RUN_MISSING_HISTORICAL_BOOK_LEVEL_DELTAS"})
        all_brier.append(pm["brier"]); all_logloss.append(pm["log_loss"])
        fold_predictions.append({"y":yt.tolist(),"p":p.tolist()})
    mark=rows[-1][1] if rows else None
    risk=risk_fixture(mark or 0.0,0.001)
    now=time.time(); pid="ofi-regime-v2-"+hashlib.sha256(f"{now}:{len(rows)}".encode()).hexdigest()[:16]
    db=init_ledger()
    db.execute("INSERT OR REPLACE INTO experiment_parent VALUES(?,?,?,?,?,?)",
      (pid,now,"RESEARCH_ONLY","Regime-conditioned 15m direction with deep OFI","BLOCKED_MISSING_AUTHORITATIVE_ACCOUNT_STATE",
       json.dumps({"real_orders":False,"ofi_available":has_ofi,"risk":risk})))
    db.execute("INSERT OR REPLACE INTO experiment_child VALUES(?,?,?,?,?,?,?,?,?,?,?)",
      (pid+"-child-001",pid,1,"buy",mark,0.001,"NOT_SENT_NO_FILL_MODEL",None,None,
       "BLOCKED_MISSING_AUTHORITATIVE_ACCOUNT_STATE",now))
    db.commit(); db.close()
    data_ok=len(rows)>=MIN_EVENTS and len(tape)>=MIN_EVENTS and len(folds)==3 and all(f.get("status") is None for f in folds)
    # Decision remains NEED_MORE_DATA until OFI, HMM full data coverage and fill model are supported.
    decision="NEED_MORE_DATA"
    summary={"experiment":"OFI_REGIME_EXPERIMENT_V2","decision":decision,
      "hypothesis":"Regime-conditioned 15-minute direction and deep order-flow imbalance improve calibrated forecasts and passive-maker expected value.",
      "status":"RESEARCH_ONLY","candle_rows":len(candles),"aligned_rows":len(rows),"microstructure_snapshot_rows":len(tape),
      "eligible_15m_labels":int(len(eligible)),"folds":folds,
      "data_gaps":{"historical_l2_ladders_in_tape":False,"multi_level_ofi_computable":False,
       "passive_fill_labels_available":False,"queue_depletion_labels_available":False,
       "authoritative_account_equity_and_margin_available":False,
       "note":"Current live state has bids_l5/asks_l5, but the historical feature tape omitted level prices/volumes. Do not infer historical OFI or passive fill odds from imb5."},
      "fee_assumptions":{"contract":"Delta Exchange India BTCUSD perpetual","taker_rate":TAKER_RATE,"maker_rate":MAKER_RATE,
       "gst_on_fees":GST_ON_FEES,"maker_fee_bps_per_side_including_gst":MAKER_FEE_BPS,
       "taker_fee_bps_per_side_including_gst":TAKER_FEE_BPS,
       "source":"official Delta Exchange India fee/help pages; account-specific discounts/fees must be verified",
       "maker_rebate_assumed":False,"reason":"Published schedule describes 0.02% maker fee, not a 0.02% rebate."},
      "risk_oracle":{"max_net_exposure_btc":MAX_EXPOSURE_BTC,"adverse_shock_fraction":SHOCK,
       "result":risk,"execution_allowed":False},
      "sqlite":{"path":str(DB),"parent_id":pid,"child_id":pid+"-child-001",
       "parent_state":"RESEARCH_ONLY","child_state":"NOT_SENT_NO_FILL_MODEL"},
      "summary_metrics":{"folds_scored":len(all_brier),"mean_brier":float(np.mean(all_brier)) if all_brier else None,
       "mean_log_loss":float(np.mean(all_logloss)) if all_logloss else None},
      "limitations":["No live or simulated exchange execution occurred.",
       "15-minute label is close-to-close return direction, not a validated barrier target.",
       "Snapshot rows are not full exchange-native L2/trade events.",
       "HMM regime states are latent statistical clusters; labels like absorption/expansion need separate validation.",
       "Fee-aware EV is not estimable without passive-fill and adverse-queue outcomes.",
       "The current run does not approve a strategy or authorize trading."]}
    OUT.write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))

if __name__=="__main__": run()
