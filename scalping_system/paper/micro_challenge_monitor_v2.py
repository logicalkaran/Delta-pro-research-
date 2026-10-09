"""Delta $2->$4 continuous paper contest. No exchange orders."""
from pathlib import Path
import sys,json,time,signal,argparse
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from strategy.predictive_levels_v1 import compute_levels
from strategy.short_horizon_predictor_v1 import predict
from strategy.short_horizon_execution_gate_v1 import gate as forecast_gate
from paper.micro_challenge_strategy_v1 import select,ChallengeConfig
STATE=ROOT/"data/live_microstructure_state.json"; CANDLES=ROOT/"data/live_candles.json"
OUT=ROOT/"data/processed/micro_challenge_stream_v2.jsonl"; SUMMARY=ROOT/"data/processed/micro_challenge_stream_v2_summary.json"
RUN=True; TICK=.5; HOLD=900; CFG=ChallengeConfig()
def stop(*_):
    global RUN; RUN=False
signal.signal(signal.SIGINT,stop); signal.signal(signal.SIGTERM,stop)
def f(x,d=0):
    try:return float(x)
    except:return d
def read(p):
    try:return json.loads(p.read_text())
    except:return None
def emit(x):
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open("a") as h:h.write(json.dumps(x,separators=(",",":"))+"\n")
def main(seconds=86400):
    global RUN
    started=time.time(); equity=2.0; peak=2.0; consecutive_losses=0; positions={}
    stats={"ticks":0,"candidate_signals":0,"accepted_entries":0,"rejected_entries":0,"forecast_rejections":0,"exits":0,"wins":0,"losses":0,"realized_pnl":0.0}
    print("DELTA $2->$4 CONTEST V2 | FORECAST GATE | PAPER ONLY",flush=True)
    while RUN and time.time()-started<seconds and equity<4.0 and equity>0:
        s=read(STATE); candles=read(CANDLES)
        if not isinstance(s,dict) or not isinstance(candles,list): time.sleep(TICK); continue
        px=f(s.get("order_book",{}).get("mid_price")); fresh=f(s.get("quality",{}).get("fresh_seconds"),999)
        if px<=0 or fresh>2: time.sleep(TICK); continue
        ob=s.get("order_book",{}); levels=compute_levels(candles,px,ob); prediction=predict(candles,levels,s)
        w5=s.get("windows",{}).get("5",{}); w30=s.get("windows",{}).get("30",{})
        d5=f(w5.get("delta_pct")); d30=f(w30.get("delta_pct")); imb=f(ob.get("imbalance_5"))
        ret5=f(s.get("price",{}).get("5",{}).get("return_pct")); spread=f(ob.get("spread_bps"),999)
        if spread==999: spread=(f(ob.get("spread"),999)/px*10000) if px>0 else 999
        now=time.time(); stats["ticks"]+=1
        for key,pos in list(positions.items()):
            hit_stop=px<=pos["stop"] if pos["side"]=="LONG" else px>=pos["stop"]
            hit_target=px>=pos["target"] if pos["side"]=="LONG" else px<=pos["target"]
            timeout=now-pos["opened"]>=HOLD
            if not (hit_stop or hit_target or timeout): continue
            reason="STOP" if hit_stop else ("TARGET" if hit_target else "TIMEOUT")
            gross=(px-pos["entry"])*CFG.min_contract_btc if pos["side"]=="LONG" else (pos["entry"]-px)*CFG.min_contract_btc
            cost=(pos["entry"]+px)*CFG.min_contract_btc*(CFG.fee_bps+CFG.slippage_bps+CFG.adverse_bps)/10000
            pnl=gross-cost; equity=max(0.0,equity+pnl); peak=max(peak,equity); stats["realized_pnl"]+=pnl; stats["exits"]+=1
            if pnl>0: stats["wins"]+=1; consecutive_losses=0
            else: stats["losses"]+=1; consecutive_losses+=1
            dd=1-equity/peak if peak else 1
            emit({"ts":now,"event":"EXIT","strategy":key,"side":pos["side"],"entry":pos["entry"],"exit":px,"reason":reason,"gross_pnl_usd":gross,"cost_usd":cost,"net_pnl_usd":pnl,"equity":equity,"drawdown":dd,"consecutive_losses":consecutive_losses,"leverage":CFG.leverage,"quantity_btc":CFG.min_contract_btc,"paper_only":True})
            del positions[key]
            if dd>=CFG.max_drawdown or consecutive_losses>=CFG.max_consecutive_losses:
                emit({"ts":now,"event":"HALT","reason":"RISK_BREAKER","equity":equity,"drawdown":dd,"consecutive_losses":consecutive_losses,"paper_only":True}); RUN=False; break
        if not RUN: break
        candidates=[]
        if d5<=-.10 and d30<0 and ret5>-.06 and imb>-.60: candidates.append(("ABSORPTION_LONG","LONG",.82))
        if d5>=.10 and d30>0 and ret5<.06 and imb<.60: candidates.append(("ABSORPTION_SHORT","SHORT",.82))
        if levels.nearest_support and abs(px-levels.nearest_support)<=max(levels.atr*.35,px*.0005) and d30<-.05 and ret5>=-.03: candidates.append(("LEVEL_FLOW_LONG","LONG",.78))
        if levels.nearest_resistance and abs(px-levels.nearest_resistance)<=max(levels.atr*.35,px*.0005) and d30>.05 and ret5<=.03: candidates.append(("LEVEL_FLOW_SHORT","SHORT",.78))
        if d5>.12 and d30>.04 and ret5>.03: candidates.append(("FLOW_MOMENTUM_LONG","LONG",.80))
        if d5<-.12 and d30<-.04 and ret5<-.03: candidates.append(("FLOW_MOMENTUM_SHORT","SHORT",.80))
        stats["candidate_signals"]+=len(candidates)
        for key,side,conf in candidates:
            if key in positions: continue
            atr=max(levels.atr,px*.0008); risk=min(atr,px*.003); entry=px
            stop=entry-risk if side=="LONG" else entry+risk; target=entry+2.5*risk if side=="LONG" else entry-2.5*risk
            fg=forecast_gate(prediction,side,entry,stop,root=ROOT)
            if not fg.allowed:
                stats["forecast_rejections"]+=1; stats["rejected_entries"]+=1
                emit({"ts":now,"event":"FORECAST_REJECT","strategy":key,"side":side,"reason":fg.reason,"forecast_direction":fg.forecast_direction,"horizon":fg.horizon,"forecast_score":fg.score,"level_price":fg.level_price,"distance_atr":fg.distance_atr,"equity":equity,"paper_only":True}); continue
            bias="BULLISH" if d5>0 else ("BEARISH" if d5<0 else "NEUTRAL")
            signal={"valid":True,"action":side,"rr":2.5,"confidence":conf,"five_min_bias":bias,"entry":entry,"stop":stop,"target":target}
            decision=select(signal,{"regime":str(levels.regime)},{"spread_bps":spread,"fresh_seconds":fresh},equity=equity,consecutive_losses=consecutive_losses,cfg=CFG)
            if not decision.get("allowed"):
                stats["rejected_entries"]+=1
                emit({"ts":now,"event":"REJECT","strategy":key,"side":side,"reason":decision.get("reason"),"score":decision.get("score"),"equity":equity,"spread_bps":spread,"forecast_score":fg.score,"paper_only":True}); continue
            positions[key]={"side":side,"entry":entry,"stop":stop,"target":target,"opened":now}; stats["accepted_entries"]+=1
            emit({"ts":now,"event":"ENTRY","strategy":key,"side":side,"entry":entry,"stop":stop,"target":target,"rr":2.5,"score":decision["score"],"forecast_score":fg.score,"forecast_horizon":fg.horizon,"forecast_direction":fg.forecast_direction,"confidence":conf,"quantity_btc":CFG.min_contract_btc,"leverage":CFG.leverage,"margin_usd":decision["margin_usd"],"risk_budget_usd":decision["risk_budget_usd"],"stop_loss_usd":decision["stop_loss_usd"],"round_cost_usd":decision["round_cost_usd"],"equity":equity,"paper_only":True,"real_orders":False})
        time.sleep(TICK)
    SUMMARY.write_text(json.dumps({**stats,"equity":equity,"peak":peak,"drawdown":1-equity/peak if peak else 1,"consecutive_losses":consecutive_losses,"open_positions":len(positions),"target_reached":equity>=4.0,"duration_s":time.time()-started,"leverage":CFG.leverage,"quantity_btc":CFG.min_contract_btc,"paper_only":True,"real_orders":False},indent=2))
    print(json.dumps({**stats,"equity":equity,"target_reached":equity>=4.0,"open_positions":len(positions),"paper_only":True,"real_orders":False},indent=2),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--seconds",type=int,default=86400); main(p.parse_args().seconds)
