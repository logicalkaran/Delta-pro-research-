"""Selective BTCUSD scalper forecaster. Research/paper-only; no orders.
Optimized for signal quality over signal frequency. Conflicting flow is a hard veto.
Probabilities are model scores, not guaranteed market probabilities.
"""
import math

def _f(x,d=0.0):
    try:return float(x)
    except:return d

def forecast(state):
    w=state.get("windows",{});ob=state.get("order_book",{});p=state.get("price",{});q=state.get("quality",{})
    d5=_f(w.get("5",{}).get("delta_pct"));d30=_f(w.get("30",{}).get("delta_pct"));d60=_f(w.get("60",{}).get("delta_pct"))
    imb=_f(ob.get("imbalance_5"));imb10=_f(ob.get("imbalance_10"));cvd=_f(state.get("cvd_slope_30s"))
    mom5=_f(p.get("5",{}).get("return_pct"));mom30=_f(p.get("30",{}).get("return_pct"))
    spread=_f(ob.get("spread"));mid=max(_f(ob.get("mid_price")),1e-9);spread_bps=spread/mid*10000
    fresh=_f(q.get("fresh_seconds"),999);trades=_f(w.get("5",{}).get("trades"))
    if trades<5: trades=0
    # Independent evidence blocks. No single input can dominate.
    flow= d5*26 + d30*24 + d60*14 + imb*24 + imb10*12
    momentum= mom5*14 + mom30*8
    cvd_sign=1 if cvd>0 else -1 if cvd<0 else 0
    flow_sign=1 if flow>1.5 else -1 if flow<-1.5 else 0
    mom_sign=1 if momentum>0.02 else -1 if momentum<-0.02 else 0
    window_signs=[1 if z>0.015 else -1 if z<-0.015 else 0 for z in (d5,d30,d60)]
    directional=[z for z in window_signs if z]
    window_agree=(sum(z==flow_sign for z in directional)/len(directional)) if directional and flow_sign else 0
    core_agree=(1 if flow_sign==mom_sign and flow_sign else 0)
    cvd_agree=(1 if cvd_sign==flow_sign and flow_sign else 0)
    absorption=abs(flow)>7 and abs(momentum)>0.08 and flow_sign!=mom_sign
    conflict=len(set(directional))>1 or (flow_sign and mom_sign and flow_sign!=mom_sign)
    regime="ABSORPTION" if absorption else "CONTINUATION" if core_agree and window_agree>=0.66 else "MIXED"
    raw=flow+momentum+(cvd_sign*4)
    # Selective probability score; capped and explicitly separated from reliability.
    prob_up=1/(1+math.exp(-max(-10,min(10,raw/6))))
    veto=[]
    if fresh>2:veto.append("STALE_DATA")
    if spread_bps>5:veto.append("WIDE_SPREAD")
    if trades==0:veto.append("LOW_TRADE_SAMPLE")
    if conflict:veto.append("FLOW_CONFLICT")
    if absorption:veto.append("ABSORPTION")
    if abs(imb10)<0.05:veto.append("WEAK_BOOK_CONFIRMATION")
    if cvd_sign and flow_sign and cvd_sign!=flow_sign:veto.append("CVD_CONFLICT")
    # Require multiple independent confirmations before emitting direction.
    confirmations=(core_agree + cvd_agree + (1 if window_agree>=0.66 else 0) + (1 if abs(imb)>=0.15 else 0))
    direction="FLAT"
    if not veto and confirmations>=3 and abs(raw)>=10:
        direction="UP" if raw>0 else "DOWN"
    if veto and direction!="FLAT": direction="UNRELIABLE"
    confidence=50+min(45,abs(raw)*2.2)
    confidence*=0.75+0.25*min(1,confirmations/4)
    if conflict or absorption: confidence*=0.55
    if spread_bps>3: confidence*=0.9
    reliability="HIGH_BUT_UNVALIDATED" if direction!="FLAT" and confidence>=82 else "MEDIUM" if direction!="FLAT" else "LOW"
    execution_quality="GOOD" if spread_bps<=3 else "CAUTION" if spread_bps<=5 else "BLOCKED"
    explanation=[
      "FLOW_BULLISH" if flow>0 else "FLOW_BEARISH" if flow<0 else "FLOW_NEUTRAL",
      "WINDOWS_ALIGNED" if window_agree>=0.66 else "WINDOW_CONFLICT",
      "MOMENTUM_BULLISH" if momentum>0 else "MOMENTUM_BEARISH" if momentum<0 else "MOMENTUM_NEUTRAL",
      "CVD_CONFIRMS" if cvd_agree else "CVD_NOT_CONFIRMING",
      "BOOK_CONFIRMS" if abs(imb)>=0.15 else "BOOK_WEAK",
    ]
    return {
      "horizon_30s":{"direction":direction,"strength":round(max(0,min(100,confidence)),1)},
      "horizon_60s":{"direction":direction,"strength":round(max(0,min(100,confidence*0.92)),1)},
      "raw_score":round(raw,3),"spread_bps":round(spread_bps,3),"fresh_seconds":fresh,
      "drivers":{"delta5":d5,"delta30":d30,"delta60":d60,"imbalance":imb,"imbalance10":imb10,"cvd_slope":cvd,"momentum5":mom5,"momentum30":mom30,"flow_score":round(flow,3),"momentum_score":round(momentum,3),"agreement":round(window_agree,2),"confirmations":confirmations,"absorption":absorption},
      "regime":regime,"reliability":reliability,"prob_up":round(prob_up*100,1),"prob_down":round((1-prob_up)*100,1),
      "explanation":explanation,"execution_quality":execution_quality,
      "vetoes":veto,"calibration":"SELECTIVE_RESEARCH","calibration_warning":"Selective model favors fewer higher-confluence signals; accuracy is not yet production-validated.",
      "paper_only":True,"order_submission":False
    }
