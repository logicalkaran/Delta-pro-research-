"""Live microstructure forward-label evaluator. Research/paper only.

Reads the bounded feature tape and creates causal future-return labels using
time-based horizons. It never changes trading/execution settings.
"""
from pathlib import Path
from collections import deque
import json,time,math

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/live_microstructure_features_v1.jsonl"
OUT=ROOT/"data/processed/live_microstructure_labeled_v1.jsonl"
MAX_BYTES=20_000_000
HORIZONS=(60,120,180,300)

def load():
    if not SRC.exists(): return []
    a=[]
    for line in SRC.read_text().splitlines():
        try:a.append(json.loads(line))
        except:pass
    return sorted(a,key=lambda x:float(x.get("ts",0)))

def nearest(rows,target,start):
    lo=start; hi=len(rows)-1
    while lo<=hi:
        m=(lo+hi)//2
        if float(rows[m]["ts"])<target: lo=m+1
        else: hi=m-1
    if lo>=len(rows): return None
    return rows[lo]

def main():
    rows=load()
    out=[]
    for i,r in enumerate(rows):
        px=float(r.get("mid",0))
        if px<=0: continue
        labels={}
        complete=True
        for h in HORIZONS:
            q=nearest(rows,float(r["ts"])+h,i+1)
            if q is None:
                complete=False; break
            qp=float(q.get("mid",0))
            labels[str(h)]={"future_ts":q["ts"],"future_mid":qp,
                            "return_pct":(qp/px-1)*100 if qp else None,
                            "move_bps":(qp/px-1)*10000 if qp else None}
        if complete:
            x=dict(r); x["labels"]=labels; out.append(x)
    text="".join(json.dumps(x,separators=(",",":"))+"\n" for x in out)
    if len(text)>MAX_BYTES:
        text="".join(text.splitlines(True)[-max(1000,len(text.splitlines())//2):])
    OUT.write_text(text)
    print(json.dumps({"feature_rows":len(rows),"complete_labeled_rows":len(out),"output_bytes":len(text),"horizons":HORIZONS},indent=2))

if __name__=="__main__":main()
