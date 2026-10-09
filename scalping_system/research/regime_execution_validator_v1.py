import json,bisect,statistics
from pathlib import Path

RAW=Path("data/raw/delta_btc_raw.jsonl")
OUT=Path("data/processed/regime_execution_validation_v1.json")

# Research-only. No exchange/order/execution imports.
rows=[]; bp=ap=0.0
with RAW.open() as f:
    for line in f:
        try: m=json.loads(line); m=m.get("message",m)
        except Exception: continue
        if m.get("type")=="ob_l1":
            bp=float(m.get("bp",0)); ap=float(m.get("ap",0)); continue
        if m.get("type")=="trades" and bp and ap:
            rows.append((int(m.get("ts",0)),bp,ap,float(m.get("p",0)),float(m.get("s",1))))
rows.sort(); T=[x[0] for x in rows]; N=len(rows)

# Exact walk-forward selector found previously, evaluated with executable bid/ask paths.
# Signal: signed 30s trade pressure >= 0.35 and 30s price momentum >= 2 bps.
# Candidate: LONG, 300s. Fill models:
# 1) optimistic maker: entry at bid, exit at bid
# 2) conservative maker: entry at bid, exit at bid, 1/2 spread adverse-selection penalty
# 3) taker reference: entry ask, exit bid
# Stop/target are symmetric and first-hit on executable quotes.
def build_events():
    E=[]
    for i,(ts,b,a,px,q) in enumerate(rows):
        j=bisect.bisect_left(T,ts-30_000_000,0,i)
        if i-j<3: continue
        mid=(b+a)/2
        spread=(a-b)/mid*10000
        rec=rows[j:i]
        signed=sum((1 if x[3]>=mid else -1)*x[4] for x in rec)
        flow=signed/(sum(x[4] for x in rec) or 1)
        mom=(px-rec[0][3])/rec[0][3]*10000
        if flow<0.35 or mom<2 or spread>5: continue
        jend=bisect.bisect_left(T,ts+300_000_000)
        if jend>=N: continue
        E.append((i,jend))
    return E

E=build_events()
# De-duplicate overlapping signals: one trade at a time, 60s cooldown.
signals=[]; last=-10**30
for i,j in E:
    ts=rows[i][0]
    if ts-last < 60_000_000: continue
    signals.append((i,j)); last=ts

def simulate(stop_bps,target_bps,entry_mode,adverse_bps):
    trades=[]
    for i,jend in signals:
        ts,bid,ask,px,q=rows[i]
        entry=bid if entry_mode=="maker" else ask
        stop=entry*(1-stop_bps/10000)
        target=entry*(1+target_bps/10000)
        end=min(jend,N-1); exit_px=rows[end][1] if entry_mode=="maker" else rows[end][1]
        reason="TIME"
        for k in range(i+1,end+1):
            bidk,askk=rows[k][1],rows[k][2]
            if bidk<=stop:
                exit_px=bidk; reason="STOP"; break
            if bidk>=target:
                exit_px=bidk; reason="TARGET"; break
        gross=(exit_px-entry)/entry*10000
        # conservative adverse-selection model for maker: subtract penalty only on filled entry.
        net=gross-adverse_bps
        if entry_mode=="taker": net=gross-11.8
        trades.append(net)
    if not trades:return None
    wins=sum(x>0 for x in trades); gains=sum(x for x in trades if x>0); losses=-sum(x for x in trades if x<0)
    eq=0.0; peak=0.0; dd=0.0
    for x in trades:
        eq += x; peak=max(peak,eq); dd=max(dd,peak-eq)
    return {"n":len(trades),"win_rate":wins/len(trades),"avg_net_bps":sum(trades)/len(trades),
            "total_net_bps":sum(trades),"profit_factor":gains/losses if losses else None,
            "max_drawdown_bps":dd}

results=[]
for stop,target in [(5,10),(8,16),(10,20),(12,24)]:
    for adverse in (0,1,2,3):
        results.append({"stop_bps":stop,"target_bps":target,"model":"maker","adverse_selection_bps":adverse,
                        "result":simulate(stop,target,"maker",adverse)})
    results.append({"stop_bps":stop,"target_bps":target,"model":"taker_reference","adverse_selection_bps":0,
                    "result":simulate(stop,target,"taker",0)})

out={"status":"RESEARCH_ONLY","selector":{"side":"LONG","horizon_s":300,"flow_min":0.35,"momentum_min_bps":2,"spread_max_bps":5},
     "raw_trade_events":N,"signals_after_cooldown":len(signals),
     "fill_warning":"Maker results are hypothetical touch fills; queue position and cancellations are unavailable in this dataset. Adverse-selection penalties are stress scenarios, not measured fills.",
     "results":results}
OUT.write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
