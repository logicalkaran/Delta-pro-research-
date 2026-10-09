"""Standalone 12-strategy shadow evaluator using the same router and fill model.

Research only. It gives every qualifying strategy an independent paper/shadow
trade path so the leaderboard is not conditioned on portfolio selection.
"""
from __future__ import annotations
import json, signal, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data/live_microstructure_state.json"
OUT=ROOT/"data/processed/scalper_shadow_portfolio_v1.jsonl"
SUMMARY=ROOT/"data/processed/scalper_shadow_portfolio_v1_summary.json"
KILL=ROOT/"data/run/LIVE_KILL_SWITCH"
import sys
sys.path.insert(0,str(ROOT))
from strategy.scalper_portfolio_v1 import evaluate_all
from execution.execution_router_v1 import decide

TICK=.50; CONTRACT_BTC=.001; CONTRACTS=1
MAKER_FEE=2.36; TAKER_FEE=5.90
MAX_AGE=2.0; STOP_BPS=5.0; TARGET_BPS=10.0; MAX_HOLD=600.0
QUEUE_FRACTION=.02; ENTRY_TIMEOUT=3.0; COOLDOWN=1.0
RUNNING=True

def stop(a,b):
    global RUNNING
    RUNNING=False
signal.signal(signal.SIGINT,stop); signal.signal(signal.SIGTERM,stop)

def f(x,d=0.0):
    try:return float(x)
    except:return d
def tick(p):return round(p/TICK)*TICK
def ist_session(ts):
    dt=datetime.fromtimestamp(ts,tz=timezone.utc)+timedelta(hours=5,minutes=30)
    h=dt.hour
    return "00-06" if h<6 else "06-12" if h<12 else "12-18" if h<18 else "18-24"
def fee(p,b):return p*CONTRACT_BTC*CONTRACTS*b/10000
def log(row):
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open("a") as h:h.write(json.dumps(row,separators=(",",":"))+"\n")

def make_position(strategy,route,side,entry,now,score,regime):
    return {"strategy":strategy,"route":route,"side":side,"entry":entry,"opened":now,
            "regime":regime,"ist_session":ist_session(now),
            "stop":tick(entry*(1-STOP_BPS/10000)) if side=="LONG" else tick(entry*(1+STOP_BPS/10000)),
            "target":tick(entry*(1+TARGET_BPS/10000)) if side=="LONG" else tick(entry*(1-TARGET_BPS/10000)),
            "entry_fee":fee(entry,MAKER_FEE if route=="MAKER" else TAKER_FEE),
            "signal_score":score}

