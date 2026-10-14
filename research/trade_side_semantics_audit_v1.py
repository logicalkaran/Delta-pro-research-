"""Read-only event-time-aligned audit of Delta trade role tags vs L1 quote tests."""
import argparse, bisect, collections, gzip, glob, json, os

def role_hypothesis(r):
    return {"t":"buy","m":"sell"}.get(r,"unknown")

def quote_hypothesis(p,bid,ask):
    if bid is None or ask is None or bid <= 0 or ask <= 0 or bid > ask: return "no_quote"
    if p >= ask: return "buy"
    if p <= bid: return "sell"
    return "ambiguous"

def load(paths):
    messages=[]; types=collections.Counter(); malformed=0
    for path in paths:
        with gzip.open(path,"rt",encoding="utf-8") as f:
            for line in f:
                try:
                    row=json.loads(line); m=row.get("message") or {}
                    typ=m.get("type","unknown"); types[typ]+=1
                    if typ=="ob_l1":
                        try:
                            ts=int(m["ts"]); bid=float(m["bp"]); ask=float(m["ap"])
                            if 0 < bid <= ask: messages.append(("quote",ts,bid,ask,row.get("received_at")))
                        except (KeyError,TypeError,ValueError): pass
                    elif typ=="trades":
                        try:
                            t=int(m["t"]); mts=int(m["ts"]); p=float(m["p"]); size=abs(float(m["s"]))
                            messages.append(("trade",t,p,size,m.get("r"),mts,row.get("received_at")))
                        except (KeyError,TypeError,ValueError): pass
                except (json.JSONDecodeError,TypeError): malformed+=1
    return messages,types,malformed

def audit(paths):
    events,types,malformed=load(paths)
    quotes=sorted((e for e in events if e[0]=="quote"),key=lambda x:x[1])
    trades=sorted((e for e in events if e[0]=="trade"),key=lambda x:x[1])
    qts=[q[1] for q in quotes]
    counts=collections.Counter(); roles=collections.Counter(); agree=disagree=compared=0
    ages=[]; examples=[]
    for tr in trades:
        _,t,p,size,tag,mts,recv=tr
        idx=bisect.bisect_right(qts,t)-1
        if idx<0:
            counts["quote_no_prior_event_time"]+=1
            continue
        q=quotes[idx]; _,qts0,bid,ask,qrecv=q
        age_ms=(t-qts0)/1000
        ages.append(age_ms)
        qside=quote_hypothesis(p,bid,ask); rside=role_hypothesis(tag)
        counts["quote_"+qside]+=1; roles["role_"+rside]+=1
        if qside in ("buy","sell") and rside in ("buy","sell"):
            compared+=1
            if qside==rside: agree+=1
            else: disagree+=1
        if len(examples)<20:
            examples.append({"trade_event_ts":t,"message_ts":mts,"quote_event_ts":qts0,
              "quote_age_ms":age_ms,"price":p,"size":size,"role_tag":tag,
              "matched_bid":bid,"matched_ask":ask,"quote_test":qside,"role_mapping_hypothesis":rside,
              "trade_received_at":recv,"quote_received_at":qrecv})
    return {"schema":"trade_side_event_time_audit_v1","inputs":paths,"message_types":dict(types),
      "malformed_json":malformed,"valid_l1_quotes":len(quotes),"valid_trades":len(trades),
      "quote_test_counts":dict(counts),"role_mapping_counts":dict(roles),
      "comparable_role_quote_trades":compared,"role_quote_agree":agree,"role_quote_disagree":disagree,
      "agreement_rate":agree/compared if compared else None,
      "matched_quote_age_ms":{"count":len(ages),"median":sorted(ages)[len(ages)//2] if ages else None,
         "p95":sorted(ages)[int(.95*(len(ages)-1))] if ages else None,"max":max(ages) if ages else None},
      "examples":examples,
      "limitations":["Quotes are aligned by exchange event timestamp, but this remains a quote-test proxy, not trade-side ground truth.",
        "Role tag mapping t=buy and m=sell is tested as a hypothesis; it is not independently verified by this audit.",
        "No production code or execution settings were changed."]}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("paths",nargs="*")
    ap.add_argument("--output",default="data/processed/trade_side_event_time_audit_v1.json"); a=ap.parse_args()
    paths=a.paths or sorted(glob.glob("data/raw/quant_protocol_bounded/**/*_raw/**/*.jsonl.gz",recursive=True))
    if not paths: raise SystemExit("No raw capture files found")
    result=audit(paths); os.makedirs(os.path.dirname(a.output) or ".",exist_ok=True)
    with open(a.output,"w",encoding="utf-8") as f: json.dump(result,f,indent=2); f.write("\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ("examples","inputs")},indent=2))
    print("output:",a.output)
if __name__=="__main__": main()
