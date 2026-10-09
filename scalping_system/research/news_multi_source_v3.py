"""Multi-source news/event collector. Research-only and fail-closed."""
import json,time,urllib.request,xml.etree.ElementTree as ET,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'data/processed/news_event_state_v3.json'; AUDIT=ROOT/'data/processed/news_event_audit_v3.jsonl'
FEEDS={'COINDESK':'https://www.coindesk.com/arc/outboundfeeds/rss/','FED_PRESS':'https://www.federalreserve.gov/feeds/press_all.xml'}
KEY=('BITCOIN','BTC','CRYPTO','FOMC','FED','INTEREST RATE','CPI','EMPLOYMENT','PAYROLL','INFLATION','SEC','ETF','SANCTION','WAR','TARIFF','OIL')
def fetch(url):
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 BTC-Research/1.0','Accept':'application/rss+xml,application/xml,text/xml,*/*'}); return urllib.request.urlopen(req,timeout=10).read()
def parse(data,src):
 root=ET.fromstring(data); out=[]
 for item in root.findall('.//item'):
  def v(k):
   x=item.find(k); return x.text.strip() if x is not None and x.text else ''
  title=v('title'); desc=v('description'); guid=v('guid') or v('link'); pub=v('pubDate'); text=(title+' '+desc).upper()
  if not guid or not any(k in text for k in KEY): continue
  try: ts=__import__('email.utils',fromlist=['parsedate_to_datetime']).parsedate_to_datetime(pub).timestamp()
  except: ts=time.time()
  out.append({'source':src,'id':guid,'title':title,'published_ts':ts,'keywords':[k for k in KEY if k in text],'hash':hashlib.sha256((src+'|'+guid).encode()).hexdigest()[:20]})
 return out
def main():
 now=time.time(); events=[]; errors={}
 for src,url in FEEDS.items():
  try: events+=parse(fetch(url),src)
  except Exception as e: errors[src]=type(e).__name__+': '+str(e)
 uniq={e['hash']:e for e in events}; events=sorted(uniq.values(),key=lambda x:x['published_ts'],reverse=True); recent=[e for e in events if 0<=now-e['published_ts']<=86400]
 state={'timestamp':now,'status':'RESEARCH_ONLY','sources_configured':len(FEEDS),'sources_healthy':len(FEEDS)-len(errors),'errors':errors,'recent_events':recent[:50],'quorum':{'minimum_distinct_sources':2,'live_orders':False},'fail_closed':True}
 OUT.write_text(json.dumps(state,indent=2));
 with AUDIT.open('a') as f:
  for e in recent[:50]: f.write(json.dumps({'observed_at':now,**e},separators=(',',':'))+'\n')
 print(json.dumps(state,indent=2))
if __name__=='__main__':main()
