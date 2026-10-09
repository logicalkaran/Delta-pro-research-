"""Hardened official-event feed collector. Research/shadow only."""
from __future__ import annotations
import hashlib,json,time,urllib.request,xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/processed/news_event_state_v2.json"
AUDIT=ROOT/"data/processed/news_event_events_v2.jsonl"

FEEDS={
    "BLS_EMPLOYMENT":"https://www.bls.gov/feed/empsit.rss",
    "BLS_CPI":"https://www.bls.gov/feed/cpi.rss",
    "BLS_PPI":"https://www.bls.gov/feed/ppi.rss",
    "BLS_JOLTS":"https://www.bls.gov/feed/jolts.rss",
}
KEYWORDS=("CPI","EMPLOYMENT","PAYROLL","UNEMPLOYMENT","FOMC","FEDERAL RESERVE","INTEREST RATE","RATE DECISION","PPI","JOLTS","INFLATION")
HEADERS={
    "User-Agent":"Mozilla/5.0 (Android 16; Mobile) AppleWebKit/537.36 Chrome/140.0 Mobile Safari/537.36 BTCResearch/1.1",
    "Accept":"application/rss+xml,application/xml,text/xml,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language":"en-US,en;q=0.9",
}

def fetch(url):
    last=None
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers=HEADERS)
            with urllib.request.urlopen(req,timeout=8) as r:
                return r.read()
        except Exception as exc:
            last=exc
            if attempt<2:
                time.sleep(0.5*(attempt+1))
    raise last

def parse(data,source):
    root=ET.fromstring(data)
    out=[]
    for item in root.findall(".//item")+root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        def val(names):
            for n in names:
                e=item.find(n)
                if e is not None and e.text:
                    return e.text.strip()
            return ""
        title=val(["title","{http://www.w3.org/2005/Atom}title"])
        desc=val(["description","summary","{http://www.w3.org/2005/Atom}summary"])
        guid=val(["guid","id","{http://www.w3.org/2005/Atom}id"])
        pub=val(["pubDate","published","updated","{http://www.w3.org/2005/Atom}updated"])
        try:
            event_ts=parsedate_to_datetime(pub).timestamp()
        except Exception:
            try:
                event_ts=time.mktime(time.strptime(pub[:19],"%Y-%m-%dT%H:%M:%S"))
            except Exception:
                event_ts=0
        text=(title+" "+desc).upper()
        hits=[k for k in KEYWORDS if k in text]
        if guid and hits:
            out.append({
                "source":source,"id":guid,"title":title,"published_ts":event_ts,
                "keywords":hits,
                "hash":hashlib.sha256((source+"|"+guid).encode()).hexdigest()[:20],
            })
    return out

def main():
    now=time.time()
    events=[]
    errors={}
    for source,url in FEEDS.items():
        try:
            events.extend(parse(fetch(url),source))
        except Exception as exc:
            errors[source]=type(exc).__name__+": "+str(exc)
    unique={e["hash"]:e for e in events}
    events=sorted(unique.values(),key=lambda x:x["published_ts"],reverse=True)
    recent=[e for e in events if 0<=now-e["published_ts"]<=86400]
    state={
        "timestamp":now,
        "status":"RESEARCH_ONLY",
        "source_count":len(FEEDS)-len(errors),
        "feed_errors":errors,
        "event_count":len(events),
        "recent_major_events":recent[:20],
        "quorum_policy":{"actionable_min_distinct_sources":2,"real_orders":False},
        "fail_closed":True,
    }
    OUT.write_text(json.dumps(state,indent=2))
    with AUDIT.open("a") as f:
        for e in recent[:20]:
            f.write(json.dumps({"observed_at":now,**e},separators=(",",":"))+"\n")
    print(json.dumps(state,indent=2))

if __name__=="__main__":
    main()