def main(seconds=86400):
    start=time.time(); last_ts=None
    active={}; pending={}; cooldown={}
    stats={"observations":0,"signals":0,"routes":{"MAKER":0,"TAKER_PAPER":0,"REJECT":0},
           "posted":0,"maker_fills":0,"taker_fills":0,"cancels":0,"trades":0,
           "wins":0,"losses":0,"sum_net_bps":0.0,"sum_net_usd":0.0,"by_strategy":{},"by_route":{}}
    while RUNNING and time.time()-start<seconds:
        now=time.time()
        try:s=json.loads(STATE.read_text())
        except Exception:time.sleep(.25);continue
        stats["observations"]+=1
        fresh=f(s.get("quality",{}).get("fresh_seconds"),999)
        if fresh>MAX_AGE:time.sleep(.25);continue
        if KILL.exists():time.sleep(.5);continue
        ob=s.get("order_book",{});bid=f(ob.get("best_bid"));ask=f(ob.get("best_ask"));mid=f(ob.get("mid_price"))
        if min(bid,ask,mid)<=0:time.sleep(.25);continue
        last=s.get("last_trade",{});ts=last.get("ts");new_trade=ts is not None and ts!=last_ts
        if new_trade:last_ts=ts

        # Manage each independent strategy position.
        for strategy,pos in list(active.items()):
            side=pos["side"];exit_px=(bid-TICK) if side=="LONG" else (ask+TICK)
            hit_stop=(exit_px<=pos["stop"]) if side=="LONG" else (exit_px>=pos["stop"])
            hit_target=(exit_px>=pos["target"]) if side=="LONG" else (exit_px<=pos["target"])
            why="STOP" if hit_stop else "TARGET" if hit_target else "TIME" if now-pos["opened"]>=MAX_HOLD else None
            if why:
                gross=(exit_px/pos["entry"]-1)*10000
                gross=gross if side=="LONG" else -gross
                total_fee=pos["entry_fee"]+fee(exit_px,TAKER_FEE)
                notional=pos["entry"]*CONTRACT_BTC
                net_usd=gross/10000*notional-total_fee
                net_bps=net_usd/notional*10000
                row={"ts":now,"event":"SHADOW_EXIT","strategy":strategy,"route":pos["route"],"side":side,
                     "entry":pos["entry"],"exit":exit_px,"gross_bps":gross,"net_bps":net_bps,
                     "net_usd":net_usd,"reason":why,"hold_s":now-pos["opened"]}
                log(row);stats["trades"]+=1;stats["sum_net_bps"]+=net_bps;stats["sum_net_usd"]+=net_usd
                stats["wins"]+=net_bps>0;stats["losses"]+=net_bps<=0
                d=stats["by_strategy"].setdefault(strategy,{"trades":0,"wins":0,"sum_net_bps":0})
                d["trades"]+=1;d["wins"]+=net_bps>0;d["sum_net_bps"]+=net_bps
                d=stats["by_route"].setdefault(pos["route"],{"trades":0,"wins":0,"sum_net_bps":0})
                d["trades"]+=1;d["wins"]+=net_bps>0;d["sum_net_bps"]+=net_bps
                del active[strategy];cooldown[strategy]=now

        # Manage independent maker queues.
        for strategy,c in list(pending.items()):
            if now-c["created"]>ENTRY_TIMEOUT:
                log({"ts":now,"event":"SHADOW_CANCEL","strategy":strategy,"reason":"QUEUE_TIMEOUT","candidate":c})
                stats["cancels"]+=1;del pending[strategy];cooldown[strategy]=now;continue
            consumed=0
            if new_trade:
                lp=f(last.get("price"));ls=str(last.get("side","")).lower();size=abs(f(last.get("size")))
                if c["side"]=="LONG" and ls=="sell" and lp<=c["limit"]:consumed=size
                if c["side"]=="SHORT" and ls=="buy" and lp>=c["limit"]:consumed=size
            c["queue"]-=consumed
            crossed=(c["side"]=="LONG" and ask<=c["limit"]) or (c["side"]=="SHORT" and bid>=c["limit"])
            if c["queue"]<=0 or crossed:
                active[strategy]=make_position(strategy,"MAKER",c["side"],c["limit"],now,c["score"],c["regime"])
                stats["maker_fills"]+=1
                log({"ts":now,"event":"SHADOW_MAKER_FILL","position":active[strategy]})
                del pending[strategy]

        # Give every qualifying strategy its own identical routing decision.
        for sig in evaluate_all(s):
            if sig.action=="NO_TRADE" or sig.strategy in active or sig.strategy in pending: continue
            if now-cooldown.get(sig.strategy,0)<COOLDOWN: continue
            spread=f(ob.get("spread"));spread_bps=spread/max(mid,1e-9)*10000
            w5=s.get("windows",{}).get("5",{})
            recent_delta=f(w5.get("delta_pct"))
            recent_return_bps=f(s.get("price",{}).get("5",{}).get("return_pct"))*100
            qa=(f(ob.get("bid_depth_5")) if sig.action=="LONG" else f(ob.get("ask_depth_5")))*QUEUE_FRACTION
            route=decide(signal_edge_bps=sig.expected_move_bps,spread_bps=spread_bps,queue_ahead=qa,
                         recent_delta=recent_delta,recent_return_bps=recent_return_bps)
            stats["signals"]+=1;stats["routes"][route.mode]=stats["routes"].get(route.mode,0)+1
            log({"ts":now,"event":"SHADOW_SIGNAL","strategy":sig.strategy,"action":sig.action,"score":sig.score,
                 "modelled_edge_bps":sig.expected_move_bps,"route":route.mode,
                 "route_reason":route.reason,"route_cost_bps":route.estimated_cost_bps,
                 "queue_cost_bps":route.queue_cost_bps,"adverse_selection_bps":route.adverse_selection_bps})
            if route.mode=="MAKER":
                side=sig.action;limit=tick(bid if side=="LONG" else ask)
                pending[sig.strategy]={"created":now,"strategy":sig.strategy,"side":side,"limit":limit,
                                       "queue":max(1,qa),"score":sig.score,"regime":s.get("regime","UNKNOWN"),
                                       "ist_session":ist_session(now)}
                stats["posted"]+=1;log({"ts":now,"event":"SHADOW_POST_ONLY","candidate":pending[sig.strategy]})
            elif route.mode=="TAKER_PAPER":
                side=sig.action;entry=ask+TICK if side=="LONG" else bid-TICK
                active[sig.strategy]=make_position(sig.strategy,"TAKER_PAPER",side,entry,now,sig.score,s.get("regime","UNKNOWN"))
                stats["taker_fills"]+=1;log({"ts":now,"event":"SHADOW_TAKER_FILL","position":active[sig.strategy]})
        time.sleep(.25)

    for d in stats["by_strategy"].values():
        d["win_rate"]=d["wins"]/d["trades"] if d["trades"] else 0
        d["avg_net_bps"]=d["sum_net_bps"]/d["trades"] if d["trades"] else 0
    for d in stats["by_route"].values():
        d["win_rate"]=d["wins"]/d["trades"] if d["trades"] else 0
        d["avg_net_bps"]=d["sum_net_bps"]/d["trades"] if d["trades"] else 0
    summary={**stats,"duration_s":time.time()-start,"open_positions":len(active),"pending":len(pending),
             "win_rate":stats["wins"]/stats["trades"] if stats["trades"] else 0,
             "avg_net_bps":stats["sum_net_bps"]/stats["trades"] if stats["trades"] else 0,
             "status":"SHADOW_ONLY","real_orders":False,"strategy_count":12,
             "execution":"EXECUTION_ROUTER_V1_SHARED_MODEL"}
    SUMMARY.write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2),flush=True)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--seconds",type=int,default=86400)
    main(p.parse_args().seconds)
