"""V4.6 event outcome labeling. Research only."""
import json,os
IN="data/processed/cross_venue_btc_v43.jsonl"; OUT="data/processed/cross_venue_v46_outcomes.jsonl"
H=(5,10,30,60); TH=2.0
def load():
 r=[]
 try:
  for line in open(IN):
   try:
    x=json.loads(line)
    if x.get("comparison",{}).get("valid") and x.get("venues_ok",0)>=2:r.append(x)
   except:pass
 except FileNotFoundError:pass
 return r
def price(r,v="delta"):
 for x in r.get("comparison",{}).get("venues",[]):
  if x["venue"]==v:return float(x["price"])
def main():
 rows=load(); events=[]; active=None
 for r in rows:
  e=r.get("edge_v42",{}); s=float(e.get("spread_bps") or 0)
  if s>=TH and e.get("leader") and e.get("lagger"):
   key=(e["leader"],e["lagger"])
   if active is None or active["key"]!=key:
    if active:events.append(active)
    active={"key":key,"start":r["epoch_ms"],"row":r,"max_spread":s}
   else:active["max_spread"]=max(active["max_spread"],s)
  elif active:
   active["end"]=r["epoch_ms"];events.append(active);active=None
 if active:events.append(active)
 out=[]
 for e in events:
  if "end" not in e:continue
  base=price(e["row"]); item={"start":e["start"],"end":e["end"],"duration_s":(e["end"]-e["start"])/1000,"leader":e["key"][0],"lagger":e["key"][1],"max_spread_bps":e["max_spread"]}
  for h in H:
   target=e["end"]+h*1000; best=None;dist=10**18
   for r in rows:
    dd=abs(r["epoch_ms"]-target)
    if dd<dist and r["epoch_ms"]>=e["end"]:best=r;dist=dd
   if best and dist<=3000:
    ret=(price(best)/base-1)*10000
    item[f"ret_{h}s_bps"]=ret
    item[f"reversion_{h}s"]=ret*(1 if e["key"][1]=="delta" else 0)
  out.append(item)
 os.makedirs(os.path.dirname(OUT),exist_ok=True)
 with open(OUT,"w") as f:
  for x in out:f.write(json.dumps(x,separators=(",",":"))+"\n")
 print(json.dumps({"samples":len(rows),"completed_events":len(out),"outcome_file":OUT,"labeled_horizons":H},indent=2))
if __name__=="__main__":main()
