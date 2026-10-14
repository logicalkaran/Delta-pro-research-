"""Deterministic after-cost champion/challenger promotion gate; research only."""
from __future__ import annotations

def _ok(x:dict)->bool:
    return (x.get('n',0)>=50 and x.get('profit_factor',0)>=1.2 and x.get('avg_net_bps',-1e9)>0 and x.get('first_half_avg_net_bps',-1e9)>=0 and x.get('second_half_avg_net_bps',-1e9)>=0)

def evaluate(champion:dict,challenger:dict)->dict:
    eligible=_ok(challenger)
    better=challenger.get('avg_net_bps',-1e9)>champion.get('avg_net_bps',-1e9)
    promote=eligible and better
    return {'promote':promote,'winner':'challenger' if promote else 'champion','reason':'CHALLENGER_PASSES_ALL_GATES' if promote else ('CHALLENGER_INELIGIBLE' if not eligible else 'CHALLENGER_NOT_BETTER'),'gates':{'sample_ge_50':challenger.get('n',0)>=50,'pf_ge_1_2':challenger.get('profit_factor',0)>=1.2,'net_positive':challenger.get('avg_net_bps',-1e9)>0,'first_half_nonnegative':challenger.get('first_half_avg_net_bps',-1e9)>=0,'second_half_nonnegative':challenger.get('second_half_avg_net_bps',-1e9)>=0,'better_than_champion':better}}
