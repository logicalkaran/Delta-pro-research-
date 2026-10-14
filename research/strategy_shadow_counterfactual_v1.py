"""Near-miss counterfactual evaluator; research-only, never feeds order logic."""
from pathlib import Path
import json,time,urllib.parse,urllib.request,collections
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/institutional_absorption_telemetry_v1.jsonl"
OUT=ROOT/"data/processed/strategy_shadow_counterfactual_v1.json"
FEE_BPS=5.5; SLIP_BPS=2.0; ADV_BPS=1.5; HOLD=30

def get_candles(start,end):
    q=urllib.parse.urlencode({"symbol":"BTCUSD","resolution":"1m","start":int(start),"end":int(end)})
    u="https://api.india.delta.exchange/v2/history/candles?"+q
    req=urllib.request.Request(u,headers={"User-Agent":"btc-shadow-research/1"})
    with urllib.request.urlopen(req,timeout=8) as r: d=json.loads(r.read())
    return d.get("result",[]) if d.get("success",True) else []

def main():
    raw=[]
    if SRC.exists():
        for line in SRC.read_text(errors="ignore").splitlines()[-300:]:
            try:
                x=json.loads(line)
                rs=x.get("reasons",[])
                if not x.get("valid",False) and any(r in {"LONG_CVD_NOT_EXTREME","SHORT_CVD_NOT_EXTREME","LONG_REJECTION_WEAK","SHORT_REJECTION_WEAK","POC_NOT_ABOVE_ENTRY","POC_NOT_BELOW_ENTRY"} for r in rs):
                    raw.append(x)
            except Exception: pass
    raw=raw[-50:]
    outcomes=[]; cache={}
    for x in raw:
        ts=int(x.get("signal_candle",0)); price=float(x.get("price",0) or 0)
        if not ts or price<=0: continue
        key=(ts//1800)
        try:
            if key not in cache: cache[key]=get_candles(ts+60,ts+(HOLD+2)*60)
            cs=sorted([c for c in cache[key] if int(c.get("time",c.get("timestamp",0)))>ts],key=lambda c:int(c.get("time",c.get("timestamp",0))))
        except Exception as e:
            continue
        if not cs: continue
        # Direction is inferred only from rejection component; ambiguous rows are skipped.
        side="LONG" if "LONG_" in " ".join(x.get("reasons",[])) else ("SHORT" if "SHORT_" in " ".join(x.get("reasons",[])) else None)
        if not side: continue
        atr=float(x.get("atr",0) or 0)
        if atr<=0: continue
        stop=(price-1.5*atr) if side=="LONG" else (price+1.5*atr)
        # Counterfactual target is 2R, deliberately independent of the live POC target.
        target=(price+2*(price-stop)) if side=="LONG" else (price-2*(stop-price))
        entry=price*(1+(SLIP_BPS+ADV_BPS)/10000) if side=="LONG" else price*(1-(SLIP_BPS+ADV_BPS)/10000)
        stop2=stop*(1-(SLIP_BPS+ADV_BPS)/10000) if side=="LONG" else stop*(1+(SLIP_BPS+ADV_BPS)/10000)
        target2=target*(1-(SLIP_BPS+ADV_BPS)/10000) if side=="LONG" else target*(1+(SLIP_BPS+ADV_BPS)/10000)
        outcome="TIMEOUT"; exit_px=None
        for c in cs[:HOLD]:
            h=float(c.get("high",0)); l=float(c.get("low",0))
            if side=="LONG" and l<=stop2:
                outcome="STOP"; exit_px=stop2; break
            if side=="SHORT" and h>=stop2:
                outcome="STOP"; exit_px=stop2; break
            if side=="LONG" and h>=target2:
                outcome="TARGET"; exit_px=target2; break
            if side=="SHORT" and l<=target2:
                outcome="TARGET"; exit_px=target2; break
        if exit_px is None:
            c=cs[min(HOLD-1,len(cs)-1)]; exit_px=float(c.get("close",price))
        gross=((exit_px-entry)/entry if side=="LONG" else (entry-exit_px)/entry)*10000
        net=gross-(2*FEE_BPS)
        outcomes.append({"signal_candle":ts,"side":side,"entry":entry,"stop":stop2,"target":target2,"outcome":outcome,"net_bps":net,"reasons":x.get("reasons",[])})
    wins=[x for x in outcomes if x["net_bps"]>0]; losses=[x for x in outcomes if x["net_bps"]<=0]
    result={"updated_at":int(time.time()),"candidates":len(raw),"evaluated":len(outcomes),"wins":len(wins),"losses":len(losses),
            "win_rate":len(wins)/len(outcomes) if outcomes else 0,"avg_net_bps":sum(x["net_bps"] for x in outcomes)/len(outcomes) if outcomes else 0,
            "by_outcome":dict(collections.Counter(x["outcome"] for x in outcomes)),
            "paper_only":True,"real_orders":False,"production_strategy_unchanged":True,"outcomes":outcomes[-50:]}
    OUT.write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!="outcomes"},indent=2))
if __name__=="__main__": main()
