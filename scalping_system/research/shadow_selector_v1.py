import json, collections, statistics, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/strategy_forward_tournament_v1.jsonl"
OUT=ROOT/"data/processed/shadow_selector_v1.json"
rows=[json.loads(x) for x in SRC.read_text().splitlines() if x.strip()]
rows.sort(key=lambda r:float(r["issued_at"]))
cut=float(rows[int(len(rows)*.70)]["issued_at"])
groups=collections.defaultdict(list)
for r in rows:
    groups[(r["strategy"],r["regime"],r["direction"],r["horizon"])].append(r)
results=[]
for key,rs in groups.items():
    train=[r for r in rs if float(r["issued_at"])<cut]
    test=[r for r in rs if float(r["issued_at"])>=cut]
    if len(train)<100 or len(test)<50: continue
    def stats(x):
        vals=[float(r["net_return_pct"])*100 for r in x]
        wins=[v for v in vals if v>0]; losses=[-v for v in vals if v<0]
        return {"n":len(vals),"avg_net_bps":round(sum(vals)/len(vals),4),
                "win_rate":round(len(wins)/len(vals),4),
                "profit_factor":round(sum(wins)/sum(losses),4) if losses else None}
    tr,te=stats(train),stats(test)
    stable=(tr["avg_net_bps"]>0 and (tr["profit_factor"] or 0)>=1.2 and
            te["avg_net_bps"]>0 and (te["profit_factor"] or 0)>=1.2)
    results.append({"strategy":key[0],"regime":key[1],"direction":key[2],"horizon":key[3],
                    "train":tr,"test":te,"stable":stable})
stable=[x for x in results if x["stable"]]
report={"status":"RESEARCH_ONLY","updated_at":time.time(),"source_rows":len(rows),
        "chronological_holdout":0.30,"cost_model":"source net_return_pct",
        "candidates":len(results),"stable_candidates":stable,
        "recommended":None if not stable else sorted(stable,key=lambda x:x["test"]["avg_net_bps"],reverse=True)[0],
        "auto_apply":False,"paper_only":True,"real_orders":False,
        "note":"No candidate is promoted unless both chronological train and holdout pass net expectancy and PF gates."}
OUT.write_text(json.dumps(report,indent=2))
print(json.dumps({"source_rows":len(rows),"candidates":len(results),"stable_candidates":len(stable),"recommended":report["recommended"]},indent=2))
