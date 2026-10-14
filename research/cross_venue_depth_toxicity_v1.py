"""Research-only cross-venue depth and volume-synchronized toxicity tape.

Consumes an existing cross_venue_ticks_<session>.jsonl capture. No network access or
orders. Binance five-level imbalance requires bid_levels_top5_btc/ask_levels_top5_btc,
which are recorded by the updated capture script for future sessions; old captures are
marked unavailable rather than approximated from top-10 aggregates.
"""
from __future__ import annotations
import argparse, json, math, statistics, sys
from collections import deque
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_DIR=ROOT/'data/raw/cross_venue_aligned'


def finite(x: Any):
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError): return None


def depth_imbalance(bids, asks, size_key=None):
    if not isinstance(bids,list) or not isinstance(asks,list) or not bids or not asks: return None
    def total(levels):
        vals=[]
        for item in levels[:5]:
            if not isinstance(item,(list,tuple)) or len(item)<2: return None
            p,q=finite(item[0]),finite(item[1])
            if p is None or q is None or p<=0 or q<0: return None
            vals.append(q)
        return sum(vals) if vals else None
    b,a=total(bids),total(asks)
    return (b-a)/(b+a) if b is not None and a is not None and b+a>0 else None


def percentile(values, q):
    if not values: return None
    xs=sorted(values); i=(len(xs)-1)*q; lo=int(i); hi=min(lo+1,len(xs)-1)
    return xs[lo]+(xs[hi]-xs[lo])*(i-lo)


class VPINBuckets:
    """Fixed-volume BTC buckets; trades are split at bucket boundaries."""
    def __init__(self, bucket_volume=50.0, rolling_buckets=20, distribution_window_s=7200.0):
        if bucket_volume<=0 or rolling_buckets<2: raise ValueError('invalid VPIN parameters')
        self.bucket_volume=bucket_volume; self.rolling_buckets=rolling_buckets; self.distribution_window_s=distribution_window_s
        self.bucket_buy=0.0; self.bucket_sell=0.0; self.bucket_start=None
        self.completed=deque(); self.history=deque(); self.last_vpin=None; self.last_p90=None; self.last_critical=None
        self.completed_count=0

    def ingest(self, ts, qty, side):
        if ts is None or qty is None or qty<=0 or side not in ('BUY','SELL'): return
        remain=qty
        while remain>1e-12:
            if self.bucket_start is None: self.bucket_start=ts
            capacity=self.bucket_volume-self.bucket_buy-self.bucket_sell
            piece=min(remain,capacity)
            if side=='BUY': self.bucket_buy+=piece
            else: self.bucket_sell+=piece
            remain-=piece
            if self.bucket_buy+self.bucket_sell >= self.bucket_volume-1e-9:
                val=abs(self.bucket_buy-self.bucket_sell)/self.bucket_volume
                self.completed.append((ts,val)); self.history.append((ts,val)); self.completed_count+=1
                self.bucket_buy=self.bucket_sell=0.0; self.bucket_start=ts
                while self.completed and ts-self.completed[0][0]>self.distribution_window_s: self.completed.popleft()
                while self.history and ts-self.history[0][0]>self.distribution_window_s: self.history.popleft()
                vals=[x[1] for x in list(self.completed)[-self.rolling_buckets:]]
                if len(vals)==self.rolling_buckets:
                    self.last_vpin=statistics.fmean(vals)
                    # Distribution uses prior completed rolling VPIN observations only.
                    if not hasattr(self,'_vpin_history'): self._vpin_history=deque()
                    prior=[v for t,v in self._vpin_history if ts-t<=self.distribution_window_s]
                    self.last_p90=percentile(prior,0.90) if len(prior)>=30 else None
                    self.last_critical=(self.last_vpin>self.last_p90) if self.last_p90 is not None else None
                    self._vpin_history.append((ts,self.last_vpin))
                    while self._vpin_history and ts-self._vpin_history[0][0]>self.distribution_window_s: self._vpin_history.popleft()

    def snapshot(self):
        return {'vpin_bucket_volume_btc':self.bucket_volume,'vpin_window_buckets':self.rolling_buckets,
                'vpin':self.last_vpin,'vpin_rolling_2h_p90':self.last_p90,'vpin_critical':self.last_critical,
                'completed_volume_buckets':self.completed_count,'vpin_status':'OK' if self.last_vpin is not None else 'INSUFFICIENT_COMPLETED_BUCKETS',
                'passive_making_veto':self.last_critical is True,
                'passive_making_allowed':self.last_critical is False}


