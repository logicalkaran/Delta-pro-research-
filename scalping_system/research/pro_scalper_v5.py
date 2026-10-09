"""Causal, abstention-first BTC microstructure hypothesis score. Not probabilities."""
from __future__ import annotations
import math

def _f(x, d=None):
    try:
        y=float(x)
        return y if math.isfinite(y) else d
    except (TypeError, ValueError): return d

def _timeframes(candles, now):
    if isinstance(candles, dict) and "timeframes" in candles: return candles["timeframes"]
    cs = candles.get("candles", []) if isinstance(candles, dict) else (candles or [])
    result={}
    valid=sorted((c for c in cs if _f(c.get("timestamp")) is not None and _f(c.get("close"),0)>0),key=lambda c:_f(c.get("timestamp"),0))
    for name, span in (("5m",5),("15m",15),("1h",60)):
        bars=[c for c in valid if _f(c.get("timestamp"),0)+60 <= now][-span:]
        result[name]={"ready":len(bars)>=span,"samples":len(bars),"trend":"MIXED"}
        if len(bars)>=span:
            first,last=_f(bars[0]["close"]),_f(bars[-1]["close"])
            result[name]["return_pct"]=(last/first-1)*100
            result[name]["trend"]="UP" if last>first else "DOWN" if last<first else "MIXED"
    return result

def evaluate(state, candles=None, qwen=None, now_ts=None, config=None):
    config=config or {}; ob=state.get("order_book",{}); w=state.get("windows",{}); p=state.get("price",{}); q=state.get("quality",{})
    now=_f(now_ts, _f(state.get("updated_at_epoch"),0))
    event_age=_f(q.get("fresh_seconds"),999)
    state_age=max(0.0,now-_f(state.get("updated_at_epoch"),now))
    age=max(event_age,state_age)
    bid=_f(ob.get("best_bid"),0); ask=_f(ob.get("best_ask"),0); mid=_f(ob.get("mid_price"),0)
    if mid<=0 and bid>0 and ask>0: mid=(bid+ask)/2
    spread=(ask-bid)/mid*10000 if mid and ask>=bid else None
    vals={"imb5":_f(ob.get("imbalance_5")),"imb10":_f(ob.get("imbalance_10")),
          "delta5":_f(w.get("5",{}).get("delta_pct")),"delta30":_f(w.get("30",{}).get("delta_pct")),"delta60":_f(w.get("60",{}).get("delta_pct")),
          "ret5":_f(p.get("5",{}).get("return_pct")),"ret30":_f(p.get("30",{}).get("return_pct")),"ret60":_f(p.get("60",{}).get("return_pct")),
          "cvd_slope":_f(state.get("cvd_slope_30s"))}
    returns=[abs(vals[k]) for k in ("ret5","ret30","ret60") if vals[k] is not None]
    volatility_proxy_bps=max(returns)*100.0 if returns else None
    missing=[k for k,v in vals.items() if v is None]
    veto=[]
    if age>float(config.get("max_fresh_seconds",2)): veto.append("STALE_DATA")
    if spread is None or bid<=0 or ask<=0: veto.append("INVALID_BOOK")
    elif spread>float(config.get("max_spread_bps",4)): veto.append("WIDE_SPREAD")
    if missing: veto.append("INSUFFICIENT_MICROSTRUCTURE")
    sample_count=_f(q.get("trade_samples"),_f(w.get("5",{}).get("trades"),0))
    if sample_count<int(config.get("min_samples_5s",3)): veto.append("INSUFFICIENT_SAMPLES")
    if volatility_proxy_bps is not None and volatility_proxy_bps>float(config.get("max_short_volatility_bps",35)):
        veto.append("EXTREME_SHORT_TERM_VOLATILITY")
    tf=_timeframes(candles,now); ready=[v.get("trend") for v in tf.values() if v.get("ready")]
    score=0.0; evidence=[]
    if not missing:
        for k,weight,threshold in (("delta5",1.2,.08),("delta30",1,.08),("delta60",.7,.08),("imb5",1,.12),("imb10",.5,.12),("cvd_slope",.7,0), ("ret5",.6,.01),("ret30",.5,.02)):
            v=vals[k]; scale=threshold or 1
            if abs(v)>=threshold:
                score+=math.copysign(weight*min(1.0,abs(v)/max(scale*2,1e-12)),v); evidence.append(k)
    # Hypotheses are descriptive evidence, only act as small score adjustments.
    d30=vals.get("delta30"); ret30=vals.get("ret30"); delta5=vals.get("delta5"); ret5=vals.get("ret5")
    absorption=bool(d30 is not None and ret30 is not None and abs(d30)>.35 and abs(ret30)<.005)
    sweep_reclaim=bool(ret5 is not None and ret30 is not None and ret5*ret30<0 and abs(ret5)>.03 and abs(ret30)<.02)
    divergence=bool(delta5 is not None and ret5 is not None and delta5*ret5<0 and abs(delta5)>.25)
    if absorption: evidence.append("absorption_hypothesis")
    if sweep_reclaim: evidence.append("sweep_reclaim_hypothesis")
    if divergence: evidence.append("flow_price_divergence")
    if ready and all(x=="UP" for x in ready): score+=.5
    elif ready and all(x=="DOWN" for x in ready): score-=.5
    elif len(set(ready))>1: veto.append("CONFLICTING_TIMEFRAMES")
    if len(ready)==0: evidence.append("TIMEFRAMES_NOT_READY")
    if volatility_proxy_bps is not None: evidence.append("SHORT_TERM_VOLATILITY_OBSERVED")
    regime=str(state.get("regime","UNKNOWN"))
    if regime not in ("UNKNOWN","BALANCED","NEUTRAL"): evidence.append("REGIME_"+regime)
    # Optional Qwen fields are evidence tags only; no directives are consumed.
    if isinstance(qwen,dict) and qwen.get("available") is True: evidence.append("QWEN_CONTEXT_AVAILABLE")
    side="LONG" if score>=float(config.get("min_score",4)) else "SHORT" if score<=-float(config.get("min_score",4)) else "ABSTAIN"
    if veto: side="ABSTAIN"
    return {"action":side,"score":round(score,4),"score_is_probability":False,"evidence":evidence,"vetoes":sorted(set(veto)),
            "features":vals,"volatility_proxy_bps":volatility_proxy_bps,"spread_bps":spread,"fresh_seconds":age,"regime":regime,"timeframes":tf,
            "hypotheses":{"absorption":absorption,"sweep_reclaim":sweep_reclaim,"divergence":divergence},
            "qwen_used_as_control":False,"paper_only":True,"real_orders":False}
