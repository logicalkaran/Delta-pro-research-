import json,os,time
ROOT=os.path.expanduser("~/btc_fisher_trader")
SRC=ROOT+"/data/live_microstructure_state.json"
OUT=ROOT+"/data/processed/forecast_journal_v1.jsonl"
LAST=ROOT+"/data/processed/forecast_last.json"
def rd(p,d=None):
 try:
  with open(p) as f:return json.load(f)
 except:return d
def price(s):
 o=s.get("order_book",{})
 try:return float(o.get("mid_price",0))
 except:return 0
def forecast():
 s=rd(SRC,{}) or {};w=s.get("windows",{});ob=s.get("order_book",{});p=s.get("price",{})
 def f(x,d=0):
  try:return float(x)
  except:return d
 d5=f(w.get("5",{}).get("delta_pct"));d30=f(w.get("30",{}).get("delta_pct"));d60=f(w.get("60",{}).get("delta_pct"));imb=f(ob.get("imbalance_5"));cvd=f(s.get("cvd_slope_30s"));mom=f(p.get("5",{}).get("return_pct"))
 raw=d5*35+d30*25+d60*15+imb*20+mom*8+(5 if cvd>0 else -5 if cvd<0 else 0)
 direction="UP" if raw>8 else "DOWN" if raw<-8 else "FLAT"
 return {"ts":time.time(),"entry_price":price(s),"direction":direction,"score":raw}
def append(row):
 os.makedirs(os.path.dirname(OUT),exist_ok=True)
 with open(OUT,"a") as f:f.write(json.dumps(row,separators=(",",":"))+"\n")
def main():
 last=rd(LAST,{}) or {};now=time.time()
 if last and now-last.get("ts",0)>=60:
  s=rd(SRC,{}) or {};px=price(s);p0=last.get("entry_price",0)
  if p0>0 and px>0:
   elapsed=now-last["ts"];ret=(px/p0-1)*100
   last["evaluation_price"]=px;last["return_pct"]=ret;last["elapsed_s"]=elapsed
   d=last.get("direction");last["hit"]=((d=="UP" and ret>0) or (d=="DOWN" and ret<0) or (d=="FLAT" and abs(ret)<0.01))
   append(last);last={}
 if not last:
  last=forecast();open(LAST,"w").write(json.dumps(last))
if __name__=="__main__":main()
