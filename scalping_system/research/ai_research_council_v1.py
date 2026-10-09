"""Evidence packet for multi-model research. Models advise; policy remains deterministic."""
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def load_results(paths:list[str]|None=None):
    paths=paths or [str(ROOT/'data'/'processed'/'adaptive_event_engine_v1.json'),str(ROOT/'data'/'processed'/'event_conditioned_edge_tournament_v1.json')]
    out=[]
    for p in paths:
        try:
            d=json.loads(Path(p).read_text()); out.append({'source':p,'data':d})
        except Exception as e: out.append({'source':p,'error':type(e).__name__})
    return out

def build_packet(paths=None):
    results=load_results(paths); questions=[]; disagreements=[]
    for r in results:
        d=r.get('data',{})
        stable=d.get('stable_positive',d.get('status')=='PROMOTE')
        if stable is not True: questions.append({'priority':'HIGH','source':r['source'],'question':'What new hypothesis can improve after-cost expectancy while surviving chronological holdout and realistic execution costs?'})
    return {'policy':'research_only','order_authority':False,'risk_authority':False,'sources':results,'roles':{'qwen':'microstructure pattern review','gemini':'independent regime/research synthesis','codex':'implementation/tests/benchmark review','chatgpt':'architecture/validation/promotion decision'},'questions':questions[:10],'disagreements':disagreements}

if __name__=='__main__': print(json.dumps(build_packet(),indent=2,sort_keys=True))