class RollingDepthCovariance:
    """Bounded two-hour covariance/correlation of matched Binance/Delta depth imbalance."""
    def __init__(self, window_s=7200.0, max_pairs=20000):
        self.window_s=window_s; self.pairs=deque(maxlen=max_pairs)
        self.sx=self.sy=self.sxx=self.syy=self.sxy=0.0

    def _remove_oldest(self):
        _,ox,oy=self.pairs.popleft()
        self.sx-=ox; self.sy-=oy; self.sxx-=ox*ox; self.syy-=oy*oy; self.sxy-=ox*oy

    def add(self, ts, x, y):
        if ts is None or x is None or y is None: return
        while self.pairs and ts-self.pairs[0][0]>self.window_s:
            self._remove_oldest()
        if len(self.pairs)==self.pairs.maxlen:
            self._remove_oldest()
        self.pairs.append((ts,x,y))
        self.sx+=x; self.sy+=y; self.sxx+=x*x; self.syy+=y*y; self.sxy+=x*y

    def snapshot(self):
        n=len(self.pairs)
        if n<2:
            return {"n":n,"covariance":None,"correlation":None}
        cov=(self.sxy-self.sx*self.sy/n)/(n-1)
        vx=max(0.0,self.sxx-self.sx*self.sx/n)
        vy=max(0.0,self.syy-self.sy*self.sy/n)
        corr=(self.sxy-self.sx*self.sy/n)/math.sqrt(vx*vy) if vx>0 and vy>0 else None
        return {"n":n,"covariance":cov,"correlation":max(-1.0,min(1.0,corr)) if corr is not None else None}


def engine_ts(row):
    venue=row.get('venue')
    keys=('engine_event_ts_s','engine_transaction_ts_s') if venue=='binance' else ('engine_ts_s','engine_trade_ts_s','feed_ts_s')
    for k in keys:
        v=finite(row.get(k))
        if v is not None and v>0: return v
    return None


