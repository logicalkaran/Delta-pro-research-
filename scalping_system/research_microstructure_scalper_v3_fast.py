"""Fast chronological V3 research replay. Research-only; no orders."""
from __future__ import annotations
import bisect,json,math
from collections import deque
from pathlib import Path
from strategy.microstructure_scalper_v3 import evaluate
ROOT=Path(__file__).resolve().parent
INPUT=ROOT/"data/raw/delta_btc_raw.jsonl"
def num(x,d=0.0):
    try: v=float(x); return v if math.isfinite(v) else d
    except: return d
def load():
    out=[]
    with INPUT.open() as f:
        for line in f:
            try:
                m=json.loads(line).get("message",{})
                if m.get("type") not in {"trades","ob_l1","ob_l2"}: continue
                ts=int(num(m.get("ts") or m.get("t")))
                if ts: out.append((ts,m))
            except: pass
    out.sort(key=lambda x:x[0]); return out
def replay(ev):
    q5=deque(); q30=deque(); prices=[]; pts=[]; pvs=[]
    buy5=sell5=buy30=sell30=0.; l1={}; bids={}; asks={}
    book={"mid_price":0.,"spread":0.,"imbalance_5":0.}
    align_hist=deque(maxlen=10); delta_hist=deque(maxlen=4); ret_hist=deque(maxlen=20)
    decisions=[]; last=-1
    def refresh():
        nonlocal book
        bs=sorted(((p,s) for p,s in bids.items() if s>0),reverse=True); a=sorted(((p,s) for p,s in asks.items() if s>0))
        if not bs and num(l1.get("bp"))>0: bs=[(num(l1["bp"]),num(l1["bs"]))]; a=[(num(l1["ap"]),num(l1["as"]))]
        b=sum(s for _,s in bs[:5]); aa=sum(s for _,s in a[:5]); bb=bs[0][0] if bs else 0.; ap=a[0][0] if a else 0.; mid=(bb+ap)/2 if bb and ap else 0.
        book={"mid_price":mid,"spread":ap-bb if mid else 0.,"imbalance_5":(b-aa)/(b+aa) if b+aa else 0.}
    def classify(m):
        p=num(m.get("p")); s=abs(num(m.get("s"))); bid=num(l1.get("bp")); ask=num(l1.get("ap"))
        if p<=0 or s<=0:return None
        if ask>0 and p>=ask:return "buy",s,p
        if bid>0 and p<=bid:return "sell",s,p
        if m.get("r")=="m":return "sell",s,p
        if m.get("r")=="t":return "buy",s,p
    for ts,m in ev:
        typ=m["type"]
        if typ=="ob_l1": l1=m; refresh(); continue
        if typ=="ob_l2": bids={num(p):num(s) for p,s in m.get("b",[]) if num(s)>0}; asks={num(p):num(s) for p,s in m.get("a",[]) if num(s)>0}; refresh(); continue
        c=classify(m)
        if not c: continue
        side,size,price=c; prices.append((ts,price)); pts.append(ts); pvs.append(price)
        q5.append((ts,side,size)); q30.append((ts,side,size))
        if side=="buy": buy5+=size; buy30+=size
        else: sell5+=size; sell30+=size
        while q5 and q5[0][0]<ts-5_000_000:
            _,s,z=q5.popleft(); buy5-=z if s=="buy" else 0; sell5-=z if s=="sell" else 0
        while q30 and q30[0][0]<ts-30_000_000:
            _,s,z=q30.popleft(); buy30-=z if s=="buy" else 0; sell30-=z if s=="sell" else 0
        if len(q5)<4: continue
        t5=buy5+sell5; t30=buy30+sell30; d5=(buy5-sell5)/t5 if t5 else 0.; d30=(buy30-sell30)/t30 if t30 else 0.
        idx=bisect.bisect_left(pts,ts-5_000_000); ret=(price/pvs[idx]-1)*100 if idx<len(pvs) and pvs[idx]>0 else 0.
        # Persistence = fraction of recent trade decisions aligned with current direction.
        aligned=(d5>0 and d30>0 and book["imbalance_5"]>0 and ret>0) or (d5<0 and d30<0 and book["imbalance_5"]<0 and ret<0)
        align_hist.append(1 if aligned else 0)
        persistence=sum(align_hist)/len(align_hist)
        delta_hist.append(d5); cvd_acc=(delta_hist[-1]-delta_hist[0]) if len(delta_hist)>1 else 0.
        ret_hist.append(ret); vol=max(ret_hist)-min(ret_hist) if ret_hist else 0.
        state={"windows":{"5":{"delta_pct":d5,"trades":len(q5)},"30":{"delta_pct":d30,"trades":len(q30)}},
               "price":{"5":{"return_pct":ret}},"order_book":book,"quality":{"fresh_seconds":0.},
               "persistence":persistence,"cvd_acceleration":cvd_acc,"volatility_pct":vol}
        sig=evaluate(state)
        if sig.action in ("LONG","SHORT") and ts!=last:
            decisions.append({"ts":ts,"price":price,"action":sig.action,"score":sig.score,"persistence":persistence,"expected_move_pct":sig.expected_move_pct}); last=ts
    return decisions,pts,pvs
def outcomes(rows,ts,pv):
    out=[]
    for r in rows:
        z=dict(r)
        for h in (10,30):
            i=bisect.bisect_left(ts,r["ts"]+h*1_000_000)
            if i>=len(pv): z[f"ret_{h}s"]=None; continue
            raw=(pv[i]/r["price"]-1)*100; z[f"ret_{h}s"]=raw if r["action"]=="LONG" else -raw
        out.append(z)
    return out
def summary(rows):
    print("V3 signals:",len(rows),"long",sum(r["action"]=="LONG" for r in rows),"short",sum(r["action"]=="SHORT" for r in rows))
    for h in (10,30):
        x=[r[f"ret_{h}s"] for r in rows if r[f"ret_{h}s"] is not None]
        if not x: continue
        gp=sum(max(v,0) for v in x); gl=sum(-min(v,0) for v in x)
        print(f"{h}s n={len(x)} win={sum(v>0 for v in x)/len(x):.4f} avg={sum(x)/len(x):.6f}% PF={(gp/gl if gl else 0):.3f}")
        for a in ("LONG","SHORT"):
            y=[r[f"ret_{h}s"] for r in rows if r["action"]==a and r[f"ret_{h}s"] is not None]
            if y: print(f"  {a} n={len(y)} win={sum(v>0 for v in y)/len(y):.4f} avg={sum(y)/len(y):.6f}%")
def main():
    e=load(); print("events_loaded:",len(e)); rows,ts,pv=replay(e); rows=outcomes(rows,ts,pv); summary(rows)
    out=ROOT/"data/processed/microstructure_scalper_v3_backtest.jsonl"
    with out.open("w") as f:
        for r in rows:f.write(json.dumps(r,separators=(",",":"))+"\n")
    print("results:",out)
if __name__=="__main__":main()
