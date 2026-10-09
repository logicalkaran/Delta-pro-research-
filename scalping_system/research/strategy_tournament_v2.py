"""BTC strategy tournament research engine. No orders; common conservative cost model."""
from pathlib import Path
import json,time,statistics
ROOT=Path(__file__).resolve().parents[1]; STATE=ROOT/"data/live_microstructure_state.json"; CANDLES=ROOT/"data/live_candles.json"; OUT=ROOT/"data/processed/strategy_tournament_v2.json"
FEE=5; SLIP=4; ADV=3; COST_BPS=FEE+SLIP+ADV
def f(x,d=0):
 try:return float(x)
 except:return d
def load(p):
 try:return json.loads(p.read_text())
 except:return None
def main():
 s=load(STATE) or {}; cs=load(CANDLES) or []; ob=s.get("order_book",{}); px=f(ob.get("mid_price")); fresh=f(s.get("quality",{}).get("fresh_seconds"),999); d5=f(s.get("windows",{}).get("5",{}).get("delta_pct")); d30=f(s.get("windows",{}).get("30",{}).get("delta_pct")); imb=f(ob.get("imbalance_5")); r5=f(s.get("price",{}).get("5",{}).get("return_pct")); spread=f(ob.get("spread"),999)/px*10000 if px else 999
 strategies={
 "ABSORPTION": d5<=-.10 or d5>=.10,
 "BREAKOUT_FLOW": abs(d5)>=.20 and abs(r5)>=.03,
 "FAILED_BREAKOUT": abs(d5)>=.10 and abs(r5)<.03 and abs(imb)>=.08,
 "FLOW_CONTINUATION": abs(d5)>=.12 and ((d5>0 and d30>0) or (d5<0 and d30<0)),
 "FLOW_MEAN_REVERSION": abs(d5)>=.12 and ((d5>0 and r5<0) or (d5<0 and r5>0)),
 "ORDERBOOK_IMBALANCE": abs(imb)>=.12,
 "DELTA_OI_DIVERGENCE": abs(d5)>=.10 and abs(d30)<=.05,
 "LEVEL_REACTION": bool(cs) and abs(r5)<.03,
 "MOMENTUM": abs(r5)>=.05 and abs(d5)>=.10,
 "VOLATILITY_EXPANSION": bool(cs) and abs(r5)>=.08,
 "MULTI_CONFLUENCE": abs(d5)>=.12 and abs(imb)>=.08 and ((d5>0 and d30>=0) or (d5<0 and d30<=0))}
 regime="HIGH_VOL" if abs(r5)>=.08 else ("LOW_VOL" if abs(r5)<.02 else "NORMAL_VOL")
 rows=[]
 for name,active in strategies.items():
  rows.append({"strategy":name,"active":active,"direction":"LONG" if d5>0 else "SHORT" if d5<0 else "NONE","regime":regime,"price":px,"delta5":d5,"delta30":d30,"imbalance":imb,"return5":r5,"spread_bps":spread,"fresh_seconds":fresh,"cost_bps":COST_BPS})
 report={"updated_at":time.time(),"regime":regime,"market":{"price":px,"spread_bps":spread,"fresh_seconds":fresh,"delta5":d5,"delta30":d30,"imbalance":imb,"return5":r5},"strategies":rows,"cost_model":{"fee_bps":FEE,"slippage_bps":SLIP,"adverse_bps":ADV},"paper_only":True,"real_orders":False,"promotion_allowed":False}
 OUT.write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
if __name__=="__main__":main()
