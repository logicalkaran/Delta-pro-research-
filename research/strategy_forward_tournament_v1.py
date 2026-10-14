"""Forward BTC strategy tournament. Frozen signals, future outcomes, paper only."""
from pathlib import Path
import json,time,uuid,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from strategy.composite_edge_v1 import select as select_composite
from strategy.composite_edge_v2 import rank as rank_composite
ROOT=Path(__file__).resolve().parents[1]; STATE=ROOT/"data/live_microstructure_state.json"; OUT=ROOT/"data/processed/strategy_forward_tournament_v1.jsonl"; PENDING=ROOT/"data/processed/strategy_forward_pending_v1.json"
COST=.0012; INTERVAL=10; HORIZONS=(1,2,3,5)
def load(p,default):
 try:return json.loads(p.read_text())
 except:return default
def px_after(cs,target):
 best=None
 for c in cs:
  try:
   t=float(c.get("timestamp")); p=float(c.get("close"))
   if t>=target and (best is None or t<best[0]):best=(t,p)
  except:pass
 return best[1] if best else None
def regime(r,imb): return "HIGH_VOL" if abs(r)>=.08 else ("LOW_VOL" if abs(r)<.02 else "NORMAL_VOL")
def signals(s,cs):
 ob=s.get("order_book",{}); d5=float(s.get("windows",{}).get("5",{}).get("delta_pct",0)); d30=float(s.get("windows",{}).get("30",{}).get("delta_pct",0)); imb=float(ob.get("imbalance_5",0)); r=float(s.get("price",{}).get("5",{}).get("return_pct",0)); p=float(ob.get("mid_price",0))
 direction="LONG" if d5>0 else "SHORT" if d5<0 else "NONE"; rg=regime(r,imb); q=[]
 comp=select_composite(cs,s)
 if comp is not None: q += ["COMPOSITE_EDGE"]
 ranked=rank_composite(cs,s)
 if ranked is not None: q += ["COMPOSITE_EDGE_V2"]
 ranked_meta=ranked.to_dict() if ranked is not None else None
 # Liquidity Sweep / Stop-Run Reversal. Research-only.
 try:
  closed=cs[-21:-1] if len(cs)>21 else cs[:-1]
  if len(closed)>=10:
   recent_high=max(float(c["high"]) for c in closed[-20:]); recent_low=min(float(c["low"]) for c in closed[-20:])
   if p <= recent_low*1.00015 and d5>0 and imb>0.05: q += ["LIQUIDITY_SWEEP"]
   elif p >= recent_high*0.99985 and d5<0 and imb<-0.05: q += ["LIQUIDITY_SWEEP"]
 except (KeyError,TypeError,ValueError): pass
 if abs(d5)>=.10:q+=["ABSORPTION"]
 if abs(d5)>=.20 and abs(r)>=.03:q+=["BREAKOUT_FLOW"]
 if abs(d5)>=.10 and abs(r)<.03 and abs(imb)>=.08:q+=["FAILED_BREAKOUT"]
 if abs(d5)>=.12 and ((d5>0 and d30>0) or (d5<0 and d30<0)):q+=["FLOW_CONTINUATION"]
 if abs(imb)>=.12:q+=["ORDERBOOK_IMBALANCE"]
 if abs(r)>=.05 and abs(d5)>=.10:q+=["MOMENTUM"]
 if abs(d5)>=.12 and abs(imb)>=.08 and ((d5>0 and d30>=0) or (d5<0 and d30<=0)):q+=["MULTI_CONFLUENCE"]
 # Additional forward-test families using only fields actually present in the live snapshot.
 # These are research labels, not production strategy changes.
 if abs(d5)>=.10 and abs(r)<.02 and ((d5>0 and imb<-.08) or (d5<0 and imb>.08)):q+=["FLOW_MEAN_REVERSION"]
 if abs(r)>=.08 and abs(d5)>=.12:q+=["VOLATILITY_EXPANSION"]
 if abs(d5)>=.12 and abs(d30)<.05:q+=["DELTA_DIVERGENCE"]
 return [{"id":uuid.uuid4().hex,"strategy":x,"direction":direction,"entry":p,"issued_at":time.time(),"regime":rg,"delta5":d5,"delta30":d30,"imbalance":imb,"return5":r,"horizon":h,"rank_score":(ranked_meta or {}).get("rank_score"),"expected_edge_bps":(ranked_meta or {}).get("expected_edge_bps")} for x in q for h in HORIZONS if direction!="NONE" and p>0]
def main():
 s=load(STATE,{}); cs=load(ROOT/"data/live_candles.json",[]); pending=load(PENDING,[]); now=time.time(); fresh=float(s.get("quality",{}).get("fresh_seconds",999))
 if fresh>2 or not s:return
 for x in signals(s,cs):pending.append(x)
 remaining=[]; exits=[]
 for x in pending:
  if now-x["issued_at"]<x["horizon"]*60:remaining.append(x);continue
  fp=px_after(cs,x["issued_at"]+x["horizon"]*60)
  if fp is None:remaining.append(x);continue
  gross=((fp/x["entry"])-1)*100 if x["direction"]=="LONG" else ((x["entry"]/fp)-1)*100
  x.update({"exit":fp,"gross_return_pct":gross,"net_return_pct":gross-COST*100,"resolved_at":now,"cost_pct":COST*100})
  exits.append(x)
 OUT.parent.mkdir(parents=True,exist_ok=True)
 with OUT.open("a") as f:
  for x in exits:f.write(json.dumps(x)+"\n")
 PENDING.write_text(json.dumps(remaining))
 print(json.dumps({"new_signals":len(signals(s,cs)),"resolved":len(exits),"pending":len(remaining),"fresh":fresh}))
if __name__=="__main__":main()
