"""Research-only absorption + L2 + frozen MonthlyFisher regime filter."""
import json,csv,sys
from pathlib import Path
from collections import deque
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from strategy.fisher import MonthlyFisher,Candle
ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/"data/raw/delta_btc_raw.jsonl"; MONTH=Path.home()/"data/BTC-USD_monthly.csv"
FEE=5.9

def f(x,d=0.0):
    try:return float(x)
    except:return d

def fisher_regime():
    eng=MonthlyFisher(); val=None
    with MONTH.open() as fh:
        for row in csv.reader(fh):
            if not row or not row[0][:4].isdigit(): continue
            # Use all historical completed months; exclude Sep-2026 partial/current research month.
            if row[0][:7] >= "2026-09": continue
            c=Candle(int(__import__("datetime").datetime.strptime(row[0],"%Y-%m-%d").timestamp()),f(row[1]),f(row[2]),f(row[3]),f(row[4]))
            v=eng.update(c)
            if v: val=v
    return val

def dd(vals):
    peak=cur=out=0.0
    for x in vals:
        cur+=x; peak=max(peak,cur); out=max(out,peak-cur)
    return out

def run():
    fv=fisher_regime(); regime="LONG" if fv and fv.fisher>fv.trigger else "SHORT" if fv else "NEUTRAL"
    l1={}; bids={}; asks={}; q=deque(); prices=deque(); samples=[]; n=0
    with RAW.open() as fh:
        for line in fh:
            try:m=json.loads(line); m=m.get("message",m)
            except:continue
            n+=1; typ=m.get("type"); ts=int(f(m.get("ts") or m.get("t")))
            if not ts:continue
            if typ=="ob_l1": l1=m; continue
            if typ=="ob_l2":
                bids={f(p):f(s) for p,s in m.get("b",[]) if f(s)>0}; asks={f(p):f(s) for p,s in m.get("a",[]) if f(s)>0}; continue
            if typ!="trades":continue
            p=f(m.get("p")); sz=abs(f(m.get("s"))); bid=f(l1.get("bp")); ask=f(l1.get("ap"))
            if p<=0 or sz<=0 or bid<=0 or ask<=0:continue
            side="sell" if p<=bid else "buy" if p>=ask else ("sell" if m.get("r")=="m" else "buy")
            q.append((ts,side,sz)); prices.append((ts,p))
            while q and q[0][0]<ts-5_000_000:q.popleft()
            while prices and prices[0][0]<ts-10_000_000:prices.popleft()
            buy=sum(x[2] for x in q if x[1]=="buy"); sell=sum(x[2] for x in q if x[1]=="sell")
            delta=(buy-sell)/(buy+sell) if buy+sell else 0
            old=prices[0][1] if prices else p; ret=(p/old-1)*10000
            bd=sum(v for _,v in sorted(bids.items(),reverse=True)[:5]); ad=sum(v for _,v in sorted(asks.items())[:5])
            imb=(bd-ad)/(bd+ad) if bd+ad else 0
            samples.append((ts,p,bid,ask,delta,ret,imb))
    results=[]
    for min_delta,min_imb,stop,target in ((.25,.20,8,16),(.30,.25,10,20),(.35,.30,12,24),(.40,.35,12,24)):
        trades=[]; pos=None; cooldown=0
        for ts,p,bid,ask,d,ret,imb in samples:
            if pos:
                if pos["side"]=="LONG": hs=bid<=pos["stop"]; ht=bid>=pos["target"]; ex=pos["stop"] if hs else pos["target"] if ht else None
                else: hs=ask>=pos["stop"]; ht=ask<=pos["target"]; ex=pos["stop"] if hs else pos["target"] if ht else None
                if ex is not None:
                    gross=((ex/pos["entry"]-1)*10000) if pos["side"]=="LONG" else ((pos["entry"]/ex-1)*10000)
                    net=gross-2*FEE; trades.append(net); pos=None; cooldown=ts+5_000_000
                continue
            if ts<cooldown:continue
            # Absorption + L2 confirmation + Fisher regime.
            if d<=-min_delta and ret>=-4 and imb>=min_imb and regime=="LONG" and ret>=1:
                e=ask; pos={"side":"LONG","entry":e,"stop":e*(1-stop/10000),"target":e*(1+target/10000)}
            elif d>=min_delta and ret<=4 and imb<=-min_imb and regime=="SHORT" and ret<=-1:
                e=bid; pos={"side":"SHORT","entry":e,"stop":e*(1+stop/10000),"target":e*(1-target/10000)}
        if trades:
            w=[x for x in trades if x>0]; l=[x for x in trades if x<=0]; gl=-sum(l)
            results.append({"min_delta":min_delta,"min_imbalance":min_imb,"stop_bps":stop,"target_bps":target,"n":len(trades),"win_rate":len(w)/len(trades),"avg_net_bps":sum(trades)/len(trades),"total_net_bps":sum(trades),"profit_factor":sum(w)/gl if gl else None,"max_drawdown_bps":dd(trades)})
    out={"events_read":n,"samples":len(samples),"fisher":None if not fv else {"fisher":fv.fisher,"trigger":fv.trigger,"regime":regime},"fee_bps_each_side":FEE,"results":results,"status":"research_only"}
    (ROOT/"data/processed/absorption_l2_fisher_v1.json").write_text(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
if __name__=="__main__":run()
