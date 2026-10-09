"""ML Scalper V3 dataset builder: joins event-level trade-flow/book features and creates forward labels."""
import csv,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
FLOW=ROOT/"data/processed/btc_trade_flow_features_v2.csv"
BOOK=ROOT/"data/processed/btc_orderflow_features_v1.csv"
OUT=ROOT/"data/processed/ml_scalper_v3_dataset.jsonl"
META=ROOT/"data/processed/ml_scalper_v3_dataset_meta.json"

def read_csv(p):
    with p.open() as f:return list(csv.DictReader(f))
def main():
    flow=read_csv(FLOW); book=read_csv(BOOK)
    if not flow or not book:
        raise SystemExit("missing source data")
    # nearest book snapshot at/before each 1s flow bar, with strict freshness <=250ms.
    bi=0; rows=[]
    for i,r in enumerate(flow):
        ts=int(r["timestamp"])
        while bi+1<len(book) and int(book[bi+1]["timestamp"])<=ts: bi+=1
        b=book[bi]; age_us=ts-int(b["timestamp"])
        if age_us<0 or age_us>250_000: continue
        rows.append({
          "ts":ts,"price":float(r["price_last"]),"total_trades":int(r["total_trades"]),
          "total_volume":float(r["total_volume"]),"delta":float(r["net_delta"]),
          "delta_ratio":float(r["delta_ratio"]),"max_trade":float(r["max_trade_size"]),
          "spread":float(b["spread"]),"imbalance5":float(b["imbalance_5"]),
          "imbalance10":float(b["imbalance_10"]),"book_age_us":age_us})
    # Forward 1/3/5-bar labels, using only future price relative to current.
    out=[]
    for i,r in enumerate(rows):
        if i+5>=len(rows): break
        p=r["price"]
        for h in (1,3,5):
            f=rows[i+h]["price"]
            gross_bps=(f/p-1)*10000
            rr=dict(r); rr["horizon_bars"]=h; rr["future_return_bps"]=gross_bps
            rr["net_return_bps"]=gross_bps-12.0
            out.append(rr)
    with OUT.open("w") as f:
        for r in out:f.write(json.dumps(r)+"\n")
    meta={"version":"ml_scalper_v3_dataset","source_flow_rows":len(flow),"source_book_rows":len(book),
          "aligned_rows":len(rows),"labeled_rows":len(out),"freshness_max_us":250000,
          "label_cost_bps":12.0,"horizons":[1,3,5],
          "status":"INSUFFICIENT_FOR_TRAINING" if len(out)<1000 else "READY_FOR_RESEARCH",
          "live_orders":False}
    META.write_text(json.dumps(meta,indent=2)); print(json.dumps(meta,indent=2))
if __name__=="__main__":main()
