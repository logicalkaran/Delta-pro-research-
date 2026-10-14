"""Independent forward cohort for Composite Edge V2. Paper only."""
from pathlib import Path
import json,time,uuid,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from strategy.composite_edge_v2 import rank
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data/live_microstructure_state.json"; CANDLES=ROOT/"data/live_candles.json"
OUT=ROOT/"data/processed/composite_v2_forward.jsonl"; PENDING=ROOT/"data/processed/composite_v2_pending.json"
COST=.0012

def load(p,d):
 try:return json.loads(p.read_text())
 except:return d

def future_price(cs,target):
 best=None
 for c in cs:
  try:
   t=float(c.get("timestamp")); p=float(c.get("close"))
   if t>=target and (best is None or t<best[0]):best=(t,p)
  except:pass
 return best[1] if best else None

def main():
 s=load(STATE,{}); cs=load(CANDLES,[]); pending=load(PENDING,[]); now=time.time()
 if not s or float(s.get("quality",{}).get("fresh_seconds",999))>2:return
 r=rank(cs,s)
 if r:
  pending.append({"id":uuid.uuid4().hex,"issued_at":now,"direction":r.side,"entry":r.entry,"horizon":r.horizon_min,"rank_score":r.rank_score,"confidence":r.confidence,"expected_edge_bps":r.expected_edge_bps,"rr":r.rr,"regime":r.regime,"sweep":r.sweep})
 remain=[]; done=[]
 for x in pending:
  if now-x["issued_at"]<x["horizon"]*60:remain.append(x);continue
  fp=future_price(cs,x["issued_at"]+x["horizon"]*60)
  if fp is None:remain.append(x);continue
  gross=((fp/x["entry"])-1)*100 if x["direction"]=="LONG" else ((x["entry"]/fp)-1)*100
  x.update(exit=fp,gross_return_pct=gross,net_return_pct=gross-COST*100,resolved_at=now)
  done.append(x)
 OUT.parent.mkdir(parents=True,exist_ok=True)
 with OUT.open("a") as f:
  for x in done:f.write(json.dumps(x)+"\n")
 PENDING.write_text(json.dumps(remain))
 print(json.dumps({"new":1 if r else 0,"resolved":len(done),"pending":len(remain),"fresh":float(s.get("quality",{}).get("fresh_seconds",999))}))
if __name__=="__main__":main()
