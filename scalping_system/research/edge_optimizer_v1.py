"""Research-only walk-forward optimizer for BTCUSD microstructure signals.
Replays the existing raw public feed. Never submits orders.
Conservative cost: 0.05% taker each side + 18% GST on trading fees.
"""
import argparse, json, os, math
from collections import deque
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/processed/edge_optimizer_v1.json"
try:
    from research.raw_archive_reader_v1 import DEFAULT_ARCHIVE_DIR, DEFAULT_LEGACY_PATH, iter_raw_records
except ModuleNotFoundError:  # direct script execution from research/
    from raw_archive_reader_v1 import DEFAULT_ARCHIVE_DIR, DEFAULT_LEGACY_PATH, iter_raw_records
COST_BPS=11.8

def f(x,d=0.0):
    try:return float(x)
    except:return d

def classify(m,l1):
    p=f(m.get("p")); s=abs(f(m.get("s")))
    if p<=0 or s<=0:return None
    bid=f(l1.get("bp")); ask=f(l1.get("ap"))
    if ask>0 and p>=ask:return "buy",s,p
    if bid>0 and p<=bid:return "sell",s,p
    r=m.get("r")
    if r=="m":return "sell",s,p
    if r=="t":return "buy",s,p
    return None

def run(max_events=2000000, session_id=None, archive_dir=DEFAULT_ARCHIVE_DIR, legacy_path=DEFAULT_LEGACY_PATH):
    q5=deque(); q30=deque(); pts=deque(); l1={}; bids={}; asks={}
    b5=s5=b30=s30=0.0; samples=[]; n=0
    for record in iter_raw_records(session_id=session_id, data_dir=archive_dir, legacy_path=legacy_path):
            if n>=max_events: break
            n+=1
            try:
                m=record.get("message",record)
                if not isinstance(m,dict): continue
            except Exception: continue
            typ=m.get("type")
            ts=int(f(m.get("ts") or m.get("t")))
            if not ts: continue
            if typ=="ob_l1": l1=m; continue
            if typ=="ob_l2":
                bids={f(p):f(s) for p,s in m.get("b",[]) if f(s)>0}
                asks={f(p):f(s) for p,s in m.get("a",[]) if f(s)>0}
                continue
            if typ!="trades": continue
            c=classify(m,l1)
            if not c: continue
            side,size,px=c
            q5.append((ts,side,size)); q30.append((ts,side,size)); pts.append((ts,px))
            if side=="buy": b5+=size;b30+=size
            else:s5+=size;s30+=size
            while q5 and q5[0][0]<ts-5_000_000:
                _,sd,sz=q5.popleft()
                if sd=="buy":b5-=sz
                else:s5-=sz
            while q30 and q30[0][0]<ts-30_000_000:
                _,sd,sz=q30.popleft()
                if sd=="buy":b30-=sz
                else:s30-=sz
            while pts and pts[0][0]<ts-5_000_000: pts.popleft()
            if len(q5)<4: continue
            bb=max(bids) if bids else f(l1.get("bp"))
            aa=min(asks) if asks else f(l1.get("ap"))
            if bb<=0 or aa<=0: continue
            mid=(bb+aa)/2; spread_bps=(aa-bb)/mid*10000
            old=pts[0][1] if pts else px
            mom=(px/old-1)*100
            d5=(b5-s5)/(b5+s5) if b5+s5 else 0
            d30=(b30-s30)/(b30+s30) if b30+s30 else 0
            depth_b=sum(v for _,v in sorted(bids.items(),reverse=True)[:5])
            depth_a=sum(v for _,v in sorted(asks.items())[:5])
            imb=(depth_b-depth_a)/(depth_b+depth_a) if depth_b+depth_a else 0
            samples.append((ts,px,d5,d30,imb,mom,spread_bps))

    # Evaluate parameter grid on event samples using future sample prices.
    results=[]
    for d5min,d30min,immin,mmin in [(0.12,0.08,0.12,0.025),(0.16,0.10,0.16,0.035),(0.20,0.12,0.20,0.045)]:
      for horizon in (10,20,30,45,60):
       for stop_bps in (6,8,10,12):
        target_bps=stop_bps*2
        vals=[]; wins=0
        for i,s in enumerate(samples[:-1]):
          ts,px,d5,d30,imb,mom,sp=s
          if sp>2.0: continue
          side=1 if d5>=d5min and d30>=d30min and imb>=immin and mom>=mmin else -1 if d5<=-d5min and d30<=-d30min and imb<=-immin and mom<=-mmin else 0
          if not side: continue
          j=i+1
          while j<len(samples) and samples[j][0]-ts<horizon*1_000_000: j+=1
          if j>=len(samples): continue
          future=samples[j][1]; move=(future/px-1)*10000*side
          # Conservative fixed-horizon approximation: clamp to stop/target.
          gross=max(-stop_bps,min(target_bps,move))
          net=gross-COST_BPS
          vals.append(net)
          wins += net>0
        if vals:
          avg=sum(vals)/len(vals); total=sum(vals)
          gross_w=sum(v+COST_BPS for v in vals if v>0)
          gross_l=-sum(v+COST_BPS for v in vals if v<0)
          pf=gross_w/gross_l if gross_l else None
          results.append({"n":len(vals),"win_rate":wins/len(vals),"avg_net_bps":avg,
                          "total_net_bps":total,"profit_factor":pf,
                          "thresholds":[d5min,d30min,immin,mmin],
                          "horizon_s":horizon,"stop_bps":stop_bps,"target_bps":target_bps})
    results.sort(key=lambda x:(x["avg_net_bps"],x["profit_factor"] or -1),reverse=True)
    top=[x for x in results if x["n"]>=30][:20]
    out={"events_read":n,"feature_samples":len(samples),"cost_bps_roundtrip":COST_BPS,
         "minimum_samples_for_candidate":30,"top_candidates":top,
         "warning":"Research approximation; not execution-ready. Uses fixed-horizon exits and no look-ahead-safe orderbook replay beyond sampled events."}
    OUT.write_text(json.dumps(out,indent=2))
    print(json.dumps(out,indent=2))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-events",type=int,default=2000000)
    parser.add_argument("--session-id",default=None,help="explicit immutable gzip session ID")
    parser.add_argument("--archive-dir",type=Path,default=DEFAULT_ARCHIVE_DIR)
    parser.add_argument("--legacy-path",type=Path,default=DEFAULT_LEGACY_PATH)
    args=parser.parse_args()
    run(max_events=args.max_events,session_id=args.session_id,archive_dir=args.archive_dir,legacy_path=args.legacy_path)

if __name__=="__main__": main()
