"""$2->$4 Delta BTC perpetual challenge selector.
200x is used for margin efficiency; actual loss is capped in USD.
Paper-only: no exchange order submission.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class ChallengeConfig:
    leverage:float=200.0
    min_contract_btc:float=0.001
    min_score:int=75
    min_rr:float=2.5
    risk_fraction:float=0.20
    max_consecutive_losses:int=2
    max_drawdown:float=0.20
    fee_bps:float=5.0
    slippage_bps:float=4.0
    adverse_bps:float=3.0

def f(x,d=0.0):
    try:return float(x)
    except (TypeError,ValueError):return d

def select(signal, levels, micro, equity=2.0, consecutive_losses=0, cfg=ChallengeConfig()):
    reasons=[]; score=0
    if consecutive_losses>=cfg.max_consecutive_losses:
        return {"allowed":False,"score":0,"reason":"LOSS_STREAK_BREAKER"}
    if equity<=0 or equity>=4:
        return {"allowed":False,"score":0,"reason":"ACCOUNT_TERMINAL"}
    if not signal.get("valid"):
        return {"allowed":False,"score":0,"reason":"SIGNAL_INVALID"}
    side=str(signal.get("action","")); rr=f(signal.get("rr")); conf=f(signal.get("confidence"))
    spread=f(micro.get("spread_bps"),999); fresh=f(micro.get("fresh_seconds"),999)
    bias=str(signal.get("five_min_bias","UNKNOWN"))
    if conf>=.80: score+=20
    elif conf>=.70: score+=12
    else: reasons.append("CONFIDENCE_LOW")
    if rr>=3: score+=20
    elif rr>=cfg.min_rr: score+=15
    else: reasons.append("RR_LOW")
    if spread<=2: score+=15
    elif spread<=3: score+=8
    else: reasons.append("SPREAD_HIGH")
    if fresh<=.5: score+=10
    elif fresh<=1.5: score+=5
    else: reasons.append("DATA_STALE")
    if (side=="LONG" and bias=="BULLISH") or (side=="SHORT" and bias=="BEARISH"): score+=15
    elif bias=="NEUTRAL": score+=5
    else: reasons.append("BIAS_CONFLICT")
    regime=str(levels.get("regime",""))
    if (side=="LONG" and "bull" in regime.lower()) or (side=="SHORT" and "bear" in regime.lower()): score+=10
    elif regime: score+=3
    if score<cfg.min_score or reasons:
        return {"allowed":False,"score":score,"reason":";".join(reasons) or "SCORE_GATE"}
    entry=f(signal.get("entry")); stop=f(signal.get("stop")); target=f(signal.get("target"))
    if min(entry,stop,target)<=0:return {"allowed":False,"score":score,"reason":"INVALID_PRICES"}
    notional=cfg.min_contract_btc*entry
    margin=notional/cfg.leverage
    max_risk_usd=equity*cfg.risk_fraction
    stop_loss_usd=abs(entry-stop)*cfg.min_contract_btc
    round_cost_usd=(entry+target)*cfg.min_contract_btc*(cfg.fee_bps+cfg.slippage_bps+cfg.adverse_bps)/10000
    if margin>equity:return {"allowed":False,"score":score,"reason":"MARGIN_UNAVAILABLE"}
    if stop_loss_usd+round_cost_usd>max_risk_usd:
        return {"allowed":False,"score":score,"reason":"RISK_BUDGET_EXCEEDED","stop_loss_usd":stop_loss_usd,
                "round_cost_usd":round_cost_usd,"risk_budget_usd":max_risk_usd}
    return {"allowed":True,"score":score,"side":side,"entry":entry,"stop":stop,"target":target,"rr":rr,
            "confidence":conf,"contracts":1,"quantity_btc":cfg.min_contract_btc,"leverage":cfg.leverage,
            "margin_usd":margin,"risk_budget_usd":max_risk_usd,"stop_loss_usd":stop_loss_usd,
            "round_cost_usd":round_cost_usd,"paper_only":True,"live_orders":False}

if __name__=="__main__": print("DELTA $2->$4 CHALLENGE: 200x MODEL | PAPER ONLY | REAL ORDERS OFF")
