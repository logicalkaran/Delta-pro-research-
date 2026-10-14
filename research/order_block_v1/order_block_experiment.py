#!/usr/bin/env python3
"""Isolated read-only Order Block research for Delta BTCUSD 15m candles."""
from __future__ import annotations
import argparse, csv, json, math, sys, time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
@dataclass(frozen=True)
class Candle:
    timestamp:int; open:float; high:float; low:float; close:float; volume:float=0.0
@dataclass
class Zone:
    side:str; low:float; high:float; formed_index:int; formed_timestamp:int; source_index:int
    used:bool=False; invalidated:bool=False
@dataclass
class Trade:
    side:str; zone_formed_at:int; signal_at:int; entry_at:int; exit_at:int
    entry:float; stop:float; target:float; exit:float; gross_r:float; net_r:float
    exit_reason:str; bars_held:int
def validate_candles(candles):
    unique={c.timestamp:c for c in candles}
    rows=[unique[k] for k in sorted(unique)]
    for c in rows:
        if not all(math.isfinite(x) for x in (c.open,c.high,c.low,c.close,c.volume)): raise ValueError("non-finite candle")
        if c.low>min(c.open,c.close) or c.high<max(c.open,c.close) or c.low>c.high: raise ValueError("invalid OHLC at %s"%c.timestamp)
    return rows
def aggregate_1m_to_15m(rows):
    minute={}
    for r in rows:
        ts=int(r.get("timestamp",r.get("time",r.get("t",0))))
        if ts>0: minute[ts]=Candle(ts,float(r["open"]),float(r["high"]),float(r["low"]),float(r["close"]),float(r.get("volume",0) or 0))
    buckets={}
    for ts,c in minute.items(): buckets.setdefault(ts-ts%900,[]).append(c)
    out=[]
    for start,bars in sorted(buckets.items()):
        bars.sort(key=lambda x:x.timestamp)
        if [b.timestamp for b in bars]!=list(range(start,start+900,60)): continue
        out.append(Candle(start,bars[0].open,max(b.high for b in bars),min(b.low for b in bars),bars[-1].close,sum(b.volume for b in bars)))
    return out
def fetch_history(days=180,symbol="BTCUSD"):
    from execution.delta_client import DeltaPublicClient
    client=DeltaPublicClient(timeout=20); end=int(time.time()); start=end-int(days)*86400
    found={}; cursor=start; chunk=7*86400
    while cursor<end:
        stop=min(end,cursor+chunk); response=client.get_candles(symbol,"15m",cursor,stop)
        rows=response.get("result",[]) if isinstance(response,dict) else []
        for r in rows:
            ts=int(r.get("time",r.get("timestamp",0)))
            if ts>0 and start<=ts<end: found[ts]=Candle(ts,float(r["open"]),float(r["high"]),float(r["low"]),float(r["close"]),float(r.get("volume",0) or 0))
        print("fetch %s..%s rows=%d unique=%d"%(datetime.fromtimestamp(cursor,timezone.utc).date(),datetime.fromtimestamp(stop,timezone.utc).date(),len(rows),len(found)),flush=True)
        cursor=stop; time.sleep(.08)
    candles=validate_candles(list(found.values()))
    if not candles: raise RuntimeError("Delta returned no BTCUSD 15m candles.")
    return candles
def write_csv(path,candles):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["timestamp","open","high","low","close","volume"]); w.writeheader()
        for c in candles: w.writerow(asdict(c))
def read_csv(path):
    with path.open(newline="",encoding="utf-8") as f:
        candles=[Candle(int(float(r.get("timestamp",r.get("time","")))),float(r["open"]),float(r["high"]),float(r["low"]),float(r["close"]),float(r.get("volume") or 0)) for r in csv.DictReader(f)]
    return validate_candles(candles)
def atr(candles,period=14):
    tr=[]
    for i,c in enumerate(candles): tr.append(c.high-c.low if i==0 else max(c.high-c.low,abs(c.high-candles[i-1].close),abs(c.low-candles[i-1].close)))
    out=[None]*len(candles)
    for i in range(period-1,len(candles)): out[i]=sum(tr[i-period+1:i+1])/period
    return out
