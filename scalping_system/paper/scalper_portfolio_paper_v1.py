"""Professional Scalper Portfolio V1 paper runtime.

Consumes live read-only microstructure state. Runs 12 strategy signals through
the execution router and a conservative paper exchange. No private API calls,
no order submission, no live-mode switch.
"""
from __future__ import annotations
import json,time,signal,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data/live_microstructure_state.json"
OUT=ROOT/"data/processed/scalper_portfolio_paper_v1.jsonl"
SUMMARY=ROOT/"data/processed/scalper_portfolio_paper_v1_summary.json"
KILL=ROOT/"data/run/LIVE_KILL_SWITCH"
sys.path.insert(0,str(ROOT))
from strategy.scalper_portfolio_v1 import portfolio_pick,evaluate_all
from execution.execution_router_v1 import decide

TICK=.50;CONTRACT_BTC=.001;CONTRACTS=1
MAKER_FEE=2.36;TAKER_FEE=5.90;MAX_AGE=2.0
STOP_BPS=5.0;TARGET_BPS=10.0;MAX_HOLD=600.0
QUEUE_FRACTION=.02;MAX_ENTRY_AGE=3.0
RUNNING=True

def handler(a,b):
    global RUNNING;RUNNING=False
signal.signal(signal.SIGINT,handler);signal.signal(signal.SIGTERM,handler)

def f(x,d=0):
    try:return float(x)
    except:return d
def state():
    try:return json.loads(STATE.read_text())
    except:return None
def tick(p):return round(p/TICK)*TICK
def bps(a,b):return (b/a-1)*10000 if a>0 else 0
def fee(p,b):return p*CONTRACT_BTC*CONTRACTS*b/10000
def log(row):
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open("a") as h:h.write(json.dumps(row,separators=(",",":"))+"\n")

