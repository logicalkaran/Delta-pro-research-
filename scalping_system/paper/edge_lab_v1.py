import json,os,time,sys
ROOT=os.path.expanduser("~/btc_fisher_trader");sys.path.insert(0,ROOT)
from strategy.pro_scalper_v4 import cost_model
SRC=ROOT+"/data/live_microstructure_state.json"; OUT=ROOT+"/data/processed/edge_lab_v1.jsonl"; PEND=ROOT+"/data/processed/edge_lab_pending_v1.json"; SUM=ROOT+"/data/processed/edge_lab_summary_v1.json"
def rd(p,d=None):
 try:
  with open(p) as f:return json.load(f)
 except:return d
def f(x,d=0):
 try:return float(x)
 except:return d
def price(s):
 try:return float(s["order_book"]["mid_price"])
 except:return 0
def hypotheses(s,fd=None):
 w=s.get("windows",{});ob=s.get("order_book",{});p=s.get("price",{})
 d5=f(w.get("5",{}).get("delta_pct"));d30=f(w.get("30",{}).get("delta_pct"));d60=f(w.get("60",{}).get("delta_pct"))
 imb=f(ob.get("imbalance_5"));cvd=f(s.get("cvd_slope_30s"));mom=f(p.get("5",{}).get("return_pct"))
 buy=f(w.get("30",{}).get("buy_volume"));sell=f(w.get("30",{}).get("sell_volume"));r30=abs(f(p.get("30",{}).get("return_pct")))*100
 flow_dir="UP" if d30>.08 and d5>.08 and cvd>0 else "DOWN" if d30<-.08 and d5<-.08 and cvd<0 else "FLAT"
 h={}
 h["flow_continuation"]=flow_dir
 absorb=(abs(buy-sell)/max(1,buy+sell)>.20 and r30<.04)
 h["absorption_reversal"]="DOWN" if absorb and buy>sell else "UP" if absorb and sell>buy else "FLAT"
 aligned=(d30>.08 and imb>.12 and cvd>0) or (d30<-.08 and imb<-.12 and cvd<0)
 cross=fd if fd in ("UP","DOWN") else "FLAT"
 h["cross_venue_confirmation"]=cross if aligned else "FLAT"
 combo=flow_dir if flow_dir==fd and flow_dir in ("UP","DOWN") and aligned else "FLAT"
 h["flow_ai_cost_filter"]=combo
 return h
def main():
 s=rd(SRC,{}) or {}; now=time.time();px=price(s)
 if px<=0:return
 pend=rd(PEND,[]) or [];keep=[];done=[]
 for r in pend:
  if now-r["ts"]<r["horizon_s"]:keep.append(r);continue
  ret=(px/r["entry_price"]-1)*10000
  r.update(resolved_ts=now,resolved_price=px,return_bps=round(ret,4),hit=int((r["direction"]=="UP" and ret>0) or (r["direction"]=="DOWN" and ret<0)))
  done.append(r)
 if done:
  os.makedirs(os.path.dirname(OUT),exist_ok=True)
  with open(OUT,"a") as x:
   for r in done:x.write(json.dumps(r,separators=(",",":"))+"\n")
 last=rd(PEND+".last",0)
 if now-f(last)>=10:
  fd=rd(ROOT+"/data/processed/forecast_last.json",{}).get("direction")
  hs=hypotheses(s,fd)
  spread=f(s.get("order_book",{}).get("spread"))/max(px,1)*10000
  for name,d in hs.items():
   if d not in ("UP","DOWN"):continue
   c=cost_model(0,spread_bps=spread);keep.append({"ts":now,"horizon_s":30,"entry_price":px,"strategy":name,"direction":d,"cost_bps":round(c["total_cost_bps"],3),"paper_only":True,"order_submission":False})
  with open(PEND+".last","w") as x:x.write(str(now))
 os.makedirs(os.path.dirname(PEND),exist_ok=True)
 with open(PEND+".tmp","w") as x:json.dump(keep,x,separators=(",",":"))
 os.replace(PEND+".tmp",PEND)
 rows=[]
 try:
  with open(OUT) as x:rows=[json.loads(z) for z in x if z.strip()]
 except:pass
 summary={"updated_ts":now,"status":"UNVALIDATED","paper_only":True,"order_submission":False,"opportunities":{},"strategies":{}}
 for name in ("flow_continuation","absorption_reversal","cross_venue_confirmation","flow_ai_cost_filter"):
  a=[r for r in rows if r.get("strategy")==name]
  wins=[r for r in a if r.get("hit")==1]
  rets=[f(r.get("return_bps")) for r in a]
  summary["strategies"][name]={"n":len(a),"win_rate":round(len(wins)/len(a),4) if a else None,"avg_gross_bps":round(sum(rets)/len(rets),4) if rets else None,"avg_net_bps":round(sum(f(r.get("return_bps"))-f(r.get("cost_bps")) for r in a)/len(a),4) if a else None}
 summary["opportunities"]={"flow_continuation":hs.get("flow_continuation"),"absorption_reversal":hs.get("absorption_reversal"),"cross_venue_confirmation":hs.get("cross_venue_confirmation"),"flow_ai_cost_filter":hs.get("flow_ai_cost_filter")}
 for name,st in summary["strategies"].items():
  a=[r for r in rows if r.get("strategy")==name and r.get("hit") is not None]
  if a:
   buckets={"positive":sum(f(r.get("return_bps"))>0 for r in a),"negative":sum(f(r.get("return_bps"))<0 for r in a),"flat":sum(f(r.get("return_bps"))==0 for r in a)}
   st["return_buckets"]=buckets
 with open(SUM,"w") as x:json.dump(summary,x,separators=(",",":"))
if __name__=="__main__":main()
