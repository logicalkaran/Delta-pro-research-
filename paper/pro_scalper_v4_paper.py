import json,os,time,sys
ROOT=os.path.expanduser("~/btc_fisher_trader");sys.path.insert(0,ROOT)
from strategy.pro_scalper_v4 import evaluate
SRC=ROOT+"/data/live_microstructure_state.json";OUT=ROOT+"/data/processed/pro_scalper_v4_paper.jsonl";SUM=ROOT+"/data/processed/pro_scalper_v4_summary.json"
def rd(p,d={}):
 try:
  with open(p) as f:return json.load(f)
 except:return d
def main():
 s=rd(SRC,{}) or {}
 # Forecast is intentionally read-only; V4 cannot submit orders.
 fp=rd(ROOT+"/data/processed/forecast_last.json",{}) or {}
 fd=fp.get("direction")
 f={"horizon_30s":{"direction":fd}} if fd else None
 d=evaluate(s,f)
 d.update({"ts":time.time(),"mid_price":s.get("order_book",{}).get("mid_price"),
           "forecast_direction":fd,"mode":"PAPER"})
 os.makedirs(os.path.dirname(OUT),exist_ok=True)
 with open(OUT,"a") as x:x.write(json.dumps(d,separators=(",",":"))+"\n")
 rows=[]
 try:
  with open(OUT) as x: rows=[json.loads(z) for z in x if z.strip()]
 except:pass
 acts=[r for r in rows if r.get("action") in ("LONG","SHORT")]
 summary={"updated_ts":time.time(),"observations":len(rows),"paper_signals":len(acts),
          "long":sum(r["action"]=="LONG" for r in acts),"short":sum(r["action"]=="SHORT" for r in acts),
          "no_trade":sum(r["action"]=="NO_TRADE" for r in rows),
          "avg_net_edge_bps":round(sum(r.get("net_edge_bps",0) for r in rows)/len(rows),4) if rows else 0,
          "status":"RESEARCH_ONLY","paper_only":True,"order_submission":False}
 with open(SUM,"w") as x:json.dump(summary,x,separators=(",",":"))
if __name__=="__main__":main()
