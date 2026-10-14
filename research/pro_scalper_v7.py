"""PRO SCALPER V7 — integrated adaptive research engine.
Research/paper only. No live execution, leverage, risk or production authority.
Combines V6 empirical edge, adaptive event evidence, regime context and costs.
"""
from __future__ import annotations
import json, math, time
from pathlib import Path
from research.pro_scalper_v6 import ensemble as v6_ensemble

ROOT=Path(__file__).resolve().parents[1]
ADAPTIVE=ROOT/"data/processed/adaptive_event_engine_v1.json"
MTF=ROOT/"data/processed/multi_timeframe_context_v1.json"
CFG=ROOT/"research/pro_scalper_v6_config.json"

def read(path, default):
    try: return json.loads(path.read_text())
    except Exception: return default

def finite(x):
    try: return math.isfinite(float(x))
    except Exception: return False

def regime_context():
    d=read(MTF,{})
    t=d.get("timeframes",{})
    ready=[]
    for tf in ("5m","15m","1h"):
        x=t.get(tf,{})
        if x.get("ready"): ready.append((tf,x))
    if not ready: return {"ready":False,"agreement":0,"regime":"UNKNOWN"}
    trends=[x.get("trend") for _,x in ready]
    non=[x for x in trends if x in ("BULLISH","BEARISH","MIXED")]
    agreement=0
    if non:
        agreement=max(non.count("BULLISH"),non.count("BEARISH"))/len(non)
    return {"ready":True,"agreement":agreement,"regime":ready[0][1].get("regime","UNKNOWN"),
            "trends":{tf:x.get("trend") for tf,x in ready}}

def adaptive_evidence(action):
    d=read(ADAPTIVE,{})
    best=None
    for c in d.get("cohorts",[]):
        event=c.get("event","")
        directional = ("long" in event and action=="LONG") or ("short" in event and action=="SHORT")
        if not directional: continue
        if best is None or float(c.get("avg_net_bps",-999))>float(best.get("avg_net_bps",-999)):
            best=c
    return best or {"avg_net_bps":-999,"n":0,"event":"NONE"}

def evaluate(state, now_ts=None):
    now=float(now_ts or time.time())
    cfg=read(CFG,{})
    v6=v6_ensemble(state,now_ts=now,config=cfg)
    action=v6.get("action")
    if action not in ("LONG","SHORT"):
        return {"schema":"pro_scalper_v7_decision","action":"ABSTAIN","reason":"V6_ABSTAIN",
                "paper_only":True,"real_orders":False,"v6":v6}

    regime=regime_context()
    event=adaptive_evidence(action)
    event_net=float(event.get("avg_net_bps",-999)) if finite(event.get("avg_net_bps")) else -999
    v6_net=float(v6.get("net_edge_bps",-999)) if finite(v6.get("net_edge_bps")) else -999

    # Independent evidence gates. Adaptive event evidence is confirmatory, never
    # allowed to turn a V6 abstention into a trade.
    if v6_net < 1.0:
        return {"schema":"pro_scalper_v7_decision","action":"ABSTAIN","reason":"V6_NET_EDGE_FAIL",
                "v6_net_edge_bps":v6_net,"event":event,"regime":regime,
                "paper_only":True,"real_orders":False,"v6":v6}

    if event.get("n",0) < 50 or event_net <= 0:
        return {"schema":"pro_scalper_v7_decision","action":"ABSTAIN","reason":"EVENT_CONFIRMATION_FAIL",
                "v6_net_edge_bps":v6_net,"event":event,"regime":regime,
                "paper_only":True,"real_orders":False,"v6":v6}

    if regime.get("ready") and regime.get("agreement",0) < 0.66:
        return {"schema":"pro_scalper_v7_decision","action":"ABSTAIN","reason":"MTF_CONFLICT",
                "v6_net_edge_bps":v6_net,"event":event,"regime":regime,
                "paper_only":True,"real_orders":False,"v6":v6}

    return {"schema":"pro_scalper_v7_decision","action":action,"reason":"MULTI_LAYER_CONFIRMED",
            "score":min(1.0,max(0.0,(v6_net/20.0))),
            "score_is_probability":False,"v6_net_edge_bps":v6_net,
            "event":event,"regime":regime,
            "evidence":["V6_EMPIRICAL_EDGE","ADAPTIVE_EVENT","MTF_CONTEXT","COST_NETTED"],
            "paper_only":True,"real_orders":False,"v6":v6}

if __name__=="__main__":
    state=read(ROOT/"data/live_microstructure_state.json",{})
    print(json.dumps(evaluate(state),indent=2))
