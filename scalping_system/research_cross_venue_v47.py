"""V4.7 statistical edge validator + professional signal gate.
Research/paper only. Never submits orders.
"""
import json,math,os,statistics
IN="data/processed/cross_venue_v46_outcomes.jsonl"
OUT="data/processed/cross_venue_v47_stats.json"
MIN_N=30

def main():
 rows=[]
 try:
  for line in open(IN):
   try: rows.append(json.loads(line))
   except: pass
 except FileNotFoundError: pass
 stats={}
 for h in (5,10,30,60):
  key=f"ret_{h}s_bps"; vals=[float(r[key]) for r in rows if key in r]
  if vals:
   wins=sum(v>0 for v in vals); mean=sum(vals)/len(vals)
   gross_win=sum(v for v in vals if v>0); gross_loss=-sum(v for v in vals if v<0)
   stats[str(h)]={"n":len(vals),"win_rate":wins/len(vals),
     "avg_bps":mean,"median_bps":statistics.median(vals),
     "profit_factor":gross_win/gross_loss if gross_loss else None,
     "ready_for_signal":len(vals)>=MIN_N and mean>0 and wins/len(vals)>=0.55}
  else: stats[str(h)]={"n":0,"ready_for_signal":False}
 result={"events":len(rows),"minimum_samples":MIN_N,"horizons":stats,
         "promotion_rule":"No cross-venue feature enters trading decisions until >=30 labeled outcomes at a horizon, positive mean return, >=55% win rate, and PF > 1.2."}
 os.makedirs(os.path.dirname(OUT),exist_ok=True)
 json.dump(result,open(OUT,"w"),indent=2)
 print(json.dumps(result,indent=2))
if __name__=="__main__": main()
