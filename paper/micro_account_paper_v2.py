"""Micro-account paper engine v2: continuous, fail-closed, no exchange orders."""
from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data/processed/micro_account_paper_v2_state.json"
LOG=ROOT/"data/processed/micro_account_paper_v2.jsonl"
START=2.0; TARGET=4.0; RISK=0.10; MAX_LOSS=0.20; LEV=3.0
FEE_BPS=11.0; SLIP_BPS=4.0; ADV_BPS=3.0; MIN_BTC=0.001

def load():
    if STATE.exists():
        try:return json.loads(STATE.read_text())
        except Exception:pass
    return {"equity":START,"peak":START,"trades":0,"wins":0,"losses":0,
            "realized_pnl":0.0,"consecutive_losses":0,"status":"ACTIVE"}

def save(s):
    STATE.write_text(json.dumps(s,indent=2))
def log(x):
    with LOG.open("a") as f:f.write(json.dumps(x)+"\n")

def simulate(s, side, entry, stop, target, btc_price=None):
    if s["status"]!="ACTIVE": return {"accepted":False,"reason":"ACCOUNT_NOT_ACTIVE"}
    if entry<=0 or stop<=0 or target<=0:return {"accepted":False,"reason":"INVALID_PRICES"}
    if s["equity"]>=TARGET:return {"accepted":False,"reason":"TARGET_REACHED"}
    if s["equity"]<=0:return {"accepted":False,"reason":"RUIN"}
    stop_pct=abs(entry-stop)/entry
    if stop_pct<=0 or stop_pct>0.05:return {"accepted":False,"reason":"STOP_CONSTRAINT"}
    notional=min(s["equity"]*LEV,(s["equity"]*RISK)/stop_pct)
    contracts=int(notional/(MIN_BTC*(btc_price or entry)))
    if contracts<1:return {"accepted":False,"reason":"MINIMUM_CONTRACT_UNREACHABLE"}
    qty=contracts*MIN_BTC
    exit_px=target
    gross=(exit_px-entry)*qty if side=="LONG" else (entry-exit_px)*qty
    cost=(entry+exit_px)*qty*(FEE_BPS+SLIP_BPS+ADV_BPS)/20000
    pnl=gross-cost
    neweq=s["equity"]+pnl
    s["equity"]=neweq;s["peak"]=max(s["peak"],neweq);s["trades"]+=1
    s["realized_pnl"]+=pnl
    if pnl>0:s["wins"]+=1;s["consecutive_losses"]=0
    else:s["losses"]+=1;s["consecutive_losses"]+=1
    dd=1-neweq/s["peak"] if s["peak"] else 1
    if dd>=MAX_LOSS or s["consecutive_losses"]>=2:s["status"]="HALTED_RISK"
    if neweq>=TARGET:s["status"]="TARGET_REACHED"
    event={"ts":time.time(),"event":"MICRO_TRADE","side":side,"entry":entry,
           "stop":stop,"target":target,"contracts":contracts,"pnl":pnl,
           "equity":neweq,"status":s["status"],"paper_only":True}
    log(event);save(s);return event

if __name__=="__main__":
 s=load();save(s);print(json.dumps(s,indent=2))