def process_capture(input_path: Path, output_path: Path, bucket_volume=50.0, max_match_age_s=0.2):
    vpin=VPINBuckets(bucket_volume=bucket_volume)
    depth_covariance=RollingDepthCovariance()
    latest_binance=None; latest_delta=None; pending_sell=deque(); counts={'input_rows':0,'binance_depth_rows':0,'delta_l2_rows':0,'binance_trades':0,'binance_sell_depth_responses':0,'cross_venue_matches':0,'binance_depth_levels_missing':0,'vpin_critical_rows':0,'matched_depth_pairs':0}
    output_path.parent.mkdir(parents=True,exist_ok=True)
    with input_path.open(encoding='utf-8') as inp, output_path.open('x',encoding='utf-8') as out:
        for line_no,line in enumerate(inp,1):
            if not line.strip(): continue
            try: row=json.loads(line)
            except json.JSONDecodeError: continue
            counts['input_rows']+=1; venue=row.get('venue'); kind=row.get('kind'); ts=engine_ts(row)
            if venue=='binance' and kind=='aggTrade':
                counts['binance_trades']+=1
                qty=finite(row.get('quantity_btc')); side=row.get('aggressor_side')
                vpin.ingest(ts,qty,side)
                if side=='SELL' and ts is not None and latest_delta is not None:
                    dts=latest_delta.get('_engine_ts')
                    if dts is not None and 0<=ts-dts<=max_match_age_s:
                        pending_sell.append({'ts':ts,'qty_btc':qty,'pre_bid':latest_delta.get('best_bid'),'pre_bid_size':latest_delta.get('bid_size_at_best'),'pre_delta_imbalance':latest_delta.get('delta_imbalance_5'),'trade_id':row.get('trade_id')})
            elif venue=='binance' and kind=='depthUpdate':
                counts['binance_depth_rows']+=1
                if row.get('book_synced') is True:
                    bi=depth_imbalance(row.get('bid_levels_top5_btc'),row.get('ask_levels_top5_btc'))
                    if bi is None: counts['binance_depth_levels_missing']+=1
                    latest_binance={'_engine_ts':ts,'_receive_mono_s':finite(row.get('receive_mono_s')),'_receive_epoch_s':finite(row.get('receive_epoch_s')),'mid':finite(row.get('mid')),'imbalance_5':bi,'book_synced':True}
            elif venue=='delta' and kind=='ob_l2_snapshot':
                counts['delta_l2_rows']+=1
                bids=row.get('bid_levels'); asks=row.get('ask_levels')
                di=depth_imbalance(bids,asks)
                bid=finite(row.get('best_bid')); ask=finite(row.get('best_ask'))
                bq=finite(bids[0][1]) if isinstance(bids,list) and bids and len(bids[0])>1 else None
                latest_delta={'_engine_ts':ts,'_receive_mono_s':finite(row.get('receive_mono_s')),'_receive_epoch_s':finite(row.get('receive_epoch_s')),'mid':finite(row.get('mid')),'best_bid':bid,'best_ask':ask,'bid_size_at_best':bq,'delta_imbalance_5':di}
                while pending_sell and ts is not None and ts-(pending_sell[0]['ts']+max_match_age_s)>0.5:
                    pending_sell.popleft()
                # Sample the response at/after the full 200ms window; tolerate <=500ms snapshot delay.
                for p in list(pending_sell):
                    age=ts-p['ts']
                    if max_match_age_s<=age<=max_match_age_s+0.5:
                        qpre=p.get('pre_bid_size'); qpost=bq
                        response=None
                        if qpre is not None and qpost is not None and qpre>0:
                            response=(qpost-qpre)/qpre
                        response_row={'schema':'cross_venue_depth_toxicity_v1','feature_type':'binance_sell_delta_bid_response','event_ts_s':p['ts'],'label_ts_s':ts,'response_window_ms':age*1000,'binance_sell_quantity_btc':p['qty_btc'],'delta_pre_bid':p.get('pre_bid'),'delta_pre_bid_size_contract_units':qpre,'delta_post_bid':bid,'delta_post_bid_size_contract_units':qpost,'delta_bid_depth_change_fraction':response,'pre_delta_imbalance_5':p.get('pre_delta_imbalance'),'post_delta_imbalance_5':di,'response_definition':'relative change in Delta best-bid displayed size; Binance BTC quantity is not mixed with Delta contract units','research_only':True,'real_orders':False}
                        out.write(json.dumps(response_row,separators=(',',':'),allow_nan=False)+'\n')
                        counts['binance_sell_depth_responses']+=1; pending_sell.remove(p)
                b_age=(ts-latest_binance['_engine_ts']) if ts is not None and latest_binance and latest_binance.get('_engine_ts') is not None else None
                b_fresh=b_age is not None and 0<=b_age<=max_match_age_s
                bi=latest_binance.get('imbalance_5') if latest_binance and b_fresh else None
                diff=bi-di if bi is not None and di is not None else None
                if b_fresh and bi is not None and di is not None:
                    depth_covariance.add(ts,bi,di)
                    counts['matched_depth_pairs']+=1
                cov=depth_covariance.snapshot()
                candidate=bool(bi is not None and di is not None and bi>0.6 and di<=0.2 and diff>0.4)
                if candidate: counts['cross_venue_matches']+=1
                vp=vpin.snapshot()
                if vp['vpin_critical']: counts['vpin_critical_rows']+=1
                feat={'schema':'cross_venue_depth_toxicity_v1','feature_type':'delta_l2_state','session_id':input_path.stem.replace('cross_venue_ticks_',''),'event_ts_s':ts,'ts':ts,'mid':latest_delta['mid'],'receive_mono_s':latest_delta['_receive_mono_s'],'microprice_method':'cross_venue_depth_toxicity_v1','binance_book_fresh':b_fresh,'binance_book_age_ms':b_age*1000 if b_age is not None else None,'binance_imbalance_5':bi,'delta_imbalance_5':di,'binance_minus_delta_imbalance':diff,'depth_imbalance_covariance_2h':cov['covariance'],'depth_imbalance_correlation_2h':cov['correlation'],'depth_imbalance_pairs_2h':cov['n'],'binance_bid_skew_candidate':candidate,'cross_venue_gate':'CANDIDATE_ONLY_NOT_ARBITRAGE' if candidate else 'NO_CANDIDATE','binance_book_levels_schema_available':bi is not None,'vpin':vp['vpin'],'vpin_rolling_2h_p90':vp['vpin_rolling_2h_p90'],'vpin_critical':vp['vpin_critical'],'passive_making_veto':vp['passive_making_veto'],'passive_making_allowed':vp['vpin_critical'] is False,'research_only':True,'real_orders':False}
                out.write(json.dumps(feat,separators=(',',':'),allow_nan=False)+'\n')
    return {'schema':'cross_venue_depth_toxicity_v1','input':str(input_path),'output':str(output_path),'counts':counts,'vpin':vpin.snapshot(),'depth_covariance_2h':depth_covariance.snapshot(),'status':'DRY_RUN_COMPLETE','research_only':True,'real_orders':False,'limitations':['VPIN is a volume-imbalance approximation, not calibrated PIN or proof of informed trading.','Cross-venue engine timestamps may have clock/timestamp-semantic offsets; stale/future matches are rejected, but timestamp comparability still needs independent validation.','Older Binance captures do not include five-level arrays, so Binance I5 is intentionally null for those rows.','Delta depth quantities are contract units and are not added to Binance BTC trade volume.','A cross-venue imbalance candidate is not deterministic arbitrage and must pass out-of-sample, after-cost tests.']}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--session',required=True);ap.add_argument('--data-dir',type=Path,default=DEFAULT_DIR);ap.add_argument('--output',type=Path,default=None);ap.add_argument('--bucket-volume-btc',type=float,default=50.0);ap.add_argument('--max-match-age-ms',type=float,default=200.0);a=ap.parse_args()
    source=a.data_dir/f'cross_venue_ticks_{a.session}.jsonl';target=a.output or a.data_dir/f'cross_venue_depth_toxicity_{a.session}.jsonl'
    try:
        report=process_capture(source,target,a.bucket_volume_btc,a.max_match_age_ms/1000)
        print(json.dumps(report,indent=2,allow_nan=False));return 0
    except (OSError,ValueError) as e:
        print(f'FAILED_CLOSED: {type(e).__name__}: {e}',file=sys.stderr);return 2

if __name__=='__main__': raise SystemExit(main())
