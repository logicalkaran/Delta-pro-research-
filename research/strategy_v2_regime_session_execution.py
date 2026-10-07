#!/usr/bin/env python3
"""Second-generation research-only BTC regime/session/execution optimizer.
No exchange/order imports; never enables live execution.
"""
import json,bisect,math,statistics
from pathlib import Path
from collections import defaultdict

RAW=Path("data/raw/delta_btc_raw.jsonl")
OUT=Path("data/processed/strategy_v2_regime_session_execution.json")
REPORT=Path("research/STRATEGY_V2_REPORT.md")
TAKER=11.8
rows=[]; bp=ap=0.0
with RAW.open() as fh:
    for line in fh:
        try:m=json.loads(line);m=m.get("message",m)
        except:continue
        if m.get("type")=="ob_l1":
            bp=float(m.get("bp",0));ap=float(m.get("ap",0));continue
        if m.get("type")=="trades" and bp and ap:
            ts=int(m.get("ts",0));p=float(m.get("p",0));q=float(m.get("s",m.get("size",1)))
            if ts and p and q:rows.append((ts,bp,ap,p,q))
rows.sort();T=[x[0] for x in rows];N=len(rows)

E=[]
for i,(ts,bid,ask,p,q) in enumerate(rows):
    j5=bisect.bisect_left(T,ts-5_000_000,0,i);j10=bisect.bisect_left(T,ts-10_000_000,0,i)
    j30=bisect.bisect_left(T,ts-30_000_000,0,i);j60=bisect.bisect_left(T,ts-60_000_000,0,i)
    if i-j30<3 or i-j60<5:continue
    mid=(bid+ask)/2; spr=(ask-bid)/mid*10000
    def flow(j):
        r=rows[j:i];v=sum(x[4] for x in r) or 1
        return sum((1 if x[3]>=mid else -1)*x[4] for x in r)/v
    f5=flow(j5) if i-j5>=2 else 0
    f10=flow(j10) if i-j10>=2 else 0
    f30=flow(j30);f60=flow(j60)
    r30=rows[j30][3];r60=rows[j60][3]
    m30=(p-r30)/r30*10000;m60=(p-r60)/r60*10000
    accel=f5-f30
    sample=rows[j60:i:max(1,(i-j60)//20 or 1)]
    mp=sum(x[3] for x in sample)/len(sample)
    vol=math.sqrt(sum((((x[3]-mp)/mp*10000)**2) for x in sample)/len(sample))
    E.append({"i":i,"ts":ts,"bid":bid,"ask":ask,"spr":spr,"f5":f5,"f10":f10,"f30":f30,"f60":f60,
              "m30":m30,"m60":m60,"acc":accel,"vol":vol,"hour":(ts//3600000000)%24})
for e in E:
    for h in (30,60,120,300,600):
        e["j"+str(h)]=bisect.bisect_left(T,e["ts"]+h*1_000_000)

def sess(h):
    # UTC bucket mapped approximately to IST; 30-minute precision unavailable from hourly grouping.
    x=(h+5)%24
    return "IST_00_06" if x<6 else "IST_06_12" if x<12 else "IST_12_18" if x<18 else "IST_18_24"

def reg(e):
    if e["spr"]>5:return "WIDE"
    if e["vol"]>=8:return "HIGH_VOL"
    if e["m60"]>=2 and e["f60"]>=.15:return "TREND_UP"
    if e["m60"]<=-2 and e["f60"]<=-.15:return "TREND_DOWN"
    if abs(e["m60"])<1.5 and abs(e["f60"])<.15:return "RANGE"
    if abs(e["acc"])>=.20:return "FLOW_SHIFT"
    return "MIXED"

# Candidate rules are parameterized, not one-off strategies.
RULES=[]
for flow in (.20,.30,.35,.40,.45):
 for mom in (1.0,2.0,3.0):
  for side in (1,-1):
   RULES.append((f"FLOW_MOM_{flow}_{mom}_{'L' if side==1 else 'S'}",flow,mom,side))
# Reversal/absorption family.
for flow in (.10,.20,.30):
 for mom in (2.0,3.0,4.0):
  RULES += [(f"ABSREV_{flow}_{mom}_L",flow,mom,1),(f"ABSREV_{flow}_{mom}_S",flow,mom,-1)]

def signal(e,rule):
 name,flow,mom,side=rule
 if e["spr"]>5:return 0
 if name.startswith("FLOW_MOM"):
  ok=(e["f30"]>=flow and e["m30"]>=mom) if side==1 else (e["f30"]<=-flow and e["m30"]<=-mom)
  return side if ok else 0
 # absorption reversal: strong price move against flow.
 ok=(e["m30"]>=mom and e["f30"]<=-flow) if side==-1 else (e["m30"]<=-mom and e["f30"]>=flow)
 return side if ok else 0

def trade(e,side,h,stop,target,model,penalty=0):
 j=e["j"+str(h)]
 if j>=N:return None
 if model=="maker":
  entry=e["bid"] if side==1 else e["ask"]
 else:
  entry=e["ask"] if side==1 else e["bid"]
 stop_px=entry*(1-stop/10000) if side==1 else entry*(1+stop/10000)
 target_px=entry*(1+target/10000) if side==1 else entry*(1-target/10000)
 exitpx=rows[j][1] if side==1 else rows[j][2]; reason="TIME"
 for k in range(e["i"]+1,j+1):
  b,a=rows[k][1],rows[k][2]
  if side==1:
   if b<=stop_px:exitpx=b;reason="STOP";break
   if b>=target_px:exitpx=b;reason="TARGET";break
  else:
   if a>=stop_px:exitpx=a;reason="STOP";break
   if a<=target_px:exitpx=a;reason="TARGET";break
 gross=((exitpx-entry)/entry*10000)*side
 # maker requires an explicit fill assumption; penalties model adverse selection.
 net=gross-(penalty if model=="maker" else TAKER)
 return net,reason

def summ(xs):
 if not xs:return {"n":0}
 vals=[x[0] for x in xs];w=[x for x in vals if x>0];l=[-x for x in vals if x<0]
 eq=pk=dd=0
 for x in vals:eq+=x;pk=max(pk,eq);dd=max(dd,pk-eq)
 return {"n":len(vals),"win_rate":len(w)/len(vals),"avg_net_bps":sum(vals)/len(vals),
         "profit_factor":sum(w)/sum(l) if l else None,"max_drawdown_bps":dd,
         "avg_winner_bps":sum(w)/len(w) if w else 0,"avg_loser_bps":-sum(l)/len(l) if l else 0}

# Optimize only on train. Session/regime are evaluated separately after selection.
n=len(E);a=int(n*.6);b=int(n*.8)
candidates=[]
for rule in RULES:
 for h in (30,60,120,300,600):
  for stop,target in ((5,10),(8,16),(10,20)):
   for model in ("taker","maker"):
    for pen in ((0,1,2,3) if model=="maker" else (0,)):
     splits={}
     for lo,hi,label in ((0,a,"train"),(a,b,"validation"),(b,n,"test")):
      xs=[];last=-10**30
      for e in E[lo:hi]:
       s=signal(e,rule)
       if not s or e["ts"]-last<60_000_000:continue
       r=trade(e,s,h,stop,target,model,pen)
       if r:xs.append(r);last=e["ts"]
      splits[label]=summ(xs)
     tr=splits["train"]
     if tr["n"]>=20:
      candidates.append({"rule":rule[0],"flow":rule[1],"momentum":rule[2],"side":rule[3],"horizon_s":h,
       "stop_bps":stop,"target_bps":target,"model":model,"adverse_penalty_bps":pen,"splits":splits})
# Favor net expectancy but penalize low PF and small samples.
def rank(c):
 t=c["splits"]["train"];pf=t.get("profit_factor") or 0
 return t["avg_net_bps"] + min(pf,2)*0.25 + math.log1p(t["n"])*0.05
candidates.sort(key=rank,reverse=True)
top=candidates[:20]

matrix=defaultdict(lambda:{"n":0,"net":0,"wins":0})
for c in top[:10]:
 for e in E:
  # identify rule parameters from stored fields
  rule=(c["rule"],c["flow"],c["momentum"],c["side"]);s=signal(e,rule)
  if not s:continue
  r=trade(e,s,c["horizon_s"],c["stop_bps"],c["target_bps"],c["model"],c["adverse_penalty_bps"])
  if not r:continue
  k=(c["rule"],reg(e),sess(e["hour"]),c["model"],c["horizon_s"]);matrix[k]["n"]+=1;matrix[k]["net"]+=r[0];matrix[k]["wins"]+=r[0]>0

mat={}
for k,v in matrix.items():
 n0=v["n"];mat["|".join(map(str,k))]={"n":n0,"avg_net_bps":v["net"]/n0 if n0 else 0,"win_rate":v["wins"]/n0 if n0 else 0}

out={"status":"RESEARCH_ONLY","raw_trade_events":N,"feature_samples":len(E),
 "taker_round_trip_bps":TAKER,"candidate_configurations":len(candidates),
 "top_train_ranked":top,"regime_session_execution_matrix":mat,
 "promotion_status":"BLOCKED","note":"Maker touch fills are hypothetical. Queue position, cancellation and missed-fill probability are not directly observable from this tape."}
OUT.write_text(json.dumps(out,indent=2))
lines=["# Strategy V2 — Regime × Session × Execution","",f"Status: RESEARCH_ONLY","Raw events: {N}","Feature samples: {len(E)}",f"Candidate configurations: {len(candidates)}", "", "## Top candidates"]
for c in top:
 t=c["splits"]["train"];v=c["splits"]["validation"];te=c["splits"]["test"]
 lines.append(f"- {c['rule']} | {c['model']} pen={c['adverse_penalty_bps']} | {c['horizon_s']}s {c['stop_bps']}/{c['target_bps']} | train n={t['n']} avg={t['avg_net_bps']:.3f} PF={t['profit_factor']} | val n={v['n']} avg={v['avg_net_bps']:.3f} PF={v['profit_factor']} | test n={te['n']} avg={te['avg_net_bps']:.3f} PF={te['profit_factor']}")
lines += ["","## Safety","No production execution was modified. No live orders were submitted. Promotion remains blocked. Session/regime matrices are diagnostic and not independent validation."]
REPORT.write_text("\n".join(lines))
print(json.dumps({"status":"RESEARCH_ONLY","events":N,"samples":len(E),"candidates":len(candidates),"top":[{"rule":c["rule"],"model":c["model"],"penalty":c["adverse_penalty_bps"],"h":c["horizon_s"],"train":c["splits"]["train"],"validation":c["splits"]["validation"],"test":c["splits"]["test"]} for c in top[:10]]},indent=2))
