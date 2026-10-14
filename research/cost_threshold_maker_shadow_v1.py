"""Cost-threshold first-touch labels and maker quote hazard simulator.
Research-only. No exchange API, order submission, or production strategy changes.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Iterable, Mapping, Any

@dataclass(frozen=True)
class BarrierConfig:
    target_bps: float = 20.0
    stop_bps: float = 10.0
    horizon_seconds: float = 300.0
    min_net_bps: float = 5.0
    assumed_round_trip_cost_bps: float = 15.8
    # The feature tape is sampled asynchronously; accept a final sample within 2s of horizon.
    coverage_tolerance_seconds: float = 2.0


def first_touch_label(entry_mid: float, path: Iterable[Mapping[str, Any]], side: int,
                      config: BarrierConfig = BarrierConfig(), entry_ts: float | None = None) -> dict[str, Any]:
    """Label +1 target-first, -1 stop-first, 0 neither/ambiguous/incomplete.
    Path rows need ts and mid. side is +1 long, -1 short. Path must be time ordered.
    A target is +20 bps in side-adjusted return; opposing barrier is -10 bps.
    """
    if entry_mid <= 0 or side not in (-1, 1):
        raise ValueError('entry_mid must be positive and side must be -1 or +1')
    rows=sorted((r for r in path if float(r.get('mid',0) or 0)>0),key=lambda r:float(r['ts']))
    if not rows:
        return {'label':0,'class':'ABSTAIN_INCOMPLETE_PATH','touch_seconds':None,'move_bps':None}
    t0=float(entry_ts) if entry_ts is not None else float(rows[0]['ts'])
    for r in rows:
        dt=float(r['ts'])-t0
        if dt>config.horizon_seconds: break
        move=side*(float(r['mid'])/entry_mid-1)*10000
        if move>=config.target_bps:
            return {'label':1,'class':'TARGET_FIRST','touch_seconds':dt,'move_bps':move}
        if move<=-config.stop_bps:
            return {'label':-1,'class':'STOP_FIRST','touch_seconds':dt,'move_bps':move}
    # A last observation just before the horizon is complete only within the explicit sampling tolerance.
    if float(rows[-1]['ts'])-t0 < config.horizon_seconds-config.coverage_tolerance_seconds:
        return {'label':0,'class':'ABSTAIN_INCOMPLETE_PATH','touch_seconds':None,'move_bps':side*(float(rows[-1]['mid'])/entry_mid-1)*10000}
    move=side*(float(rows[-1]['mid'])/entry_mid-1)*10000
    return {'label':0,'class':'ABSTAIN_NO_BARRIER','touch_seconds':None,'move_bps':move}

@dataclass(frozen=True)
class QuoteConfig:
    target_bps: float = 20.0
    stop_bps: float = 10.0
    ttl_ms: int = 500
    queue_expansion_abort: float = 0.25
    maker_fee_bps: float = 2.36
    taker_fee_bps: float = 5.90
    adverse_selection_bps: float = 1.5


def simulate_passive_quote(*, side: str, best_bid: float, best_ask: float,
                           queue_ahead_initial: float, queue_ahead_peak: float,
                           fill_after_ms: float | None, markout_bps: float = 0.0,
                           config: QuoteConfig = QuoteConfig()) -> dict[str, Any]:
    """Counterfactual top-of-book quote. Not an actual queue/fill simulator.
    Cancels on >25% queue growth or after 500ms; no fill is assumed otherwise.
    Filled maker entry is marked out at supplied signed price move, with taker exit
    and conservative adverse-selection charge. Spread capture is deliberately not
    guaranteed because fill path and queue priority are unknown.
    """
    side=side.upper()
    if side not in ('LONG','SHORT'): raise ValueError('side must be LONG or SHORT')
    if best_bid<=0 or best_ask<best_bid: raise ValueError('invalid book')
    if queue_ahead_initial<0 or queue_ahead_peak<0: raise ValueError('queue cannot be negative')
    if queue_ahead_initial>0 and queue_ahead_peak/queue_ahead_initial-1>config.queue_expansion_abort:
        return {'status':'CANCEL_QUEUE_HAZARD','filled':False,'cancel_after_ms':0,'net_markout_bps':None}
    if fill_after_ms is None or fill_after_ms>config.ttl_ms:
        return {'status':'EXPIRED_UNFILLED','filled':False,'cancel_after_ms':config.ttl_ms,'net_markout_bps':None}
    if fill_after_ms<0: raise ValueError('fill_after_ms cannot be negative')
    # Input markout is side-adjusted: positive means price moved favorably after fill.
    total_cost=config.maker_fee_bps+config.taker_fee_bps+config.adverse_selection_bps
    return {'status':'FILLED_COUNTERFACTUAL','filled':True,'fill_after_ms':fill_after_ms,
            'quote_price':best_bid if side=='LONG' else best_ask,
            'gross_markout_bps':markout_bps,'assumed_cost_bps':total_cost,
            'net_markout_bps':markout_bps-total_cost,
            'execution_model':'maker_entry_taker_exit_no_spread_capture_credit',
            'live_execution_enabled':False}


def summarize_shadow(path: str) -> dict[str, Any]:
    """Resolve recorded decision prices against later recorded prices at 15s sampling.
    Outputs approximate 60/120/300s markouts only; never represents tick-complete path.
    """
    import json
    rows=[]
    with open(path,encoding='utf-8') as f:
        for line in f:
            try:
                r=json.loads(line)
                px=float(r.get('entry_reference',r.get('price',0)) or 0)
                ts=float(r.get('observed_at_epoch',0) or 0)
                if px>0 and ts>0: rows.append((ts,px,r))
            except (ValueError,TypeError): pass
    rows.sort(key=lambda x:x[0]); out=[]
    for ts,px,r in rows:
        side=r.get('side')
        if side not in ('LONG','SHORT') or r.get('allowed') is not True: continue
        sign=1 if side=='LONG' else -1
        horizons={}
        for h in (60,120,300):
            future=next((x for x in rows if x[0]>=ts+h),None)
            if future:
                horizons[str(h)]={'gross_markout_bps':sign*(future[1]/px-1)*10000,
                                  'net_taker_bps':sign*(future[1]/px-1)*10000-15.8,
                                  'net_hybrid_estimate_bps':sign*(future[1]/px-1)*10000-8.0}
        out.append({'ts':ts,'side':side,'allowed':True,'horizons':horizons})
    return {'status':'RESEARCH_ONLY','source':path,'rows':len(rows),'accepted_decisions':len(out),
            'markouts':out,'sampling_warning':'15-second decision snapshots are not tick-complete; no queue/fill inference is possible',
            'real_orders':False,'live_execution_enabled':False}

if __name__=='__main__':
    import json,sys
    from pathlib import Path
    p=Path(sys.argv[1]) if len(sys.argv)>1 else Path('data/processed/confluence_shadow_decisions.jsonl')
    print(json.dumps(summarize_shadow(str(p)),indent=2,allow_nan=False))
