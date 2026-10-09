from strategy.professional_alpha_router_v1 import route
a=route(base_action="LONG",score=9,data_age_s=0.5,spread_bps=1,session_ok=True,cross_validated=True)
assert a["action"]=="LONG"
b=route(base_action="LONG",score=9,data_age_s=0.5,spread_bps=1,session_ok=True,cross_validated=False)
assert b["action"]=="NO_TRADE"
print("PROFESSIONAL ALPHA ROUTER TEST: PASS")