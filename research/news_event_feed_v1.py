"""News/event intelligence layer. Research/shadow only; never submits orders."""
import json,time,urllib.request,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'data/processed/news_event_state.json'
SOURCES={
 'BLS_EMPLOYMENT':'https://www.bls.gov/schedule/news_release/empsit.htm',
 'BLS_CPI':'https://www.bls.gov/schedule/news_release/cpi.htm',
 'BLS_CALENDAR':'https://www.bls.gov/schedule/news_release/bls.ics',
 'FED':'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm',
}
MAJOR={'CPI','EMPLOYMENT','FOMC','FEDERAL RESERVE','PPI','GDP','NFP','JOBS','INFLATION','RATE DECISION','INTEREST RATE','POWELL','WAR','SANCTIONS','ETF','BITCOIN','CRYPTO'}

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'BTCResearchNewsFeed/1.0'})
    with urllib.request.urlopen(req,timeout=10) as r:return r.read()

def classify(text):
    u=text.upper(); hits=[x for x in MAJOR if x in u]
    return hits

def main():
    events=[]; errors={}
    for name,url in SOURCES.items():
        try:
            data=fetch(url); text=data.decode('utf-8','ignore'); hits=classify(text)
            events.append({'source':name,'url':url,'fetched_at':time.time(),'bytes':len(data),'major_keywords':hits,'available':True})
        except Exception as e: errors[name]=str(e)
    state={'timestamp':time.time(),'status':'RESEARCH_ONLY','sources':events,'errors':errors,
           'news_execution':{'enabled':False,'certainty_required':1.0,'real_orders':False,
             'policy':'Never trade solely because of news. Require source confirmation + event classification + timestamp integrity + microstructure momentum confirmation + execution safety gate.'}}
    OUT.write_text(json.dumps(state,indent=2)); print(json.dumps(state,indent=2))
if __name__=='__main__':main()
