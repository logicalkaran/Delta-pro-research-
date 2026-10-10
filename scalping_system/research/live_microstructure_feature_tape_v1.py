"""Bounded live microstructure feature tape. Research/paper only."""
from pathlib import Path
import json,time,os,uuid
try:
    from research.microprice_validation_hook_v1 import microprice_features
except ModuleNotFoundError:  # direct script execution from research/
    from microprice_validation_hook_v1 import microprice_features
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data/live_microstructure_state.json"
OUT=ROOT/"data/processed/live_microstructure_features_v1.jsonl"
MAX_BYTES=20_000_000
INTERVAL=1.0

def f(x,d=0.0):
    try:return float(x)
    except:return d

def snapshot(session_id=None):
    d=json.loads(STATE.read_text())
    ob=d.get("order_book",{}); w=d.get("windows",{}); p=d.get("price",{})
    bid=f(ob.get("best_bid")); ask=f(ob.get("best_ask")); mid=f(ob.get("mid_price"))
    spread=ask-bid if ask and bid else 0
    depth5b=f(ob.get("bid_depth_5")); depth5a=f(ob.get("ask_depth_5"))
    depth10b=f(ob.get("bid_depth_10")); depth10a=f(ob.get("ask_depth_10"))
    mp=microprice_features(ob)
    bids=ob.get("bids_l5") or []; asks=ob.get("asks_l5") or []
    bq=f(bids[0][1]) if bids and len(bids[0])>1 else 0.0
    aq=f(asks[0][1]) if asks and len(asks[0])>1 else 0.0
    den=bq+aq; w1=w.get("1",{})
    state_ts=f(d.get("updated_at_epoch",time.time()))
    state_age=max(0.0,time.time()-state_ts)
    return {
      "session_id":session_id or "UNSCOPED",
      "microprice_method":"price_distance_decay_v1",
      "ts":state_ts,"state_age_s":state_age,
      "mid":mid,"bid":bid,"ask":ask,"spread":spread,
      "spread_bps":spread/mid*10000 if mid else 0,
      "imb5":f(ob.get("imbalance_5")),"imb10":f(ob.get("imbalance_10")),
      "microprice_status":mp["status"],"microprice":mp["microprice"],
      "microprice_shift":mp.get("microprice_shift"),"microprice_imbalance_n":mp.get("imbalance_n"),
      "microprice_direction":mp.get("direction",0),"microprice_threshold_pass":mp.get("entry_threshold_pass",False),
      "l1_imbalance":(bq-aq)/den if den else None,
      "signed_flow_1s":f(w1.get("buy_volume"))-f(w1.get("sell_volume")),
      "flow_1s_trade_count":int(f(w1.get("trades"))),
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
      "fresh":state_age,
      "trade_samples":int(f(d.get("quality",{}).get("trade_samples"),0))
    }

def main():
    session_id=os.environ.get("SESSION_ID") or ("l2_5level_"+time.strftime("%Y%m%d_%H%M%S",time.gmtime())+"_"+uuid.uuid4().hex[:6])
    OUT.parent.mkdir(parents=True,exist_ok=True)
    last=0
    last_source_ts=None
    while True:
        now=time.time()
        if now-last>=INTERVAL and STATE.exists():
            try:
                r=snapshot(session_id)
                # Only append a new source snapshot once; don't duplicate stale state during feed gaps.
                if r["ts"] != last_source_ts:
                    with OUT.open("a") as fh: fh.write(json.dumps(r,separators=(",",":"))+"\n")
                    last_source_ts=r["ts"]
                last=now
                if OUT.stat().st_size>MAX_BYTES:
                    lines=OUT.read_text().splitlines()
                    keep=lines[-max(1000,len(lines)//2):]
                    OUT.write_text("\n".join(keep)+"\n")
            except Exception:
                pass
        time.sleep(.15)

if __name__=="__main__": main()
