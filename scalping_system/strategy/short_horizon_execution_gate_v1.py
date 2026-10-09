"""Calibration-aware short-horizon execution gate. Paper-only."""
from dataclasses import dataclass
import json
from pathlib import Path
@dataclass(frozen=True)
class GateDecision:
    allowed:bool; score:float; reason:str; horizon:int; forecast_direction:str; level_price:float|None; distance_atr:float|None
def _calibration(root):
    try:return json.loads((Path(root)/"data/processed/short_horizon_calibration_v2.json").read_text()).get("horizons",{})
    except:return {}
def gate(pred,side,entry,stop,cost_bps=12,root=None):
    fs=list(pred.forecasts)
    if not fs:return GateDecision(False,0,"NO_FORECAST",0,"NEUTRAL",None,None)
    wanted="UP" if side=="LONG" else "DOWN"; cal=_calibration(root) if root else {}; viable=[]
    for x in fs:
        if x.direction!=wanted or x.confidence<.60: continue
        row=cal.get(str(x.minutes),{}); n=int(row.get("samples",0) or 0); acc=row.get("directional_accuracy"); edge=row.get("mean_aligned_move_pct")
        if n<30 or acc is None or float(acc)<.52 or edge is None or float(edge)<.015: continue
        viable.append((x,n,float(acc),float(edge)))
    if not viable:return GateDecision(False,0,"FORECAST_NOT_CALIBRATED",0,fs[0].direction,None,None)
    x,n,acc,edge=max(viable,key=lambda z:(z[2],z[3],z[1]))
    level=pred.support[0] if side=="LONG" and pred.support else pred.resistance[0] if side=="SHORT" and pred.resistance else None
    if level is None:return GateDecision(False,0,"NO_RELEVANT_LEVEL",x.minutes,x.direction,None,None)
    risk=max(abs(entry-stop),entry*.0005); dist=abs(entry-level)/risk
    if dist>2.5:return GateDecision(False,0,"LEVEL_TOO_FAR",x.minutes,x.direction,level,round(dist,3))
    if abs(x.expected_return_pct)<cost_bps/100*1.25:return GateDecision(False,0,"EXPECTED_MOVE_BELOW_COST_BUFFER",x.minutes,x.direction,level,round(dist,3))
    score=min(100,40+x.confidence*25+(acc-.5)*100+edge*100+min(15,abs(x.expected_return_pct)*80)+min(10,max(0,2.5-dist)*4))
    return GateDecision(True,round(score,2),"SHORT_HORIZON_CONFIRMED",x.minutes,x.direction,level,round(dist,3))
