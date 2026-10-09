#!/usr/bin/env python3
"""
Research-only BTC strategy portfolio + regime/session router.
No exchange imports. No order submission. Does not modify production execution.
"""
import json, bisect, math, statistics
from pathlib import Path
from collections import defaultdict

RAW=Path("data/raw/delta_btc_raw.jsonl")
OUT=Path("data/processed/strategy_portfolio_results.json")
REG=Path("data/processed/strategy_regime_matrix.json")
SES=Path("data/processed/strategy_session_matrix.json")
REPORT=Path("research/STRATEGY_PORTFOLIO_REPORT.md")
TAKER_RT=11.8

def f(x):
    try: return float(x)
    except: return 0.0

# Build chronological L1/trade tape. We retain only fields needed for research.
rows=[]; bp=ap=0.0
with RAW.open() as fh:
    for line in fh:
        try: m=json.loads(line); m=m.get("message",m)
        except Exception: continue
        typ=m.get("type")
        if typ=="ob_l1":
            bp=f(m.get("bp")); ap=f(m.get("ap"))
            continue
        if typ=="trades" and bp>0 and ap>0:
            ts=int(m.get("ts") or m.get("t") or 0)
            px=f(m.get("p")); q=f(m.get("s") or m.get("size") or m.get("q"))
            if ts and px and q:
                rows.append((ts,bp,ap,px,q))
rows.sort()
T=[x[0] for x in rows]; N=len(rows)