def main(seconds=86400):
    start=time.time();pos=None;candidate=None;last_ts=None;trades=[]
    stats={"observations":0,"strategy_candidates":0,"route_counts":{"MAKER":0,"TAKER_PAPER":0,"REJECT":0},
           "posted":0,"maker_fills":0,"taker_fills":0,"cancels":0,"trades":0,"wins":0,"losses":0,
           "sum_net_bps":0.0,"sum_net_usd":0.0,"by_strategy":{},"by_route":{},"kill_blocks":0,"stale_blocks":0}
    print("SCALPER PORTFOLIO PAPER V1 | 12 STRATEGIES | REAL ORDERS OFF",flush=True)
    while RUNNING and time.time()-start<seconds:
        s=state();now=time.time();stats["observations"]+=1
        if not s:time.sleep(.25);continue
        fresh=f(s.get("quality",{}).get("fresh_seconds"),999)
        if fresh>MAX_AGE:stats["stale_blocks"]+=1;time.sleep(.25);continue
        if KILL.exists():
            stats["kill_blocks"]+=1;time.sleep(.5);continue
        ob=s.get("order_book",{});bid=f(ob.get("best_bid"));ask=f(ob.get("best_ask"));mid=f(ob.get("mid_price"))
        if min(bid,ask,mid)<=0:time.sleep(.25);continue
        last=s.get("last_trade",{});ts=last.get("ts");new_trade=ts is not None and ts!=last_ts
        if new_trade:last_ts=ts

        # Exit management.
        if pos:
            side=pos["side"];exit_px=(bid-TICK) if side=="LONG" else (ask+TICK)
            stop=(exit_px<=pos["stop"]) if side=="LONG" else (exit_px>=pos["stop"])
            target=(exit_px>=pos["target"]) if side=="LONG" else (exit_px<=pos["target"])
            why="STOP" if stop else "TARGET" if target else "TIME" if now-pos["opened"]>=MAX_HOLD else None
            if why:
                gross=bps(pos["entry"],exit_px);gross=gross if side=="LONG" else -gross
                total_fee=pos["entry_fee"]+fee(exit_px,TAKER_FEE);notional=pos["entry"]*CONTRACT_BTC
                net_usd=gross/10000*notional-total_fee;net_bps=net_usd/notional*10000
                row={"ts":now,"event":"PAPER_EXIT","strategy":pos["strategy"],"route":pos["route"],
                     "side":side,"entry":pos["entry"],"exit":exit_px,"gross_bps":gross,"net_bps":net_bps,
                     "net_usd":net_usd,"reason":why,"hold_s":now-pos["opened"]}
                log(row);trades.append(row);stats["trades"]+=1;stats["sum_net_bps"]+=net_bps;stats["sum_net_usd"]+=net_usd
                stats["wins"]+=net_bps>0;stats["losses"]+=net_bps<=0
                bs=stats["by_strategy"].setdefault(pos["strategy"],{"trades":0,"wins":0,"sum_net_bps":0})
                bs["trades"]+=1;bs["wins"]+=net_bps>0;bs["sum_net_bps"]+=net_bps
                br=stats["by_route"].setdefault(pos["route"],{"trades":0,"wins":0,"sum_net_bps":0})
                br["trades"]+=1;br["wins"]+=net_bps>0;br["sum_net_bps"]+=net_bps
                pos=None

        # Resting maker candidate management.
        if not pos and candidate:
            if now-candidate["created"]>MAX_ENTRY_AGE:
                log({"ts":now,"event":"ENTRY_CANCEL","reason":"QUEUE_TIMEOUT","candidate":candidate})
                stats["cancels"]+=1;candidate=None
            else:
                consumed=0
                if new_trade:
                    lp=f(last.get("price"));side=str(last.get("side","")).lower();size=abs(f(last.get("size")))
                    if candidate["side"]=="LONG" and side=="sell" and lp<=candidate["limit"]:consumed=size
                    if candidate["side"]=="SHORT" and side=="buy" and lp>=candidate["limit"]:consumed=size
                candidate["queue"]-=consumed
                crossed=(candidate["side"]=="LONG" and ask<=candidate["limit"]) or (candidate["side"]=="SHORT" and bid>=candidate["limit"])
                if candidate["queue"]<=0 or crossed:
                    entry=candidate["limit"];side=candidate["side"]
                    pos={"strategy":candidate["strategy"],"route":"MAKER","side":side,"entry":entry,"opened":now,
                         "stop":tick(entry*(1-STOP_BPS/10000)) if side=="LONG" else tick(entry*(1+STOP_BPS/10000)),
                         "target":tick(entry*(1+TARGET_BPS/10000)) if side=="LONG" else tick(entry*(1-TARGET_BPS/10000)),
                         "entry_fee":fee(entry,MAKER_FEE),"signal_score":candidate["score"]}
                    stats["maker_fills"]+=1;log({"ts":now,"event":"MAKER_FILL","position":pos});candidate=None

        # New portfolio selection.
        if not pos and not candidate:
            best,all_sigs=portfolio_pick(s)
            if best:
                spread=f(ob.get("spread"));spread_bps=spread/max(mid,1e-9)*10000
                w5=s.get("windows",{}).get("5",{});recent_delta=f(w5.get("delta_pct"))
                recent_return_bps=f(s.get("price",{}).get("5",{}).get("return_pct"))*100
                qa=(f(ob.get("bid_depth_5")) if best.action=="LONG" else f(ob.get("ask_depth_5")))*QUEUE_FRACTION
                route=decide(signal_edge_bps=best.expected_move_bps,spread_bps=spread_bps,queue_ahead=qa,
                             recent_delta=recent_delta,recent_return_bps=recent_return_bps)
                rc=route.mode;stats["route_counts"][rc]=stats["route_counts"].get(rc,0)+1
                stats["strategy_candidates"]+=1
                log({"ts":now,"event":"PORTFOLIO_SIGNAL","strategy":best.strategy,"action":best.action,
                     "score":best.score,"modelled_edge_bps":best.expected_move_bps,"route":route.mode,
                     "route_reason":route.reason,"route_cost_bps":route.estimated_cost_bps,
                     "queue_cost_bps":route.queue_cost_bps,"adverse_selection_bps":route.adverse_selection_bps,
                     "alternatives":[{"strategy":x.strategy,"action":x.action,"score":x.score} for x in all_sigs[:5]]})
                if rc=="MAKER":
                    side=best.action;limit=tick(bid if side=="LONG" else ask)
                    candidate={"created":now,"strategy":best.strategy,"side":side,"limit":limit,
                               "queue":max(1,qa),"score":best.score}
                    stats["posted"]+=1;log({"ts":now,"event":"POST_ONLY_ENTRY","candidate":candidate})
                elif rc=="TAKER_PAPER":
                    side=best.action;entry=ask+TICK if side=="LONG" else bid-TICK
                    pos={"strategy":best.strategy,"route":"TAKER_PAPER","side":side,"entry":entry,"opened":now,
                         "stop":tick(entry*(1-STOP_BPS/10000)) if side=="LONG" else tick(entry*(1+STOP_BPS/10000)),
                         "target":tick(entry*(1+TARGET_BPS/10000)) if side=="LONG" else tick(entry*(1-TARGET_BPS/10000)),
                         "entry_fee":fee(entry,TAKER_FEE),"signal_score":best.score}
                    stats["taker_fills"]+=1;log({"ts":now,"event":"TAKER_PAPER_FILL","position":pos})
        time.sleep(.25)
    wins=[t["net_bps"] for t in trades if t["net_bps"]>0];losses=[-t["net_bps"] for t in trades if t["net_bps"]<0]
    for d in stats["by_strategy"].values():d["win_rate"]=d["wins"]/d["trades"] if d["trades"] else 0;d["avg_net_bps"]=d["sum_net_bps"]/d["trades"] if d["trades"] else 0
    for d in stats["by_route"].values():d["win_rate"]=d["wins"]/d["trades"] if d["trades"] else 0;d["avg_net_bps"]=d["sum_net_bps"]/d["trades"] if d["trades"] else 0
    summary={**stats,"duration_s":time.time()-start,"open_position":pos,"win_rate":len(wins)/len(trades) if trades else 0,
             "avg_net_bps":sum(wins+[-x for x in losses])/len(trades) if trades else 0,
             "profit_factor":sum(wins)/sum(losses) if losses else None,"status":"PAPER_ONLY","real_orders":False,
             "promotion":"BLOCKED","strategy_count":12,"execution":"EXECUTION_ROUTER_V1"}
    SUMMARY.write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2),flush=True)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--seconds",type=int,default=86400)
    main(p.parse_args().seconds)