def detect_zones(candles,atrs,swing=2,lookback=5,displacement_atr=.8):
    created=[[] for _ in candles]; last_high=None; last_low=None
    for i,c in enumerate(candles):
        pivot=i-swing
        if pivot>=swing:
            win=candles[pivot-swing:pivot+swing+1]; p=candles[pivot]
            if p.high==max(x.high for x in win) and sum(x.high==p.high for x in win)==1: last_high=p.high
            if p.low==min(x.low for x in win) and sum(x.low==p.low for x in win)==1: last_low=p.low
        a=atrs[i]
        if a is None or a<=0 or abs(c.close-c.open)<displacement_atr*a: continue
        side="long" if c.close>c.open and last_high is not None and c.close>last_high else "short" if c.close<c.open and last_low is not None and c.close<last_low else None
        if side is None: continue
        source=None
        for j in range(i-1,max(-1,i-lookback-1),-1):
            p=candles[j]
            if (side=="long" and p.close<p.open) or (side=="short" and p.close>p.open): source=j; break
        if source is None: continue
        o=candles[source]
        low,high=(o.low,max(o.low,o.open)) if side=="long" else (min(o.high,o.open),o.high)
        if high>low: created[i].append(Zone(side,low,high,i,c.timestamp,source))
    return created
def simulate(candles,fee_bps_per_side=5.0,slippage_bps_per_side=2.0,risk_reward=2.0,max_hold_bars=48,start_index=0,end_index=None,min_risk_bps=0.0):
    end_index=len(candles) if end_index is None else min(end_index,len(candles))
    if end_index-start_index<40: return []
    atrs=atr(candles); created=detect_zones(candles,atrs); zones=[]; trades=[]; i=max(start_index,1)
    cost_fraction=2*(fee_bps_per_side+slippage_bps_per_side)/10000
    while i<end_index-1:
        zones.extend(created[i]); c=candles[i]
        # Expire stale zones after 96 bars (24h) and discard closed zones to bound CPU/memory.
        zones=[z for z in zones if not z.used and not z.invalidated and i-z.formed_index<=96]
        for z in zones:
            if not z.used and not z.invalidated and i>z.formed_index and ((z.side=="long" and c.close<z.low) or (z.side=="short" and c.close>z.high)): z.invalidated=True
        candidate=None
        for z in reversed(zones):
            if z.used or z.invalidated or i<=z.formed_index: continue
            if z.side=="long" and c.low<=z.high and c.high>=z.low and c.close>c.open: candidate=z; break
            if z.side=="short" and c.high>=z.low and c.low<=z.high and c.close<c.open: candidate=z; break
        if candidate is None: i+=1; continue
        z=candidate; entry_i=i+1; ec=candles[entry_i]; entry=ec.open; a=atrs[i] or (z.high-z.low); buf=max(a*.1,entry*.0001)
        stop=z.low-buf if z.side=="long" else z.high+buf; risk=entry-stop if z.side=="long" else stop-entry
        if risk<=0 or not math.isfinite(risk): z.used=True; i+=1; continue
        # Optional research filter: skip entries whose stop distance is too narrow
        # relative to price, because fixed transaction costs consume more R.
        if min_risk_bps>0 and risk/entry*10000<min_risk_bps:
            i+=1; continue
        target=entry+risk*risk_reward if z.side=="long" else entry-risk*risk_reward
        xi=None; xp=None; reason="time"; final=min(end_index-1,entry_i+max_hold_bars)
        for k in range(entry_i,final+1):
            b=candles[k]; sh,th=(b.low<=stop,b.high>=target) if z.side=="long" else (b.high>=stop,b.low<=target)
            if sh: xi=k; xp=min(b.open,stop) if z.side=="long" else max(b.open,stop); reason="stop"; break
            if th: xi=k; xp=max(b.open,target) if z.side=="long" else min(b.open,target); reason="target"; break
        if xi is None: xi=final; xp=candles[xi].close
        raw=xp-entry if z.side=="long" else entry-xp; gr=raw/risk; nr=gr-entry*cost_fraction/risk
        trades.append(Trade(z.side,z.formed_timestamp,c.timestamp,ec.timestamp,candles[xi].timestamp,entry,stop,target,float(xp),gr,nr,reason,xi-entry_i+1))
        z.used=True; i=xi+1
    return trades
