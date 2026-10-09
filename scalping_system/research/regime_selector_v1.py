import json,bisect,statistics
from pathlib import Path
P=Path('data/raw/delta_btc_raw.jsonl'); rows=[]; l1={}
def f(x):
 try:return float(x)
 except:return 0.0
with P.open() as fh:
 for line in fh:
  try:m=json.loads(line);m=m.get('message',m)
  except:continue
  if m.get('type')=='ob_l1':l1=m;continue
  if m.get('type')!='trades':continue
  ts=int(m.get('ts') or m.get('t') or 0);b=f(l1.get('bp'));a=f(l1.get('ap'));px=f(m.get('p'));q=f(m.get('q') or m.get('size') or m.get('s'))
  if ts and b and a and px:rows.append((ts,b,a,px,q))
rows.sort(key=lambda x:x[0]); T=[x[0] for x in rows];n=len(rows);events=[]
for i,r in enumerate(rows):
 ts,b,a,px,q=r;j30=bisect.bisect_left(T,ts-30_000_000,0,i);j60=bisect.bisect_left(T,ts-60_000_000,0,i)
 if i-j30<3 or i-j60<5:continue
 mid=(b+a)/2;spr=(a-b)/mid*10000;recent=rows[j30:i];signed=sum((1 if x[3]>=mid else -1)*x[4] for x in recent);vol=sum(x[4] for x in recent) or 1;delta=signed/vol;mom=(px-rows[j30][3])/rows[j30][3]*10000;p60=[x[3] for x in rows[j60:i:max(1,(i-j60)//20 or 1)]];volat=(max(p60)-min(p60))/px*10000 if p60 else 0
 j120=bisect.bisect_left(T,ts+120_000_000);j300=bisect.bisect_left(T,ts+300_000_000)
 if j120<n and j300<n:
  x120=rows[j120];x300=rows[j300];events.append((ts,delta,mom,volat,spr,(x120[1]/a-1)*10000,(b/x120[2]-1)*10000,(x300[1]/a-1)*10000,(b/x300[2]-1)*10000))
configs=[('FLOW',.25,.5),('FLOW_EXTREME',.40,1.0),('MOM',.20,1.5),('MOM_EXTREME',.35,3.0)];res=[]
for name,dth,mth in configs:
 for side in ('LONG','SHORT'):
  for idx,h in ((5,120),(7,300)):
   vals=[e[idx] for e in events if e[4]<=5 and ((e[1]>=dth and e[2]>=mth) if side=='LONG' else (e[1]<=-dth and e[2]<=-mth))]
   if vals:res.append({'regime':name,'side':side,'horizon_s':h,'n':len(vals),'win_rate':sum(x>0 for x in vals)/len(vals),'avg_gross_bps':sum(vals)/len(vals),'median_gross_bps':statistics.median(vals),'p90':sorted(vals)[int(.9*len(vals))]})
res.sort(key=lambda x:x['avg_gross_bps'],reverse=True);out={'status':'RESEARCH_ONLY','samples':len(events),'cost_reference_bps':11.8,'selector':'strong signed flow + momentum + spread filter','results':res};Path('data/processed/regime_selector_v1.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
