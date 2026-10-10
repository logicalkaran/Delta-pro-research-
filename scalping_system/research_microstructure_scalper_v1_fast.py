"""Fast chronological research replay for microstructure_scalper_v1.
Research-only: no exchange access and no production execution writes.
Uses only information available at each decision timestamp.
"""
from __future__ import annotations
import bisect, json, math
from collections import deque
from pathlib import Path
from strategy.microstructure_scalper_v1 import evaluate

ROOT=Path(__file__).resolve().parent
INPUT=ROOT/"data/raw/delta_btc_raw.jsonl"
HORIZONS=(10,30)
WINDOW5=5_000_000
WINDOW30=30_000_000


def num(x,d=0.0):
    try:
        v=float(x); return v if math.isfinite(v) else d
    except (TypeError,ValueError): return d


def load_events():
    out=[]
    with INPUT.open() as f:
        for line in f:
            try:
                r=json.loads(line); m=r.get("message",r); typ=m.get("type")
                if typ not in {"trades","ob_l1","ob_l2"}: continue
                ts=int(num(m.get("ts") or m.get("t")))
                if ts: out.append((ts,m))
            except (json.JSONDecodeError,ValueError,TypeError): pass
    out.sort(key=lambda x:x[0])
    return out


def replay(events):
    q5=deque(); q30=deque()
    buy5=sell5=buy30=sell30=0.0
    l1={}; bids={}; asks={}
    book_stats={"mid_price":0.0,"spread":0.0,"imbalance_5":0.0,"imbalance_10":0.0}
    prices=[]; price_ts=[]; price_vals=[]; decisions=[]
    last_signal_ts=-1

    def classify(m):
        p=num(m.get("p")); s=abs(num(m.get("s")))
        if p<=0 or s<=0: return None
        bid=num(l1.get("bp")); ask=num(l1.get("ap"))
        if ask>0 and p>=ask: return "buy",s,p
        if bid>0 and p<=bid: return "sell",s,p
        if m.get("r")=="m": return "sell",s,p
        if m.get("r")=="t": return "buy",s,p
        return None

    def refresh_book():
        nonlocal book_stats
        bs=sorted(((p,s) for p,s in bids.items() if s>0),reverse=True)
        a=sorted(((p,s) for p,s in asks.items() if s>0))
        if not bs and num(l1.get("bp"))>0:
            bs=[(num(l1.get("bp")),num(l1.get("bs")))]
            a=[(num(l1.get("ap")),num(l1.get("as")))]
        b5=sum(s for _,s in bs[:5]); a5=sum(s for _,s in a[:5])
        b10=sum(s for _,s in bs[:10]); a10=sum(s for _,s in a[:10])
        bb=bs[0][0] if bs else 0.0; aa=a[0][0] if a else 0.0
        mid=(bb+aa)/2 if bb>0 and aa>0 else 0.0
        book_stats={"mid_price":mid,"spread":aa-bb if mid else 0.0,
                    "imbalance_5":(b5-a5)/(b5+a5) if b5+a5 else 0.0,
                    "imbalance_10":(b10-a10)/(b10+a10) if b10+a10 else 0.0}

    def expire(ts):
        nonlocal buy5,sell5,buy30,sell30
        while q5 and q5[0][0] < ts-WINDOW5:
            _,side,size=q5.popleft()
            if side=="buy": buy5-=size
            else: sell5-=size
        while q30 and q30[0][0] < ts-WINDOW30:
            _,side,size=q30.popleft()
            if side=="buy": buy30-=size
            else: sell30-=size

    for ts,m in events:
        typ=m["type"]
        if typ=="ob_l1":
            l1=m; refresh_book()
        elif typ=="ob_l2":
            bids={num(p):num(s) for p,s in m.get("b",[]) if num(s)>0}
            asks={num(p):num(s) for p,s in m.get("a",[]) if num(s)>0}
            refresh_book()
        else:
            c=classify(m)
            if not c: continue
            side,size,price=c
            prices.append((ts,price)); price_ts.append(ts); price_vals.append(price)
            q5.append((ts,side,size)); q30.append((ts,side,size))
            if side=="buy": buy5+=size; buy30+=size
            else: sell5+=size; sell30+=size
            expire(ts)
            if len(q5)<3: continue
            total5=buy5+sell5; total30=buy30+sell30
            ret5=0.0
            idx=bisect.bisect_left(price_ts,ts-WINDOW5)
            if idx<len(price_vals) and price_vals[idx]>0: ret5=(price/price_vals[idx]-1)*100
            state={"regime":"REPLAY","windows":{
                "5":{"delta_pct":(buy5-sell5)/total5 if total5 else 0.0,"delta":buy5-sell5,"trades":len(q5)},
                "30":{"delta_pct":(buy30-sell30)/total30 if total30 else 0.0,"delta":buy30-sell30,"trades":len(q30)},
            },"price":{"5":{"return_pct":ret5}},"order_book":book_stats,
            "quality":{"fresh_seconds":0.0},"_price":price}
            sig=evaluate(state)
            if sig.action in ("LONG","SHORT") and ts!=last_signal_ts:
                decisions.append({"ts":ts,"price":price,"action":sig.action,"score":sig.score,"reasons":list(sig.reasons)})
                last_signal_ts=ts
    return decisions,price_ts,price_vals