def metrics(trades):
    if not trades: return {"trades":0,"win_rate":None,"gross_expectancy_r":None,"gross_profit_factor":None,"net_expectancy_r":None,"net_profit_factor":None,"avg_cost_r":None,"avg_risk_bps":None,"net_total_r":0.0,"max_drawdown_r":0.0,"long_trades":0,"short_trades":0}
    ns=[t.net_r for t in trades]; gp=sum(x for x in ns if x>0); gl=-sum(x for x in ns if x<0); eq=peak=dd=0.0
    for x in ns: eq+=x; peak=max(peak,eq); dd=max(dd,peak-eq)
    gross=[t.gross_r for t in trades]; gpos=sum(x for x in gross if x>0); gneg=-sum(x for x in gross if x<0)
    return {"trades":len(trades),"win_rate":sum(x>0 for x in ns)/len(ns),"gross_expectancy_r":sum(gross)/len(gross),"gross_profit_factor":gpos/gneg if gneg>0 else None,"net_expectancy_r":sum(ns)/len(ns),"net_profit_factor":gp/gl if gl>0 else None,"avg_cost_r":sum(t.gross_r-t.net_r for t in trades)/len(trades),"avg_risk_bps":sum(abs(t.entry-t.stop)/t.entry*10000 for t in trades)/len(trades),"net_total_r":sum(ns),"max_drawdown_r":dd,"long_trades":sum(t.side=="long" for t in trades),"short_trades":sum(t.side=="short" for t in trades)}
def render_report(r):
    fmt=lambda v:"n/a" if v is None else ("%.4f"%v if isinstance(v,float) else str(v))
    lines=["# Order Block Research v1 — BTCUSD 15m","","**Mode:** isolated research-only local paper simulation. **Live execution:** disabled.","","- Source: "+r["source"],"- Candles: %d"%r["candles"],"- UTC range: %s to %s"%(r["first_utc"],r["last_utc"]),"- Cost assumption: %.2f bps fee + %.2f bps slippage per side"%(r["fee_bps_per_side_assumption"],r["slippage_bps_per_side_assumption"]),"- Entry: next candle open after retest/confirmation; target 2R; max hold 48 bars.","- Same-bar stop/target collision resolves stop-first; one position at a time.","- Split: isolated chronological first 70% exploratory, final 30% holdout; zones and positions reset.",""]
    for title,key in [("Training period","train"),("Out-of-sample holdout","holdout"),("All sample (descriptive only)","all_sample_descriptive")]:
        m=r[key]; lines += ["## "+title,"","- Trades: "+str(m["trades"]),"- Net win rate: "+fmt(m["win_rate"]),"- Gross expectancy (R/trade): "+fmt(m.get("gross_expectancy_r")),"- Net expectancy (R/trade): "+fmt(m["net_expectancy_r"]),"- Gross profit factor: "+fmt(m.get("gross_profit_factor")),"- Net profit factor: "+fmt(m["net_profit_factor"]),"- Average cost (R/trade): "+fmt(m.get("avg_cost_r")),"- Average risk width (bps): "+fmt(m.get("avg_risk_bps")),"- Net total (R): "+fmt(m["net_total_r"]),"- Max drawdown (R): "+fmt(m["max_drawdown_r"]),"- Long / short: %d / %d"%(m["long_trades"],m["short_trades"]),""] 
    lines += ["## Cost sensitivity (all sample)","","| Fee bps/side | Slippage bps/side | Net expectancy (R/trade) | Net profit factor |","|---:|---:|---:|---:|"]
    for row in r["cost_sensitivity"]:
        m=row["all_sample"]
        lines.append("| %.1f | %.1f | %.4f | %s |"%(row["fee_bps_per_side"],row["slippage_bps_per_side"],m["net_expectancy_r"],fmt(m["net_profit_factor"])))
    lines += ["","## Validation warnings",""]+["- "+x for x in r["validation_warnings"]]+["","This is not live-readiness approval or a claim of future profitability.",""]
    return "\n".join(lines)
