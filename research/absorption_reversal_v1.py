"""Research-only BTCUSD absorption/reversal detector. Never submits orders."""
import json
from pathlib import Path
from collections import deque
ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/"data/raw/delta_btc_raw.jsonl"; OUT=ROOT/"data/processed/absorption_reversal_v1.json"
FEE=5.9

def f(x,d=0.0):
    try:return float(x)
    except:return d

def dd(vals):
    peak=cur=out=0.0
    for x in vals:
        cur+=x; peak=max(peak,cur); out=max(out,peak-cur)
    return out

def run():
    l1={}; q=deque(); prices=deque(); samples=[]; n=0
    with RAW.open() as fh:
        for line in fh:
            try:m=json.loads(line); m=m.get("message",m)
            except:continue
            n+=1; typ=m.get("type"); ts=int(f(m.get("ts") or m.get("t")))
            if not ts:continue
            if typ=="ob_l1": l1=m; continue
            if typ!="trades":continue
            p=f(m.get("p")); sz=abs(f(m.get("s")))
            if p<=0 or sz<=0:continue
            bid=f(l1.get("bp")); ask=f(l1.get("ap"))
            if bid<=0 or ask<=0:continue
            side="sell" if p<=bid else "buy" if p>=ask else ("sell" if m.get("r")=="m" else "buy")
            q.append((ts,side,sz)); prices.append((ts,p))
            while q and q[0][0]<ts-5_000_000:q.popleft()
            while prices and prices[0][0]<ts-10_000_000:prices.popleft()
            buy=sum(x[2] for x in q if x[1]=="buy"); sell=sum(x[2] for x in q if x[1]=="sell")
            delta=(buy-sell)/(buy+sell) if buy+sell else 0
            old=prices[0][1] if prices else p
            ret=(p/old-1)*10000
            samples.append((ts,p,bid,ask,delta,ret,buy+sell))

    results=[]
    # Absorption: strong selling, but price decline is unusually small; enter LONG only
    # after a short confirmation bounce. Symmetric logic for SHORT.
    for stop,target in ((4,8),(6,12),(8,16),(10,20),(12,24)):
        trades=[]; pos=None; cooldown=0; candidate=None
        for s in samples:
            ts,p,bid,ask,d,ret,vol=s
            if pos:
                if pos["side"]=="LONG":
                    hs=bid<=pos["stop"]; ht=bid>=pos["target"]
                    ex=pos["stop"] if hs else pos["target"] if ht else None
                else:
                    hs=ask>=pos["stop"]; ht=ask<=pos["target"]
                    ex=pos["stop"] if hs else pos["target"] if ht else None
                if ex is not None:
                    gross=((ex/pos["entry"]-1)*10000) if pos["side"]=="LONG" else ((pos["entry"]/ex-1)*10000)
                    net=gross-2*FEE
                    trades.append({"side":pos["side"],"entry":pos["entry"],"exit":ex,"net_bps":net,"outcome":"WIN" if net>0 else "LOSS"})
                    pos=None; cooldown=ts+5_000_000
                continue
            if ts<cooldown:continue
            # Candidate absorption: sell delta <= -25%, but 10s price decline <= 4 bps.
            if d<=-0.25 and ret>=-4.0: candidate=("LONG",ts,p,ask)
            elif d>=0.25 and ret<=4.0: candidate=("SHORT",ts,p,bid)
            else: candidate=None
            if candidate:
                side,cts,cp,quote=candidate
                # Confirmation: require current micro price to move 1 bp back in reversal direction.
                if side=="LONG" and ret>=1.0:
                    entry=ask; pos={"side":side,"entry":entry,"stop":entry*(1-stop/10000),"target":entry*(1+target/10000)}
                    candidate=None
                elif side=="SHORT" and ret<=-1.0:
                    entry=bid; pos={"side":side,"entry":entry,"stop":entry*(1+stop/10000),"target":entry*(1-target/10000)}
                    candidate=None
        if trades:
            wins=[x for x in trades if x["net_bps"]>0]; losses=[x for x in trades if x["net_bps"]<=0]
            gp=sum(x["net_bps"] for x in wins); gl=-sum(x["net_bps"] for x in losses)
            results.append({"stop_bps":stop,"target_bps":target,"n":len(trades),"win_rate":len(wins)/len(trades),
                            "avg_net_bps":sum(x["net_bps"] for x in trades)/len(trades),
                            "total_net_bps":sum(x["net_bps"] for x in trades),
                            "profit_factor":gp/gl if gl else None,
                            "max_drawdown_bps":dd([x["net_bps"] for x in trades])})
    out={"events_read":n,"feature_samples":len(samples),"fee_bps_each_side":FEE,"results":results,
         "method":"Sell/buy-flow absorption proxy + constrained price response + reversal confirmation; executable bid/ask exits.",
         "status":"research_only_no_order_submission"}
    OUT.write_text(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
if __name__=="__main__":run()
