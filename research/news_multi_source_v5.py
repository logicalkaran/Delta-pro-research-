import hashlib,json,re,time,urllib.request,xml.etree.ElementTree as ET
from pathlib import Path
from difflib import SequenceMatcher
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'data/processed/news_event_state_v5.json'; AUD=ROOT/'data/processed/news_event_audit_v5.jsonl'
FEEDS={'COINDESK':'https://www.coindesk.com/arc/outboundfeeds/rss/','FED_PRESS':'https://www.federalreserve.gov/feeds/press_all.xml','COINTELEGRAPH':'https://cointelegraph.com/rss'}
FAMILIES={'MACRO':['FOMC','FED','RATE','CPI','PPI','PAYROLL','EMPLOYMENT','INFLATION','GDP','TREASURY','YIELD'],'REGULATION':['SEC','CFTC','CLARITY','REGULATION','BAN','SANCTION','LICENSE'],'ETF_FLOWS':['ETF','INFLOW','OUTFLOW','FUND'],'GEOPOLITICAL':['WAR','IRAN','TARIFF','OIL','ATTACK','SANCTION'],'CRYPTO_MARKET':['BITCOIN','BTC','CRYPTO','LIQUIDATION','EXCHANGE','WHale','STABLECOIN'],'CORPORATE':['COINBASE','ROBINHOOD','STRATEGY','MICROSTRATEGY','OKX','BINANCE']}
STOP={'THE','AND','FOR','WHAT','WITH','FROM','THIS','THAT','ITS','HAS','HAVE','ARE','WAS','WERE','OVER','INTO','AFTER','JUST','AS','OF','TO','A','AN','ON','IN','BY','US','U.S'}
def fetch(u):
 q=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0 research-news/1.0','Accept':'application/rss+xml,application/xml,text/xml,*/*'}); return urllib.request.urlopen(q,timeout=10).read()
def parse(data,src):
 root=ET.fromstring(data); out=[]
 for x in root.findall('.//item'):
  def v(k):
   z=x.find(k); return z.text.strip() if z is not None and z.text else ''
  title=v('title'); desc=v('description'); guid=v('guid') or v('link'); pub=v('pubDate'); text=(title+' '+desc).upper()
  if not guid: continue
  try: ts=__import__('email.utils',fromlist=['parsedate_to_datetime']).parsedate_to_datetime(pub).timestamp()
  except: ts=time.time()
  toks={t for t in re.findall(r'[A-Z0-9]{3,}',title.upper()) if t not in STOP}
  fam=[f for f,ks in FAMILIES.items() if any(k.upper() in text for k in ks)]
  out.append({'source':src,'id':guid,'title':title,'published_ts':ts,'tokens':sorted(toks),'families':fam,'hash':hashlib.sha256((src+'|'+guid).encode()).hexdigest()[:20]})
 return out
def sim(a,b):
 sa,sb=set(a['tokens']),set(b['tokens']); jac=len(sa&sb)/max(1,len(sa|sb)); seq=SequenceMatcher(None,a['title'].upper(),b['title'].upper()).ratio(); fam=len(set(a['families'])&set(b['families'])); return max(jac,seq*.75),jac,seq,fam
def main():
 now=time.time(); ev=[]; errors={}
 for src,url in FEEDS.items():
  try: ev+=parse(fetch(url),src)
  except Exception as e: errors[src]=type(e).__name__+': '+str(e)
 ev=list({e['hash']:e for e in ev}.values()); recent=[e for e in ev if 0<=now-e['published_ts']<=86400]; clusters=[]
 for i,a in enumerate(recent):
  for b in recent[i+1:]:
   if a['source']==b['source'] or abs(a['published_ts']-b['published_ts'])>7200: continue
   score,jac,seq,fam=sim(a,b)
   if ((score>=.42 and jac>=.18) or (fam>=1 and len(set(a['tokens'])&set(b['tokens']))>=2 and score>=.25)): clusters.append({'cluster_id':hashlib.sha256('|'.join(sorted([a['hash'],b['hash']])).encode()).hexdigest()[:20],'sources':sorted({a['source'],b['source']}),'event_hashes':[a['hash'],b['hash']],'titles':[a['title'],b['title']],'families':sorted(set(a['families'])|set(b['families'])),'time_delta_sec':abs(a['published_ts']-b['published_ts']),'event_time_ts':max(a['published_ts'],b['published_ts']),'similarity':round(score,3)})
 state={'timestamp':now,'status':'RESEARCH_ONLY','sources_configured':len(FEEDS),'sources_healthy':len(FEEDS)-len(errors),'errors':errors,'recent_events':sorted(recent,key=lambda x:x['published_ts'],reverse=True)[:150],'corroborated_events':clusters[:100],'quorum':{'minimum_distinct_sources':2,'requires_same_event':True,'max_time_delta_sec':7200,'min_similarity':.25,'secondary_rule':'shared_family_plus_two_title_tokens'},'real_orders':False,'fail_closed':True}
 OUT.write_text(json.dumps(state,indent=2)); AUD.open('a').write(json.dumps({'observed_at':now,'sources_healthy':state['sources_healthy'],'corroborated_events':clusters[:100]})+'\n'); print(json.dumps({'sources_healthy':state['sources_healthy'],'events':len(recent),'corroborated_events':len(clusters),'errors':errors,'real_orders':False}))
if __name__=='__main__': main()