# Feature/event construction. Future values are used only after the signal timestamp.
E=[]
for i,(ts,bid,ask,px,q) in enumerate(rows):
    j30=bisect.bisect_left(T,ts-30_000_000,0,i)
    j60=bisect.bisect_left(T,ts-60_000_000,0,i)
    j120=bisect.bisect_left(T,ts-120_000_000,0,i)
    if i-j30<3 or i-j60<5: continue
    mid=(bid+ask)/2
    spread=(ask-bid)/mid*10000
    r30=rows[j30:i]; r60=rows[j60:i]
    vol30=sum(x[4] for x in r30) or 1.0
    signed30=sum((1 if x[3]>=mid else -1)*x[4] for x in r30)
    flow30=signed30/vol30
    vol60=sum(x[4] for x in r60) or 1.0
    signed60=sum((1 if x[3]>=mid else -1)*x[4] for x in r60)
    flow60=signed60/vol60
    mom30=(px-r30[0][3])/r30[0][3]*10000
    mom60=(px-r60[0][3])/r60[0][3]*10000
    intensity30=len(r30)/30.0
    # Recent trade price volatility proxy.
    sample=r60[::max(1,len(r60)//20)]
    meanp=sum(x[3] for x in sample)/len(sample)
    vol_bps=math.sqrt(sum((((x[3]-meanp)/meanp*10000)**2) for x in sample)/len(sample))
    # L1 depth imbalance proxy.
    imb=(sum(x[4] for x in r30 if x[3]<=mid)-sum(x[4] for x in r30 if x[3]>mid))/vol30
    # flow acceleration.
    flow_acc=flow30-flow60
    E.append({
      "i":i,"ts":ts,"bid":bid,"ask":ask,"mid":mid,"spread":spread,
      "flow30":flow30,"flow60":flow60,"flow_acc":flow_acc,
      "mom30":mom30,"mom60":mom60,"intensity":intensity30,"vol":vol_bps,"imb":imb,
      "utc_hour":(ts//3_600_000_000)%24,
    })

# Only score signals where a future endpoint exists.
for e in E:
    e["j60"]=bisect.bisect_left(T,e["ts"]+60_000_000)
    e["j120"]=bisect.bisect_left(T,e["ts"]+120_000_000)
    e["j300"]=bisect.bisect_left(T,e["ts"]+300_000_000)

def session(hour):
    ist=(hour+5)%24  # approximate IST hour; +5h30 represented by bucket shift
    # Half-hour is not available in this compact hourly grouping.
    if 0<=ist<6: return "IST_ASIA_EARLY"
    if 6<=ist<12: return "IST_ASIA_EUROPE"
    if 12<=ist<18: return "IST_EUROPE_US"
    return "IST_US_ASIA"

def regime(e):
    if e["spread"]>5: return "WIDE_SPREAD"
    if e["vol"]>12: return "HIGH_VOL"
    if abs(e["mom60"])<1.0 and abs(e["flow60"])<0.15: return "RANGE"
    if e["mom60"]>=2 and e["flow60"]>=0.20: return "TREND_UP"
    if e["mom60"]<=-2 and e["flow60"]<=-0.20: return "TREND_DOWN"
    if abs(e["flow_acc"])>=0.20: return "FLOW_SHIFT"
    return "MIXED"

# 12 deliberately different research hypotheses.
def signal(name,e):
    s=e["spread"]
    if s>5: return 0
    f30,f60,fa,m30,m60,v,imb=e["flow30"],e["flow60"],e["flow_acc"],e["mom30"],e["mom60"],e["vol"],e["imb"]
    if name=="momentum_continuation":
        return 1 if m30>=2 and f30>=.15 else -1 if m30<=-2 and f30<=-.15 else 0
    if name=="delta_continuation":
        return 1 if f30>=.35 and m30>=0 else -1 if f30<=-.35 and m30<=0 else 0
    if name=="cvd_acceleration":
        return 1 if fa>=.20 and f30>=.10 else -1 if fa<=-.20 and f30<=-.10 else 0
    if name=="l2_imbalance_proxy":
        return 1 if imb<=-.25 and m30>0 else -1 if imb>=.25 and m30<0 else 0
    if name=="liquidity_sweep_reversal":
        return -1 if m30>=4 and f30<.10 else 1 if m30<=-4 and f30>-.10 else 0
    if name=="absorption_reversal":
        return -1 if m30>=2.5 and f30<=-.20 else 1 if m30<=-2.5 and f30>=.20 else 0
    if name=="breakout_volume":
        return 1 if m30>=3 and f30>=.25 and v>=4 else -1 if m30<=-3 and f30<=-.25 and v>=4 else 0
    if name=="vwap_mean_reversion":
        return -1 if m60>=4 and abs(f30)<.20 else 1 if m60<=-4 and abs(f30)<.20 else 0
    if name=="volatility_expansion":
        return 1 if m30>=2 and v>=6 and f30>=.20 else -1 if m30<=-2 and v>=6 and f30<=-.20 else 0
    if name=="momentum_exhaustion":
        return -1 if m60>=5 and m30<m60*.45 else 1 if m60<=-5 and m30>m60*.45 else 0
    if name=="fisher_microstructure_proxy":
        # Research proxy only: medium-term direction + strong flow.
        return 1 if m60>=2 and f60>=.25 and f30>=.20 else -1 if m60<=-2 and f60<=-.25 and f30<=-.20 else 0
    if name=="multifactor_ensemble":
        score=(1 if m30>0 else -1 if m30<0 else 0)+(1 if f30>.20 else -1 if f30<-.20 else 0)+(1 if fa>.10 else -1 if fa<-.10 else 0)
        return 1 if score>=3 else -1 if score<=-3 else 0
    return 0

strategies=[
"momentum_continuation","delta_continuation","cvd_acceleration","l2_imbalance_proxy",
"liquidity_sweep_reversal","absorption_reversal","breakout_volume","vwap_mean_reversion",
"volatility_expansion","momentum_exhaustion","fisher_microstructure_proxy","multifactor_ensemble"]

# Evaluate executable taker paths for 60/120/300s. Stop/target are 1:2.
# This is intentionally conservative: entry at ask for long / bid for short; exit at bid/ask.
def eval_trade(e,side,horizon,stop_bps,target_bps):
    j=e["j"+str(horizon)]
    if j>=N: return None
    entry=e["ask"] if side==1 else e["bid"]
    stop=entry*(1-stop_bps/10000) if side==1 else entry*(1+stop_bps/10000)
    target=entry*(1+target_bps/10000) if side==1 else entry*(1-target_bps/10000)
    end=j; reason="TIME"
    exit_px=(rows[end][1] if side==1 else rows[end][2])
    for k in range(e["i"]+1,end+1):
        bid,ask=rows[k][1],rows[k][2]
        if side==1:
            if bid<=stop: exit_px=bid; reason="STOP"; break
            if bid>=target: exit_px=bid; reason="TARGET"; break
        else:
            if ask>=stop: exit_px=ask; reason="STOP"; break
            if ask<=target: exit_px=ask; reason="TARGET"; break
    gross=((exit_px-entry)/entry*10000)*(1 if side==1 else -1)
    return gross-TAKER_RT, reason

def summarize(trades):
    if not trades: return {"n":0}
    xs=[x[0] for x in trades]; wins=[x for x in xs if x>0]; losses=[-x for x in xs if x<0]
    eq=peak=dd=0.0
    for x in xs:
        eq+=x; peak=max(peak,eq); dd=max(dd,peak-eq)
    return {
      "n":len(xs),"win_rate":len(wins)/len(xs),"avg_net_bps":sum(xs)/len(xs),
      "median_net_bps":statistics.median(xs),"profit_factor":sum(wins)/sum(losses) if losses else None,
      "max_drawdown_bps":dd,"avg_winner_bps":sum(wins)/len(wins) if wins else 0,
      "avg_loser_bps":-sum(losses)/len(losses) if losses else 0,
      "targets":sum(1 for _,r in trades if r=="TARGET"),
      "stops":sum(1 for _,r in trades if r=="STOP"),
      "time_exits":sum(1 for _,r in trades if r=="TIME"),
    }

# Chronological 60/20/20 split; selection is made on train only.
n=len(E); a=int(n*.60); b=int(n*.80)
all_results=[]; selected={}
for name in strategies:
    for horizon in (60,120,300):
        for stop,target in ((5,10),(8,16),(10,20)):
            splits=[]
            for lo,hi,label in ((0,a,"train"),(a,b,"validation"),(b,n,"test")):
                trades=[]; last_ts=-10**30
                for e in E[lo:hi]:
                    side=signal(name,e)
                    if side==0 or e["ts"]-last_ts<60_000_000: continue
                    r=eval_trade(e,side,horizon,stop,target)
                    if r:
                        trades.append(r); last_ts=e["ts"]
                splits.append((label,summarize(trades)))
            train=splits[0][1]
            if train["n"]>=20:
                all_results.append({"strategy":name,"horizon_s":horizon,"stop_bps":stop,"target_bps":target,"splits":dict(splits)})

# Rank only by train evidence, then inspect validation/test separately.
all_results.sort(key=lambda x: (x["splits"]["train"].get("avg_net_bps",-999),x["splits"]["train"].get("profit_factor") or 0), reverse=True)
top=all_results[:30]
for r in top:
    key=(r["strategy"],r["horizon_s"],r["stop_bps"],r["target_bps"])
    selected[key]=r

# Regime/session matrices for top candidates, using full sample only as diagnostic,
# never for selecting the winner.
regmat=defaultdict(lambda: {"n":0,"net_bps":0.0,"wins":0})
sesmat=defaultdict(lambda: {"n":0,"net_bps":0.0,"wins":0})
for r in top[:12]:
    name=r["strategy"]; horizon=r["horizon_s"]; stop=r["stop_bps"]; target=r["target_bps"]
    for e in E:
        side=signal(name,e)
        if side==0 or e["ts"]<E[0]["ts"]: continue
        rr=eval_trade(e,side,horizon,stop,target)
        if not rr: continue
        net,reason=rr
        rk=(name,regime(e),horizon); sk=(name,session(e["utc_hour"]),horizon)
        regmat[rk]["n"]+=1; regmat[rk]["net_bps"]+=net; regmat[rk]["wins"]+=net>0
        sesmat[sk]["n"]+=1; sesmat[sk]["net_bps"]+=net; sesmat[sk]["wins"]+=net>0

def finish(mat):
    out={}
    for k,v in mat.items():
        n=v["n"]; out["|".join(map(str,k))]={"n":n,"avg_net_bps":v["net_bps"]/n if n else 0,"win_rate":v["wins"]/n if n else 0}
    return out

portfolio={
 "status":"RESEARCH_ONLY",
 "raw_trade_events":N,"feature_samples":len(E),"taker_round_trip_cost_bps":TAKER_RT,
 "split":{"train":a,"validation":b-a,"test":n-b,"chronological":True},
 "strategy_count":len(strategies),"strategies":strategies,
 "ranking_note":"Train-selected candidates are ranked by net expectancy; validation/test are held out and not used for selection.",
 "top_candidates":top,
 "winner_rule":"Do not promote on train rank. Require >=100 labeled trades, positive validation/test/walk-forward net, PF>1.2, and realistic execution evidence."
}
OUT.write_text(json.dumps(portfolio,indent=2))
REG.write_text(json.dumps({"status":"RESEARCH_ONLY","matrix":finish(regmat)},indent=2))
SES.write_text(json.dumps({"status":"RESEARCH_ONLY","matrix":finish(sesmat)},indent=2))

winner=top[0] if top else None
lines=["# Strategy Portfolio v1","",f"Status: RESEARCH_ONLY","",f"Raw trade events: {N}",f"Feature samples: {len(E)}",f"Strategies tested: {len(strategies)}",f"Taker round-trip cost: {TAKER_RT} bps","", "No production execution code was modified. No live order was submitted.","","## Top train-ranked candidates"]
for r in top[:12]:
    tr=r["splits"]["train"]; va=r["splits"]["validation"]; te=r["splits"]["test"]
    lines.append(f"- {r['strategy']} | {r['horizon_s']}s | {r['stop_bps']}/{r['target_bps']} bps | train n={tr.get('n',0)} avg={tr.get('avg_net_bps',0):.3f} PF={tr.get('profit_factor')} | validation n={va.get('n',0)} avg={va.get('avg_net_bps',0):.3f} PF={va.get('profit_factor')} | test n={te.get('n',0)} avg={te.get('avg_net_bps',0):.3f} PF={te.get('profit_factor')}")
lines += ["","## Interpretation","The router is a research ranking layer, not a live trading authorization. Session/regime matrices are diagnostic and use the full historical sample; they must not be treated as out-of-sample evidence.","","A candidate is not considered profitable unless it survives chronological validation/test, realistic execution, sample-size requirements, and walk-forward validation. Maker fills are not assumed.",""]
REPORT.write_text("\n".join(lines))
print(json.dumps({"status":"RESEARCH_ONLY","events":N,"samples":len(E),"strategies":len(strategies),"top":[{"strategy":r["strategy"],"horizon":r["horizon_s"],"train":r["splits"]["train"],"validation":r["splits"]["validation"],"test":r["splits"]["test"]} for r in top[:12]]},indent=2))