def attach_outcomes(rows,ts_list,prices):
    out=[]
    for d in rows:
        r=dict(d)
        for h in HORIZONS:
            target=d["ts"]+h*1_000_000
            i=bisect.bisect_left(ts_list,target)
            if i>=len(prices): r[f"ret_{h}s"]=None; continue
            raw=(prices[i]/d["price"]-1)*100
            signed=raw if d["action"]=="LONG" else -raw
            r[f"ret_{h}s"]=signed; r[f"win_{h}s"]=signed>0
        out.append(r)
    return out


def summarize(rows):
    print("="*72); print("MICROSTRUCTURE SCALPER V1 FAST HISTORICAL REPLAY"); print("="*72)
    print("signals:",len(rows),"longs:",sum(r["action"]=="LONG" for r in rows),"shorts:",sum(r["action"]=="SHORT" for r in rows))
    for h in HORIZONS:
        xs=[r[f"ret_{h}s"] for r in rows if r.get(f"ret_{h}s") is not None]
        if not xs: print(f"{h}s: no completed outcomes"); continue
        wins=sum(x>0 for x in xs); gross=sum(max(x,0) for x in xs); loss=sum(-min(x,0) for x in xs)
        print(f"{h:>2}s n={len(xs)} win_rate={wins/len(xs):.4f} avg_signed_return_pct={sum(xs)/len(xs):.6f} profit_factor={(gross/loss if loss else float('inf')):.4f} best={max(xs):.6f} worst={min(xs):.6f}")
        for a in ("LONG","SHORT"):
            ys=[r[f"ret_{h}s"] for r in rows if r["action"]==a and r.get(f"ret_{h}s") is not None]
            if ys: print(f"    {a.lower():5s} n={len(ys)} win_rate={sum(x>0 for x in ys)/len(ys):.4f} avg={sum(ys)/len(ys):.6f}")
    print("Note: raw price outcomes; fees, slippage, queue position and funding are excluded.")
    print("This is research evidence, not live-trading validation.")


def main():
    events=load_events(); print("events_loaded:",len(events))
    decisions,ts_list,prices=replay(events); rows=attach_outcomes(decisions,ts_list,prices)
    summarize(rows)
    out=ROOT/"data/processed/microstructure_scalper_v1_backtest_fast.jsonl"
    with out.open("w") as f:
        for r in rows: f.write(json.dumps(r,separators=(",",":"))+"\n")
    print("results:",out)

if __name__=="__main__": main()
