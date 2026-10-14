from pathlib import Path
import json, random, time
import os
from research.pro_scalper_v5 import evaluate
from research.pro_scalper_v5_costs import calculate, round_tick, funding_crossings, funding_cost_bps, LOT_BTC
try:
    from research.qwen_specialization.layer import build_context
except Exception:
    build_context = None

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"research/pro_scalper_v5_config.json"
STATE=ROOT/"data/live_microstructure_state.json"
CANDLES=ROOT/"data/live_candles.json"
MTF=ROOT/"data/processed/multi_timeframe_context_v1.json"
OUT=ROOT/"data/processed/pro_scalper_v5_paper.jsonl"
PAPER_STATE=ROOT/"data/processed/pro_scalper_v5_paper_state.json"

def read(path, default):
    try: return json.loads(path.read_text())
    except (OSError, ValueError): return default

def floor_lots(quantity_btc):
    import math
    return math.floor(max(0.0,float(quantity_btc))/LOT_BTC + 1e-12)*LOT_BTC

class PaperEngine:
    def __init__(self, config=None, rng=None):
        self.config=config or read(CONFIG,{})
        self.rng=rng or random.Random()
        self.position=None
        self.trades=[]

    def _context(self, now):
        qwen=None
        if build_context:
            try: qwen={"available":True,"context":build_context(now_ts=now,tape_limit=5)}
            except Exception: qwen={"available":False}
        mtf=read(MTF,{})
        return mtf.get("timeframes",{}), qwen

    def step(self, state, now_ts=None, funding_rate=None):
        now=float(now_ts if now_ts is not None else time.time())
        ob=state.get("order_book",{})
        bid=float(ob.get("best_bid") or 0); ask=float(ob.get("best_ask") or 0)
        if bid<=0 or ask<=0 or ask<bid:
            return {"signal":None,"trade":None,"position":self.position,"reason":"NO_EXECUTABLE_BOOK","real_orders":False}
        tf,qwen=self._context(now)
        signal=evaluate(state,candles={"timeframes":tf},qwen=qwen,now_ts=now,config=self.config)
        if "STALE_DATA" in signal.get("vetoes",[]):
            return {"signal":signal,"trade":None,"position":self.position,"reason":"STALE_DATA_NO_FILL","real_orders":False}
        if self.position:
            pos=self.position
            for settlement in funding_crossings(pos["entry_ts"],now,self.config.get("funding_interval_seconds",28800)):
                if settlement not in pos["funding_settlements"]:
                    pos["funding_settlements"].append(settlement)
                    if funding_rate is None: pos["funding_status"]="UNKNOWN"
                    else:
                        pos["funding_bps"] += funding_cost_bps(pos["side"],funding_rate,1)
                        pos["funding_status"]="OBSERVED"
            mark=bid if pos["side"]=="LONG" else ask
            move=((mark-pos["entry_px"])/pos["entry_px"]*10000)*(1 if pos["side"]=="LONG" else -1)
            age=now-pos["entry_ts"]
            reason=None
            if move>=float(self.config.get("paper_target_bps",8)): reason="TARGET_FIRST_HIT"
            elif move<=-float(self.config.get("paper_stop_bps",8)): reason="STOP_FIRST_HIT"
            elif age>=float(self.config.get("max_hold_seconds",90)): reason="MAX_HOLD"
            elif signal["action"] in ("LONG","SHORT") and signal["action"]!=pos["side"]: reason="OPPOSITE_SIGNAL"
            if reason:
                exit_px=bid if pos["side"]=="LONG" else ask
                gross=((exit_px-pos["entry_px"])/pos["entry_px"]*10000)*(1 if pos["side"]=="LONG" else -1)
                costs=calculate(pos["notional"],gross,pos["entry_kind"],"TAKER",
                    # Entry and exit gross uses executable quotes; spread is already in gross.
                    spread_bps=0,
                    slippage_bps=float(self.config.get("taker_slippage_bps",1)),
                    adverse_selection_bps=float(pos["adverse_bps"]),
                    funding_bps=float(pos["funding_bps"]),funding_status=pos["funding_status"])
                trade={"side":pos["side"],"entry_ts":pos["entry_ts"],"exit_ts":now,
                    "entry_px":pos["entry_px"],"exit_px":exit_px,"entry_kind":pos["entry_kind"],"exit_kind":"TAKER",
                    "exit_reason":reason,"quantity_btc":pos["quantity_btc"],"notional_usd":pos["notional"],
                    "gross_usd":costs.gross_usd,"fees_usd":costs.fees_usd,"slippage_usd":costs.slippage_usd,
                    "funding_usd":costs.funding_usd,"net_usd":costs.net_usd,"gross_bps":costs.gross_bps,
                    "net_bps":costs.net_bps,"funding_status":costs.funding_status,"paper_only":True,"real_orders":False}
                self.trades.append(trade); self.position=None
                return {"signal":signal,"trade":trade,"position":None,"real_orders":False}
            return {"signal":signal,"trade":None,"position":dict(pos),"real_orders":False}
        if signal["action"] not in ("LONG","SHORT"):
            return {"signal":signal,"trade":None,"position":None,"reason":"SIGNAL_ABSTAIN","real_orders":False}
        notional=float(self.config.get("paper_notional_usd",100))
        qty=floor_lots(notional/float((bid+ask)/2))
        if qty<LOT_BTC:
            return {"signal":signal,"trade":None,"position":None,"reason":"BELOW_MINIMUM_LOT","real_orders":False}
        actual_notional=qty*float((bid+ask)/2)
        gross_assumption=float(self.config.get("paper_target_bps",20))
        rough=calculate(actual_notional,gross_assumption,"MAKER","TAKER",
            spread_bps=float(signal.get("spread_bps") or 0)/2,
            slippage_bps=float(self.config.get("taker_slippage_bps",1)),
            adverse_selection_bps=float(self.config.get("maker_adverse_selection_bps",1.5)))
        if rough.net_bps<float(self.config.get("min_net_edge_bps",1)):
            return {"signal":signal,"trade":None,"position":None,"reason":"COST_FLOOR","real_orders":False}
        side=signal["action"]
        limit=round_tick(bid if side=="LONG" else ask,side="BUY" if side=="LONG" else "SELL")
        p=float(self.config.get("maker_fill_probability",.35))
        queue=float(self.config.get("maker_queue_fraction",.5))
        p=max(0,min(1,p*(1-queue*.5)))
        last_trade=state.get("last_trade") or {}
        trade_px=float(last_trade.get("price") or 0)
        plausible=(trade_px>0 and ((side=="LONG" and trade_px<=limit) or (side=="SHORT" and trade_px>=limit)))
        p_eff=min(0.95,p+(0.35 if plausible else 0))
        if self.rng.random()>=p_eff:
            return {"signal":signal,"trade":None,"position":None,"reason":"MAKER_MISSED_OR_QUEUED","fill_probability":p_eff,"real_orders":False}
        self.position={"side":side,"entry_ts":now,"entry_px":limit,"entry_kind":"MAKER","quantity_btc":qty,
                       "notional":actual_notional,"adverse_bps":float(self.config.get("maker_adverse_selection_bps",1.5)),
                       "funding_bps":0.0,"funding_status":"UNKNOWN","funding_settlements":[]}
        return {"signal":signal,"trade":None,"position":dict(self.position),"fill_probability":p_eff,"real_orders":False}

def main():
    e=PaperEngine(); persisted=read(PAPER_STATE,{})
    e.position=persisted.get("position")
    last_snapshot=None
    OUT.parent.mkdir(parents=True,exist_ok=True)
    try:
        while True:
            state=read(STATE,{})
            snapshot=state.get("updated_at_epoch")
            if snapshot is not None and snapshot!=last_snapshot:
                last_snapshot=snapshot
                live=read(ROOT/"data/live_market_state.json",{})
                try: rate=float(live["funding_rate"]) if live.get("funding_rate") is not None else None
                except (TypeError,ValueError): rate=None
                result=e.step(state,read(CANDLES,[]),funding_rate=rate)
                with OUT.open("a") as f: f.write(json.dumps({"ts":time.time(),**result},separators=(",",":"))+"\n")
                tmp=PAPER_STATE.with_suffix(".tmp")
                tmp.write_text(json.dumps({"position":e.position,"paper_only":True,"real_orders":False},separators=(",",":")))
                os.replace(tmp,PAPER_STATE)
            time.sleep(0.25)
    except KeyboardInterrupt:
        return
if __name__=="__main__": main()
