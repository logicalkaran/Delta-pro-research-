"""Continuous live forward-label worker. Research/paper only."""
from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/live_microstructure_features_v1.jsonl"
OUT=ROOT/"data/processed/live_microstructure_labeled_v1.jsonl"
MAX_BYTES=20_000_000
H=(60,120,180,300)
seen=set()

def rows():
    a=[]
    if not SRC.exists(): return a
    for line in SRC.read_text().splitlines():
        try:a.append(json.loads(line))
        except:pass
    return sorted(a,key=lambda x:float(x["ts"]))

def main():
    while True:
        a=rows()
        for i,r in enumerate(a):
            key=r["ts"]
            if key in seen: continue
            px=float(r.get("mid",0))
            if px<=0: continue
            labels={}
            ok=True
            for h in H:
                target=float(r["ts"])+h
                q=next((z for z in a[i+1:] if float(z["ts"])>=target),None)
                if q is None: ok=False; break
                qp=float(q.get("mid",0))
                labels[str(h)]={"future_ts":q["ts"],"move_bps":(qp/px-1)*10000 if qp else None}
            if not ok: continue
            x=dict(r); x["labels"]=labels
            with OUT.open("a") as f:f.write(json.dumps(x,separators=(",",":"))+"\n")
            seen.add(key)
        if OUT.exists() and OUT.stat().st_size>MAX_BYTES:
            ls=OUT.read_text().splitlines()
            OUT.write_text("\n".join(ls[-max(1000,len(ls)//2):])+"\n")
        time.sleep(5)

if __name__=="__main__":main()
