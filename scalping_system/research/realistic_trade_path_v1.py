"""Research-only realistic trade-path backtester. Never submits orders."""
import json
from pathlib import Path
from collections import deque
ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/"data/raw/delta_btc_raw.jsonl"
OUT=ROOT/"data/processed/realistic_trade_path_v1.json"

FEE_BPS=5.9
SLIPPAGE_BPS=0.0
CONTRACT_BTC=0.001
GRID=((4,8),(6,12),(8,16),(10,20),(12,24))

def f(x,d=0.0):
    try:return float(x)
    except:return d

def classify(m,l1):
    p=f(m.get("p")); s=abs(f(m.get("s")))
    if p<=0 or s<=0:return None
    bid=f(l1.get("bp")); ask=f(l1.get("ap"))
    if ask>0 and p>=ask:return ("LONG",s,p)
    if bid>0 and p<=bid:return ("SHORT",s,p)
    r=m.get("r")
    if r=="m":return ("SHORT",s,p)
    if r=="t":return ("LONG",s,p)
    return None

def run():
    l1={}; bids={}; asks={}; q5=deque(); q30=deque(); pts=deque()
    b5=s5=b30=s30=0.0; samples=[]; events=0
    with RAW.open() as fh:
        for line in fh:
            try:m=json.loads(line); m=m.get("message",m)
            except Exception:continue
            events+=1; typ=m.get("type"); ts=int(f(m.get("ts") or m.get("t")))
            if not ts:continue
            if typ=="ob_l1": l1=m; continue
            if typ=="ob_l2":
                bids={f(p):f(s) for p,s in m.get("b",[]) if f(s)>0}
                asks={f(p):f(s) for p,s in m.get("a",[]) if f(s)>0}
                continue
            if typ!="trades":continue
            c=classify(m,l1)
            if not c:continue
            side,size,px=c
            q5.append((ts,side,size)); q30.append((ts,side,size)); pts.append((ts,px))
            if side=="LONG":b5+=size;b30+=size
            else:s5+=size;s30+=size
            while q5 and q5[0][0]<ts-5_000_000:
                _,sd,z=q5.popleft()
                if sd=="LONG":b5-=z
                else:s5-=z
            while q30 and q30[0][0]<ts-30_000_000:
                _,sd,z=q30.popleft()
                if sd=="LONG":b30-=z
                else:s30-=z
            while pts and pts[0][0]<ts-5_000_000:pts.popleft()
            bb=f(l1.get("bp")); aa=f(l1.get("ap"))
            if bb<=0 or aa<=0:continue
            old=pts[0][1] if pts else px
            d5=(b5-s5)/(b5+s5) if b5+s5 else 0
            d30=(b30-s30)/(b30+s30) if b30+s30 else 0
            mom=(px/old-1)*100
            samples.append((ts,px,bb,aa,d5,d30,mom))

    results=[]
    for stop_bps,target_bps in GRID:
        trades=[]
        pos=None
        cooldown_until=0
        for i,s in enumerate(samples):
            ts,px,bid,ask,d5,d30,mom=s
            if pos:
                side=pos["side"]; entry=pos["entry"]
                stop=pos["stop"]; target=pos["target"]
                # Conservative event-path rule: executable quote crosses first; if both are crossed,
                # count STOP to avoid optimistic intrabar ordering.
                if side=="LONG":
                    hit_stop=bid<=stop; hit_target=bid>=target
                    exit_px=stop if hit_stop else target if hit_target else None
                else:
                    hit_stop=ask>=stop; hit_target=ask<=target
                    exit_px=stop if hit_stop else target if hit_target else None
                if exit_px is not None:
                    gross_bps=((exit_px/entry-1)*10000) if side=="LONG" else ((entry/exit_px-1)*10000)
                    net_bps=gross_bps-2*FEE_BPS-SLIPPAGE_BPS*2
                    trades.append({"entry_ts":pos["ts"],"exit_ts":ts,"side":side,"entry":entry,"exit":exit_px,
                                   "gross_bps":gross_bps,"net_bps":net_bps,
                                   "outcome":"WIN" if net_bps>0 else "LOSS"})
                    pos=None; cooldown_until=ts+5_000_000
                    continue
            if pos or ts<cooldown_until:continue
            # Research signal: continuation alignment, requiring cost-aware move room.
            long=d5>=0.12 and d30>=0.08 and mom>=0.025
            short=d5<=-0.12 and d30<=-0.08 and mom<=-0.025
            if not (long or short):continue
            if long:
                entry=ask*(1+SLIPPAGE_BPS/10000); stop=entry*(1-stop_bps/10000); target=entry*(1+target_bps/10000); side="LONG"
            else:
                entry=bid*(1-SLIPPAGE_BPS/10000); stop=entry*(1+stop_bps/10000); target=entry*(1-target_bps/10000); side="SHORT"
            pos={"ts":ts,"side":side,"entry":entry,"stop":stop,"target":target}
        if trades:
            wins=[t for t in trades if t["net_bps"]>0]; losses=[t for t in trades if t["net_bps"]<=0]
            avg=sum(t["net_bps"] for t in trades)/len(trades)
            gp=sum(t["net_bps"] for t in wins); gl=-sum(t["net_bps"] for t in losses)
            results.append({"stop_bps":stop_bps,"target_bps":target_bps,"n":len(trades),
                            "win_rate":len(wins)/len(trades),"avg_net_bps":avg,
                            "total_net_bps":sum(t["net_bps"] for t in trades),
                            "profit_factor":gp/gl if gl else None,
                            "max_drawdown_bps":max_drawdown([t["net_bps"] for t in trades]),
                            "longs":sum(t["side"]=="LONG" for t in trades),
                            "shorts":sum(t["side"]=="SHORT" for t in trades)})
    out={"events_read":events,"feature_samples":len(samples),"fee_bps_each_side":FEE_BPS,
         "slippage_bps_each_side":SLIPPAGE_BPS,"results":results,
         "warning":"Research-only. Real order submission is untouched and remains disabled.",
         "method":"Executable bid/ask entry and exit, first-hit stop/target, taker fees, one position at a time, chronological replay."}
    OUT.write_text(json.dumps(out,indent=2))
    print(json.dumps(out,indent=2))

def max_drawdown(vals):
    peak=cur=dd=0.0
    for x in vals:
        cur+=x; peak=max(peak,cur); dd=max(dd,peak-cur)
    return dd

if __name__=="__main__":run()