def save_report(out,candles,trades,fee,slip,days,source):
    out.mkdir(parents=True,exist_ok=True); split=int(len(candles)*.7)
    # Isolate partitions: no open positions or pre-split zones cross the boundary.
    train=simulate(candles,fee_bps_per_side=fee,slippage_bps_per_side=slip,start_index=0,end_index=split)
    test=simulate(candles,fee_bps_per_side=fee,slippage_bps_per_side=slip,start_index=split,end_index=len(candles))
    gap_count=sum((b.timestamp-a.timestamp)!=900 for a,b in zip(candles,candles[1:]))
    sensitivity=[]
    for f,s in [(2.0,1.0),(5.0,2.0),(8.0,4.0)]:
        ts=trades if (f,s)==(fee,slip) else simulate(candles,fee_bps_per_side=f,slippage_bps_per_side=s)
        sensitivity.append({"fee_bps_per_side":f,"slippage_bps_per_side":s,"all_sample":metrics(ts)})
    r={"experiment":"order_block_v1","mode":"research_only_local_paper_simulation","live_execution_enabled":False,"symbol":"BTCUSD","timeframe":"15m","direction":"both","source":source,"requested_history_days":days,"candles":len(candles),"first_utc":datetime.fromtimestamp(candles[0].timestamp,timezone.utc).isoformat(),"last_utc":datetime.fromtimestamp(candles[-1].timestamp,timezone.utc).isoformat(),"fee_bps_per_side_assumption":fee,"slippage_bps_per_side_assumption":slip,"risk_reward":2.0,"max_hold_bars":48,"walk_forward_split":"isolated chronological first 70% / final 30%; zones/positions reset at split","data_gap_count":gap_count,"train":metrics(train),"holdout":metrics(test),"all_sample_descriptive":metrics(trades),"cost_sensitivity":sensitivity,"validation_warnings":[]}
    if len(candles)<1000:r["validation_warnings"].append("Fewer than 1,000 candles; evidence is insufficient.")
    if len(test)<30:r["validation_warnings"].append("Fewer than 30 holdout trades; inference is too sparse.")
    if not test:r["validation_warnings"].append("No holdout trades were generated.")
    if gap_count:r["validation_warnings"].append("%d missing/irregular 15m intervals detected."%gap_count)
    if metrics(test)["net_expectancy_r"] is not None and metrics(test)["net_expectancy_r"]<=0:r["validation_warnings"].append("Holdout net expectancy is non-positive; do not promote this rule set.")
    if metrics(test)["avg_cost_r"] is not None and metrics(test)["gross_expectancy_r"] is not None and metrics(test)["avg_cost_r"]>=metrics(test)["gross_expectancy_r"]:r["validation_warnings"].append("Modeled transaction costs exceed holdout gross expectancy; the current edge does not cover costs.")
    if metrics(trades)["gross_expectancy_r"] is not None and metrics(trades)["gross_expectancy_r"]<=0:r["validation_warnings"].append("All-sample gross expectancy is non-positive before costs.")
    (out/"paper_trades.jsonl").write_text("".join(json.dumps(asdict(t),separators=(",",":"))+"\n" for t in trades),encoding="utf-8")
    (out/"report.json").write_text(json.dumps(r,indent=2)+"\n",encoding="utf-8"); (out/"report.md").write_text(render_report(r),encoding="utf-8")
    return r
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--days",type=int,default=180); p.add_argument("--input",type=Path); p.add_argument("--fee-bps-per-side",type=float,default=5.0); p.add_argument("--slippage-bps-per-side",type=float,default=2.0); p.add_argument("--output-dir",type=Path,default=HERE/"output"); a=p.parse_args()
    if not 1<=a.days<=730:p.error("--days must be between 1 and 730")
    if a.fee_bps_per_side<0 or a.slippage_bps_per_side<0:p.error("costs cannot be negative")
    if a.input:candles=read_csv(a.input); source=str(a.input)
    else:candles=validate_candles(fetch_history(a.days)); source="Delta public candles API (read-only)"; write_csv(HERE/"btcusd_15m.csv",candles)
    if len(candles)<40:raise SystemExit("Insufficient data: %d candles; need at least 40."%len(candles))
    trades=simulate(candles,fee_bps_per_side=a.fee_bps_per_side,slippage_bps_per_side=a.slippage_bps_per_side)
    r=save_report(a.output_dir,candles,trades,a.fee_bps_per_side,a.slippage_bps_per_side,a.days,source)
    print(json.dumps(r,indent=2)); print("Report:",a.output_dir/"report.md"); print("Research paper ledger:",a.output_dir/"paper_trades.jsonl"); print("LIVE EXECUTION: DISABLED")
if __name__=="__main__":main()
