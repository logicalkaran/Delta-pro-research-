"""Single authoritative Delta India BTCUSD research paper cost model."""
from dataclasses import dataclass
import math
MAKER_BPS=MAKER_FEE_BPS=2.0*1.18
TAKER_BPS=TAKER_FEE_BPS=5.0*1.18
TICK_USD=TICK_SIZE=0.50
LOT_BTC=LOT_SIZE_BTC=0.001
FUNDING_INTERVAL_SECONDS=28800

def _finite(x, default=0.0):
    try:
        y=float(x); return y if math.isfinite(y) else default
    except (TypeError,ValueError): return default

def round_tick(price, tick=TICK_USD, side=None):
    # Directional price rounding preserves a passive limit: buy down, sell up.
    if side in ("BUY","LONG","down"): n=math.floor(_finite(price)/tick+1e-12)
    elif side in ("SELL","SHORT","up"): n=math.ceil(_finite(price)/tick-1e-12)
    else: n=round(_finite(price)/tick)
    return round(n*tick,8)

def round_lots(qty): return math.floor(max(0,_finite(qty))/LOT_BTC+1e-12)*LOT_BTC

@dataclass(frozen=True)
class CostBreakdown:
    gross_usd:float; fees_usd:float; slippage_usd:float; funding_usd:float; net_usd:float
    gross_bps:float; fees_bps:float; slippage_bps:float; funding_bps:float; net_bps:float; funding_status:str

def calculate(notional_usd,gross_bps,entry_kind="TAKER",exit_kind="TAKER",spread_bps=0.0,
              slippage_bps=0.0,adverse_selection_bps=0.0,funding_bps=None,funding_status=None):
    n=max(0,_finite(notional_usd)); gross=_finite(gross_bps)
    fees=(MAKER_BPS if str(entry_kind).upper()=="MAKER" else TAKER_BPS)+(MAKER_BPS if str(exit_kind).upper()=="MAKER" else TAKER_BPS)
    # Spread is round-trip total; do not add it when executable-side fills already include it.
    slip=max(0,_finite(spread_bps))+2*max(0,_finite(slippage_bps))+2*max(0,_finite(adverse_selection_bps))
    fund=_finite(funding_bps) if funding_bps is not None else 0.0
    status=funding_status or ("OBSERVED" if funding_bps is not None else "UNKNOWN_UNAVAILABLE_ZERO_ASSUMED")
    net=gross-fees-slip-fund; usd=lambda b:n*b/10000
    return CostBreakdown(usd(gross),usd(fees),usd(slip),usd(fund),usd(net),gross,fees,slip,fund,net,status)

def funding_crossings(entry_ts,exit_ts,interval=FUNDING_INTERVAL_SECONDS):
    a,b=_finite(entry_ts),_finite(exit_ts); interval=int(interval)
    if b<=a or interval<=0:return []
    t=(math.floor(a/interval)+1)*interval; out=[]
    while t<=b:out.append(t);t+=interval
    return out

def funding_cost_bps(position_side,funding_rate,crossings):
    return (1 if str(position_side).upper() in ("LONG","BUY") else -1)*_finite(funding_rate)*10000*int(crossings)

def calculate_costs(*,side,entry_price,exit_price,quantity_btc,entry_maker=False,exit_maker=False,
                    slippage_bps=1.0,adverse_selection_bps=0.5,funding_rate=None,funding_mark=None,crossed_funding=False):
    q=round_lots(quantity_btc)
    if side not in ("LONG","SHORT") or q<=0:raise ValueError("valid side and lot-rounded quantity required")
    direction=1 if side=="LONG" else -1
    notional=((entry_price+exit_price)/2)*q
    gross=direction*(exit_price-entry_price)*q/notional*10000
    f_bps=funding_cost_bps(side,funding_rate,1) if crossed_funding and funding_rate is not None and funding_mark is not None else None
    return calculate(notional,gross,"MAKER" if entry_maker else "TAKER","MAKER" if exit_maker else "TAKER",
        slippage_bps=slippage_bps,adverse_selection_bps=adverse_selection_bps,funding_bps=f_bps,
        funding_status="OBSERVED" if f_bps is not None else ("UNKNOWN_UNAVAILABLE_ZERO_ASSUMED" if crossed_funding else "NOT_CROSSED"))
