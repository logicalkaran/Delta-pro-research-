"""Historical replay/backtest for microstructure_scalper_v1.

Research-only. No exchange access and no production strategy/execution writes.
Signal features use only events at or before the decision timestamp.
Outcomes are measured from later trades, preventing look-ahead.
"""
from __future__ import annotations
import json, math
from collections import deque
from pathlib import Path
from strategy.microstructure_scalper_v1 import evaluate

ROOT=Path(__file__).resolve().parent
INPUTS=[ROOT/"data/raw/delta_btc_raw.jsonl"]
HORIZONS=(10,30)
WINDOW_US=(5_000_000,30_000_000)
MAX_EVENTS=250_000


def num(x,d=0.0):
    try:
        v=float(x)
        return v if math.isfinite(v) else d
    except (TypeError,ValueError):
        return d


def load_events():
    events=[]
    for path in INPUTS:
        with path.open() as f:
            for line in f:
                try:
                    r=json.loads(line); m=r.get("message",r)
                    ts=int(num(m.get("ts") or m.get("t"),0))
                    if ts and m.get("type") in {"trades","ob_l1","ob_l2"}:
                        events.append((ts,m))
                except (json.JSONDecodeError,ValueError):
                    pass
    events.sort(key=lambda x:x[0])
    return events[-MAX_EVENTS:]


def replay(events):
    trades=deque(maxlen=10000)
    prices=deque(maxlen=10000)
    book={"bids":{}, "asks":{}, "mid_price":0.0, "spread":0.0,
          "imbalance_5":0.0, "imbalance_10":0.0}
    l1={}
    decisions=[]

    def classify(m):
        p=num(m.get("p")); s=abs(num(m.get("s")))
        bid=num(l1.get("bp")); ask=num(l1.get("ap"))
        if p<=0 or s<=0: return None
        if ask>0 and p>=ask: return ("buy",s,p)
        if bid>0 and p<=bid: return ("sell",s,p)
        if m.get("r")=="m": return ("sell",s,p)
        if m.get("r")=="t": return ("buy",s,p)
        return None

    def book_stats():
        bids=sorted(book["bids"].items(),reverse=True)
        asks=sorted(book["asks"].items())
        if not bids and l1.get("bp") is not None:
            bids=[(num(l1.get("bp")),num(l1.get("bs")))]
            asks=[(num(l1.get("ap")),num(l1.get("as")))]
        b5=sum(x[1] for x in bids[:5]); a5=sum(x[1] for x in asks[:5])
        b10=sum(x[1] for x in bids[:10]); a10=sum(x[1] for x in asks[:10])
        bb=bids[0][0] if bids else 0; aa=asks[0][0] if asks else 0
        mid=(bb+aa)/2 if bb>0 and aa>0 else 0
        spread=aa-bb if bb>0 and aa>0 else 0
        return {"mid_price":mid,"spread":spread,
                "imbalance_5":(b5-a5)/(b5+a5) if b5+a5 else 0,
                "imbalance_10":(b10-a10)/(b10+a10) if b10+a10 else 0}

    def snapshot(ts):
        def stats(window):
            xs=[x for x in trades if x[0]>=ts-window]
            buy=sum(x[2] for x in xs if x[1]=="buy")
            sell=sum(x[2] for x in xs if x[1]=="sell")
            total=buy+sell
            return {"delta_pct":(buy-sell)/total if total else 0,
                    "delta":buy-sell,"trades":len(xs)}
        w5=stats(WINDOW_US[0]); w30=stats(WINDOW_US[1])
        current=prices[-1][1] if prices else 0
        old=next((x for x in prices if x[0]>=ts-WINDOW_US[0]),None)
        ret5=((current/old[1])-1)*100 if old and old[1] else 0
        b=book_stats()
        return {"regime":"REPLAY","windows":{"5":w5,"30":w30},
                "price":{"5":{"return_pct":ret5}},
                "order_book":b,
                "quality":{"fresh_seconds":0.0},
                "_price":current}

    for ts,m in events:
        typ=m["type"]
        if typ=="ob_l1":
            l1=m
        elif typ=="ob_l2":
            bids={num(p):num(s) for p,s in m.get("b",[]) if num(s)>0}
            asks={num(p):num(s) for p,s in m.get("a",[]) if num(s)>0}
            book["bids"],book["asks"]=bids,asks
        elif typ=="trades":
            c=classify(m)
            if c:
                side,size,price=c
                trades.append((ts,side,size))
                prices.append((ts,price))
                if len(trades)>=5:
                    st=snapshot(ts)
                    sig=evaluate(st)
                    if sig.action in ("LONG","SHORT"):
                        decisions.append({"ts":ts,"price":price,"action":sig.action,
                                          "score":sig.score,"reasons":list(sig.reasons)})
    return decisions, prices


def outcomes(decisions, prices):
    results=[]
    for d in decisions:
        row=dict(d)
        for h in HORIZONS:
            target=d["ts"]+h*1_000_000
            future=next((p for ts,p in prices if ts>=target),None)
            if future is None:
                row[f"ret_{h}s"]=None
                continue
            r=(future/d["price"]-1)*100
            signed=r if d["action"]=="LONG" else -r
            row[f"ret_{h}s"]=signed
            row[f"win_{h}s"]=signed>0
        results.append(row)
    return results


def summarize(rows):
    print("="*72)
    print("MICROSTRUCTURE SCALPER V1 HISTORICAL REPLAY")
    print("="*72)
    print("input: data/raw/delta_btc_raw.jsonl")
    print("signals:",len(rows))
    for h in HORIZONS:
        xs=[r[f"ret_{h}s"] for r in rows if r.get(f"ret_{h}s") is not None]
        if not xs:
            print(f"{h}s: no completed outcomes")
            continue
        wins=sum(x>0 for x in xs)
        avg=sum(xs)/len(xs)
        gross=sum(max(x,0) for x in xs)
        loss=sum(-min(x,0) for x in xs)
        pf=gross/loss if loss else float("inf")
        print(f"{h:>2}s: n={len(xs)} win_rate={wins/len(xs):.3f} avg_signed_return_pct={avg:.5f} profit_factor={pf:.3f} best={max(xs):.5f} worst={min(xs):.5f}")
    longs=sum(r["action"]=="LONG" for r in rows)
    shorts=sum(r["action"]=="SHORT" for r in rows)
    print("longs:",longs,"shorts:",shorts)
    print("Note: fees, slippage, queue position and funding are NOT included.")
    print("This is research evidence, not live-trading validation.")


def main():
    events=load_events()
    decisions,prices=replay(events)
    rows=outcomes(decisions,prices)
    summarize(rows)
    out=ROOT/"data/processed/microstructure_scalper_v1_backtest.jsonl"
    with out.open("w") as f:
        for r in rows: f.write(json.dumps(r,separators=(",",":"))+"\n")
    print("results:",out)


if __name__=="__main__":
    main()
