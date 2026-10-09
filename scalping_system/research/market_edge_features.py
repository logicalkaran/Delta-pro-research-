"""Canonical microstructure feature enrichment for research.
No execution authority; transforms already-captured one-second observations."""
from __future__ import annotations
import math

def enrich(r, prev=None):
    prev=prev or {}
    mid=float(r.get('mid',0) or 0); spread=float(r.get('spread_bps',0) or 0)
    imb5=float(r.get('imb5',0) or 0); imb10=float(r.get('imb10',0) or 0)
    d5=float(r.get('delta5',0) or 0); d30=float(r.get('delta30',0) or 0); d60=float(r.get('delta60',0) or 0)
    ret5=float(r.get('ret5',0) or 0); ret30=float(r.get('ret30',0) or 0); ret60=float(r.get('ret60',0) or 0)
    cvd=float(r.get('cvd',0) or 0); cvds=float(r.get('cvd_slope30',0) or 0)
    b=float(r.get('depth5_ratio',1) or 1); a=float(r.get('depth10_ratio',1) or 1)
    # Pressure-vs-capacity: aggressive flow normalized by displayed liquidity.
    pressure=(d5 + d30*0.5)/(1.0+abs(math.log(max(b,1e-9))))
    liquidity=(imb5*0.55+imb10*0.45)
    fragility=min(1.0,abs(imb5-imb10)+max(0.0,spread-float(prev.get('spread_bps',spread) or spread))/10.0)
    spread_change=spread-float(prev.get('spread_bps',spread) or spread)
    flow_accel=d5-0.5*d30
    momentum=(ret5*0.5+ret30*0.3+ret60*0.2)
    divergence=(d30/100.0)-ret30
    cvd_change=cvd-float(prev.get('cvd',cvd) or cvd)
    return {**r,
      'ofi_proxy':liquidity*abs(d5), 'pressure_capacity':pressure,
      'liquidity_state':liquidity, 'liquidity_fragility':fragility,
      'spread_change_bps':spread_change, 'flow_acceleration':flow_accel,
      'momentum_composite':momentum, 'flow_price_divergence':divergence,
      'cvd_change':cvd_change, 'depth_asymmetry':math.tanh(math.log(max(a,1e-9))),
      'toxicity_score':min(1.0,0.5*abs(pressure)+0.3*fragility+0.2*min(1,abs(spread_change)/2.0)),
    }
