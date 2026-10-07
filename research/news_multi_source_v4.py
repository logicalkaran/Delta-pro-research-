"""Event-corroborating multi-source news collector. Research-only, fail-closed.

A quorum is valid only when >=2 independent sources publish semantically similar relevant
headlines inside the same time window. Feed health alone never counts as corroboration.
"""
import hashlib,json,re,time,urllib.request,xml.etree.ElementTree as ET
from pathlib import Path
from difflib import SequenceMatcher
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/processed/news_event_state_v4.json'
AUDIT=ROOT/'data/processed/news_event_audit_v4.jsonl'
FEEDS={'COINDESK':'https://www.coindesk.com/arc/outboundfeeds/rss/','FED_PRESS':'https://www.federalreserve.gov/feeds/press_all.xml'}
KEY=('BITCOIN','BTC','CRYPTO','FOMC','FED','INTEREST RATE','CPI','EMPLOYMENT','PAYROLL','INFLATION','SEC','ETF','SANCTION','WAR','TARIFF','OIL')
STOP={'THE','AND','FOR','WHAT','WITH','FROM','THIS','THAT','ITS','HAS','HAVE','ARE','WAS','WERE','OVER','INTO','AFTER','JUST','AS','OF','TO','A','AN','ON','IN','BY','US','U.S'}
def fetch(url):
 r=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 BTC-Research/1.0','Accept':'application/rss+xml,application/xml,text/xml,*/*'}); return urllib.request.urlopen(r,timeout=10).read()
def tokens(title):
 return {x for x in re.findall(r'[A-Z0-9]{3,}',title.upper()) if x not in STOP}
def parse(data,src):
 root=ET.fromstring(data); out=[]
 for item in root.findall('.//item'):
  def v(k):
   x=item.find(k); return x.text.strip() if x is not None and x.text else ''
  title=v('title'); desc=v('description'); guid=v('guid') or v('link'); pub=v('pubDate'); text=(title+' '+desc).upper()
  if not guid or not any(k in text for k in KEY): continue
  try: ts=__import__('email.utils',fromlist=['parsedate_to_datetime']).parsedate_to_datetime(pub).timestamp()
  except: ts=time.time()
  out.append({'source':src,'id':guid,'title':title,'published_ts':ts,'keywords':[k for k in KEY if k in text],'tokens':sorted(tokens(title)),'hash':hashlib.sha256((src+'|'+guid).encode()).hexdigest()[:20]})
 return out
def similarity(a,b):
 sa,sb=set(a['tokens']),set(b['tokens']); jac=len(sa&sb)/max(1,len(sa|sb)); seq=SequenceMatcher(None,a['title'].upper(),b['title'].upper()).ratio(); key=len(set(a['keywords'])&set(b['keywords']))
 return max(jac,seq*0.75),jac,seq,key
def main():
 now=time.time(); events=[]; errors={}
 for src,url in FEEDS.items():
  try: events+=parse(fetch(url),src)
  except Exception as e: errors[src]=type(e).__name__+': '+str(e)
 uniq={e['hash']:e for e in events}; events=sorted(uniq.values(),key=lambda x:x['published_ts'],reverse=True); recent=[e for e in events if 0<=now-e['published_ts']<=86400]
 clusters=[]; used=set()
 for i,a in enumerate(recent):
  for b in recent[i+1:]:
   if a['source']==b['source'] or abs(a['published_ts']-b['published_ts'])>1800: continue
   score,jac,seq,key=similarity(a,b)
   if score>=0.42 and (jac>=0.25 or key>=1):
    cid=hashlib.sha256('|'.join(sorted([a['hash'],b['hash']])).encode()).hexdigest()[:20]
    clusters.append({'cluster_id':cid,'sources':sorted({a['source'],b['source']}),'event_hashes':[a['hash'],b['hash']],'titles':[a['title'],b['title']],'time_delta_sec':abs(a['published_ts']-b['published_ts']),'similarity':round(score,3),'keyword_overlap':key})
    used.update([a['hash'],b['hash']])
 corroborated=[c for c in clusters if len(c['sources'])>=2]
 state={'timestamp':now,'status':'RESEARCH_ONLY','sources_configured':len(FEEDS),'sources_healthy':len(FEEDS)-len(errors),'errors':errors,'recent_events':recent[:100],'corroborated_events':corroborated[:50],'quorum':{'minimum_distinct_sources':2,'requires_same_event':True,'max_time_delta_sec':1800,'min_similarity':0.42,'live_orders':False},'fail_closed':True}
 OUT.write_text(json.dumps(state,indent=2))
 with AUDIT.open('a') as f: f.write(json.dumps({'observed_at':now,'corroborated_events':corroborated[:50],'sources_healthy':state['sources_healthy']},separators=(',',':'))+'\n')
 print(json.dumps({'sources_healthy':state['sources_healthy'],'events':len(recent),'corroborated_events':len(corroborated),'errors':errors,'live_orders':False},indent=2))
if __name__=='__main__': main()
