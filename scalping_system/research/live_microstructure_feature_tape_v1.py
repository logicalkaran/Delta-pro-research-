"""Bounded live microstructure feature tape. Research/paper only."""
from pathlib import Path
import json,time,os
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data/live_microstructure_state.json"
OUT=ROOT/"data/processed/live_microstructure_features_v1.jsonl"
MAX_BYTES=20_000_000
INTERVAL=1.0

def f(x,d=0.0):
    try:return float(x)
    except:return d

def snapshot():
    d=json.loads(STATE.read_text())
    ob=d.get("order_book",{}); w=d.get("windows",{}); p=d.get("price",{})
    bid=f(ob.get("best_bid")); ask=f(ob.get("best_ask")); mid=f(ob.get("mid_price"))
    spread=ask-bid if ask and bid else 0
    depth5b=f(ob.get("bid_depth_5")); depth5a=f(ob.get("ask_depth_5"))
    depth10b=f(ob.get("bid_depth_10")); depth10a=f(ob.get("ask_depth_10"))
    return {
      "ts":f(d.get("updated_at_epoch",time.time())),
      "mid":mid,"spread":spread,
      "spread_bps":spread/mid*10000 if mid else 0,
      "imb5":f(ob.get("imbalance_5")),"imb10":f(ob.get("imbalance_10")),
      "depth5_ratio":depth5b/(depth5a or 1),
      "depth10_ratio":depth10b/(depth10a or 1),
      "delta5":f(w.get("5",{}).get("delta_pct")),
      "delta30":f(w.get("30",{}).get("delta_pct")),
      "delta60":f(w.get("60",{}).get("delta_pct")),
      "ret5":f(p.get("5",{}).get("return_pct")),
      "ret30":f(p.get("30",{}).get("return_pct")),
      "ret60":f(p.get("60",{}).get("return_pct")),
      "cvd":f(d.get("cvd")),
      "cvd_slope30":f(d.get("cvd_slope_30s")),
      "regime":str(d.get("regime","UNKNOWN")),
      "fresh":f(d.get("quality",{}).get("fresh_seconds"),999),
      "trade_samples":int(f(d.get("quality",{}).get("trade_samples"),0))
    }

def main():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    last=0
    while True:
        now=time.time()
        if now-last>=INTERVAL and STATE.exists():
            try:
                r=snapshot()
                with OUT.open("a") as fh: fh.write(json.dumps(r,separators=(",",":"))+"\n")
                last=now
                if OUT.stat().st_size>MAX_BYTES:
                    lines=OUT.read_text().splitlines()
                    keep=lines[-max(1000,len(lines)//2):]
                    OUT.write_text("\n".join(keep)+"\n")
            except Exception:
                pass
        time.sleep(.15)

if __name__=="__main__": main()
