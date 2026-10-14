"""Research-only Qwen data and retrieval helpers. No strategy/execution imports."""
from __future__ import annotations
import json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FEATURES = ROOT / "data/processed/live_microstructure_features_v1.jsonl"
LABELED = ROOT / "data/processed/live_microstructure_labeled_v1.jsonl"
CANDLES = ROOT / "data/live_candles.json"
OUT = Path(__file__).with_name("training.jsonl")
FEATURE_KEYS = ("mid", "spread_bps", "imb5", "imb10", "depth5_ratio", "depth10_ratio",
                "delta5", "delta30", "delta60", "ret5", "ret30", "ret60", "cvd",
                "cvd_slope30", "regime", "fresh", "trade_samples")

def read_jsonl(path: Path) -> list[dict]:
    rows=[]
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                obj=json.loads(line)
                if isinstance(obj,dict): rows.append(obj)
            except (ValueError, TypeError): pass
    return rows

def feature_view(row: dict) -> dict:
    """Whitelist causal-at-issue fields; future labels never enter this view."""
    return {k: row[k] for k in FEATURE_KEYS if k in row}

def make_example(row: dict, include_target: bool) -> dict:
    item={"id":str(row.get("ts", "")), "kind":"labeled_example" if include_target else "feature_snapshot",
          "source":"live_microstructure_labeled_v1" if include_target else "live_microstructure_features_v1",
          "input":{"as_of_ts":row.get("ts"),"features":feature_view(row),
                   "context_status":"microstructure only; candle timeframe context unavailable in source row"},
          "epistemic_type":"observed_features"}
    if include_target:
        item["target"]={"type":"observed_forward_outcome","horizons":{
            h:{"move_bps":v.get("move_bps")} for h,v in row.get("labels",{}).items()
            if isinstance(v,dict) and _finite(v.get("move_bps"))}}
    return item

def _finite(x):
    try: return math.isfinite(float(x))
    except (TypeError, ValueError): return False

def build_training(features_path: Path=FEATURES, labeled_path: Path=LABELED,
                   out_path: Path=OUT, feature_limit: int=681, label_limit: int=387) -> dict:
    # Explicit limits preserve the supplied research cohort; chronological tails keep latest rows.
    fs=sorted(read_jsonl(features_path),key=lambda r:float(r.get("ts",0)))[-feature_limit:]
    ls=sorted(read_jsonl(labeled_path),key=lambda r:float(r.get("ts",0)))[-label_limit:]
    examples=[make_example(r,False) for r in fs]+[make_example(r,True) for r in ls]
    out_path.write_text("".join(json.dumps(x,separators=(",",":"),allow_nan=False)+"\n" for x in examples))
    return {"feature_snapshots":len(fs),"labeled_examples":len(ls),"examples":len(examples),"path":str(out_path)}

def timeframe_context(candles: list[dict]) -> dict:
    """Aggregate closed 1m candles into compact trailing 5m/15m/1h context."""
    cs=sorted((c for c in candles if _finite(c.get("timestamp")) and _finite(c.get("close")) and float(c["close"])>0),key=lambda c:float(c["timestamp"]))
    result={}
    for name,n in (("5m",5),("15m",15),("1h",60)):
        bars=cs[-n:]
        if len(bars)<n:
            result[name]={"ready":False,"samples":len(bars),"required":n}; continue
        closes=[float(b["close"]) for b in bars]
        result[name]={"ready":True,"samples":len(bars),"start_ts":bars[0]["timestamp"],"end_ts":bars[-1]["timestamp"],
                      "return_pct":(closes[-1]/closes[0]-1)*100,
                      "high_low_pct":(max(float(b.get("high",b["close"])) for b in bars)/min(float(b.get("low",b["close"])) for b in bars)-1)*100}
    return result

def build_context(state_path: Path=ROOT/"data/live_microstructure_state.json",
                  candles_path: Path=CANDLES, now_ts: float|None=None,
                  tape_path: Path=FEATURES, tape_limit: int=10) -> dict:
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    candle_data=json.loads(candles_path.read_text()) if candles_path.exists() else []
    candles=candle_data if isinstance(candle_data,list) else candle_data.get("candles",[])
    micro={"ts":state.get("updated_at_epoch"),"mid":state.get("order_book",{}).get("mid_price"),
           "imb5":state.get("order_book",{}).get("imbalance_5"),"imb10":state.get("order_book",{}).get("imbalance_10"),
           "spread_bps":None,"delta5":state.get("windows",{}).get("5",{}).get("delta_pct"),
           "delta30":state.get("windows",{}).get("30",{}).get("delta_pct"),"delta60":state.get("windows",{}).get("60",{}).get("delta_pct"),
           "ret5":state.get("price",{}).get("5",{}).get("return_pct"),"ret30":state.get("price",{}).get("30",{}).get("return_pct"),
           "ret60":state.get("price",{}).get("60",{}).get("return_pct"),"regime":state.get("regime","UNKNOWN"),
           "fresh_seconds":state.get("quality",{}).get("fresh_seconds")}
    bid=state.get("order_book",{}).get("best_bid"); ask=state.get("order_book",{}).get("best_ask"); mid=micro["mid"]
    try:
        if float(mid)>0 and bid is not None and ask is not None: micro["spread_bps"]=(float(ask)-float(bid))/float(mid)*10000
    except (TypeError,ValueError): pass
    age=None
    if now_ts is not None and _finite(micro["ts"]): age=max(0.0,float(now_ts)-float(micro["ts"]))
    tape=sorted(read_jsonl(tape_path),key=lambda r:float(r.get("ts",0)))[-max(0,tape_limit):]
    recent=[{"as_of_ts":r.get("ts"),"features":feature_view(r)} for r in tape]
    return {"schema":"qwen-research-context-v1","as_of_ts":now_ts,"microstructure":micro,
            "micro_age_seconds":age,"recent_microstructure":recent,"timeframes":timeframe_context(candles),
            "retrieval_policy":"Features only. Never include labels, future prices, future timestamps, or model-generated outcomes.",
            "research_only":True,"orders":False,"risk_or_leverage_control":False}

if __name__=="__main__": print(json.dumps(build_training(),indent=2))
