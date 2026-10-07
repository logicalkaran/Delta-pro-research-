"""Create a guarded BTCUSD trade plan from a price and direction.
No API key, account access, or order submission is performed.
"""
import argparse, json
from live_trade_guard import TradePlan, GuardConfig, round_tick, validate

p=argparse.ArgumentParser()
p.add_argument("--side",required=True,choices=["LONG","SHORT"])
p.add_argument("--entry",required=True,type=float)
p.add_argument("--risk",default=250.0,type=float,help="stop distance in USD")
p.add_argument("--rr",default=2.0,type=float)
a=p.parse_args()

entry=round_tick(a.entry)
risk=round_tick(a.risk)
target_dist=round_tick(risk*a.rr)
if a.side=="LONG":
    stop=round_tick(entry-risk); target=round_tick(entry+target_dist)
else:
    stop=round_tick(entry+risk); target=round_tick(entry-target_dist)

cfg=GuardConfig(rr=a.rr)
plan=TradePlan(a.side,entry,stop,target,1)
ok,detail=validate(plan,cfg)
print(json.dumps({
    "status":"READY" if ok else "BLOCKED",
    "execution":"NOT_SUBMITTED",
    "plan":plan.__dict__,
    "risk_check":detail
},indent=2))
