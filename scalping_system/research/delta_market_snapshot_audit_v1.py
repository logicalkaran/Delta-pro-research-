#!/usr/bin/env python3
"""Offline data-quality and microstructure summary for a harvested Delta snapshot."""
from __future__ import annotations
import argparse, json, math, hashlib, tempfile, os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any


def number(x: Any) -> float | None:
    try:
        y=float(x)
        return y if math.isfinite(y) else None
    except (TypeError,ValueError): return None


def candle_audit(rows: list[dict[str,Any]], expected_step: int, *, allow_nonpositive: bool = False) -> dict[str,Any]:
    clean=[]; bad=0
    for r in rows:
        t=number(r.get('time',r.get('timestamp'))); o=number(r.get('open')); h=number(r.get('high')); l=number(r.get('low')); c=number(r.get('close'))
        if t is None or None in (o,h,l,c) or (not allow_nonpositive and min(o,h,l,c)<=0) or h<max(o,l,c) or l>min(o,h,c): bad+=1; continue
        clean.append((int(t),o,h,l,c,number(r.get('volume'))))
    clean.sort(key=lambda x:x[0])
    times=[x[0] for x in clean]
    gaps=sum(1 for a,b in zip(times,times[1:]) if b-a>expected_step*1.5)
    returns=[]
    for a,b in zip(clean,clean[1:]):
        if not allow_nonpositive and a[4]>0 and b[4]>0: returns.append((b[4]/a[4]-1)*10000)
    mean=sum(returns)/len(returns) if returns else None
    std=(sum((x-mean)**2 for x in returns)/max(1,len(returns)-1))**0.5 if len(returns)>1 and mean is not None else None
    volumes=[x[5] for x in clean if x[5] is not None and x[5]>=0]
    closes=[x[4] for x in clean]
    return {'rows_received':len(rows),'rows_valid':len(clean),'invalid_rows':bad,'gap_count':gaps,'first_ts':times[0] if times else None,'last_ts':times[-1] if times else None,'return_count':len(returns),'mean_return_bps_per_bar':mean,'std_return_bps_per_bar':std,'close_first':clean[0][4] if clean else None,'close_last':clean[-1][4] if clean else None,'change_pct':(clean[-1][4]/clean[0][4]-1)*100 if len(clean)>1 and clean[0][4]>0 and not allow_nonpositive else None,'close_mean':sum(closes)/len(closes) if closes else None,'close_min':min(closes) if closes else None,'close_max':max(closes) if closes else None,'volume_sum':sum(volumes) if volumes else None}


def analyze(snapshot: dict[str,Any], symbol: str) -> dict[str,Any]:
    symbol=symbol.upper()
    tick=next((x for x in snapshot.get('tickers',[]) if str(x.get('symbol','')).upper()==symbol),{})
    product=next((x for x in snapshot.get('products',[]) if str(x.get('symbol','')).upper()==symbol),{})
    book_wrap=snapshot.get('orderbooks',{}).get(symbol,{})
    book=book_wrap.get('result',{}) if isinstance(book_wrap,dict) else {}
    bid=book.get('buy',[]) if isinstance(book,dict) else []; ask=book.get('sell',[]) if isinstance(book,dict) else []
    def levels(rows):
        out=[]
        for row in rows:
            if not isinstance(row,dict): continue
            p=number(row.get('price')); s=number(row.get('size'))
            if p is not None and p>0 and s is not None and s>=0: out.append((p,s))
        return out
    bids=levels(bid); asks=levels(ask)
    best_bid=max((x[0] for x in bids),default=None); best_ask=min((x[0] for x in asks),default=None)
    spread_bps=((best_ask-best_bid)/((best_ask+best_bid)/2)*10000) if best_bid and best_ask and best_ask>=best_bid else None
    n=20; bd=sum(s for _,s in sorted(bids,reverse=True)[:n]); ad=sum(s for _,s in sorted(asks)[:n]); depth_imb=(bd-ad)/(bd+ad) if bd+ad>0 else None
    mark=number(tick.get('mark_price')); spot=number(tick.get('spot_price'))
    mark_basis_bps=(mark/spot-1)*10000 if mark and spot and mark>0 and spot>0 else None
    series={}
    steps={'1m':60,'5m':300,'1h':3600}
    for key,value in snapshot.get('candle_sets',{}).items():
        parts=key.split('|')
        if len(parts)!=3 or parts[0].upper()!=symbol: continue
        _,kind,res=parts
        series[f'{kind}_{res}']=candle_audit(value.get('candles',[]),steps.get(res,3600),allow_nonpositive=(kind=='funding'))
    oi=series.get('open_interest_1h',{})
    oi_change=None
    if oi.get('close_first') and oi.get('close_last') and oi['close_first']>0: oi_change_pct=(oi['close_last']/oi['close_first']-1)*100
    else: oi_change_pct=None
    return {'schema_version':1,'symbol':symbol,'snapshot_collected_at':snapshot.get('collected_at'),'audited_at':datetime.now(timezone.utc).isoformat(),'product':{k:product.get(k) for k in ('id','contract_type','state','tick_size','contract_value','contract_unit_currency','initial_margin','maintenance_margin','maker_commission_rate','taker_commission_rate','default_leverage','trading_status')},'ticker':{k:tick.get(k) for k in ('timestamp','mark_price','spot_price','mark_basis','funding_rate','oi','oi_value_usd','volume','turnover_usd','ltp_change_24h','product_trading_status')},'derived':{'mark_vs_spot_basis_bps':mark_basis_bps,'orderbook_best_bid':best_bid,'orderbook_best_ask':best_ask,'orderbook_spread_bps':spread_bps,'bid_depth_top20':bd,'ask_depth_top20':ad,'top20_depth_imbalance':depth_imb,'open_interest_change_pct_over_sample':oi_change_pct},'series':series,'data_quality':{'harvest_failures':snapshot.get('failures',[]),'all_series_empty':not any(v.get('rows_valid',0) for v in series.values()),'interpretation':'Descriptive data-quality summary only. Funding-rate units, contract multipliers, and orderbook size semantics must be verified before cost or PnL calculations.'},'authority':{'research_only':True,'paper_only':True,'real_orders':False,'production_strategy_changed':False}}


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('snapshot',type=Path); p.add_argument('--symbol',default='BTCUSD'); p.add_argument('--output-dir',default='data/processed')
    a=p.parse_args()
    try:
        snap=json.loads(a.snapshot.read_text(encoding='utf-8')); result=analyze(snap,a.symbol)
        raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode(); result['integrity']={'sha256_before_integrity_field':hashlib.sha256(raw).hexdigest()}
        outdir=Path(a.output_dir); outdir.mkdir(parents=True,exist_ok=True); stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); out=outdir/f'delta_market_audit_{a.symbol.upper()}_{stamp}.json'
        fd,tmp=tempfile.mkstemp(prefix=out.name+'.',suffix='.tmp',dir=str(outdir))
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(result,f,indent=2,allow_nan=False); f.flush(); os.fsync(f.fileno())
            os.replace(tmp,out)
        except BaseException:
            try: os.unlink(tmp)
            except OSError: pass
            raise
        print(json.dumps({'output':str(out),'symbol':result['symbol'],'series':{k:{'rows_valid':v['rows_valid'],'invalid_rows':v['invalid_rows'],'gap_count':v['gap_count']} for k,v in result['series'].items()},'derived':result['derived'],'failures':len(result['data_quality']['harvest_failures']),'research_only':True,'real_orders':False},indent=2))
        return 0
    except Exception as e:
        print(json.dumps({'status':'FAILED_CLOSED','error_type':type(e).__name__,'message':str(e)[:160],'real_orders':False},indent=2)); return 2
if __name__=='__main__': raise SystemExit(main())
