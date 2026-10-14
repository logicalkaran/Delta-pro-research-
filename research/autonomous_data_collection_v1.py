"""Bounded research-data collection and recurring diagnostics. Public data only."""
from __future__ import annotations
import argparse, json, signal, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PY=sys.executable
OUT=ROOT/'data/processed/autonomous_data_collection_v1.json'
LOG=ROOT/'data/processed/autonomous_data_collection_v1.jsonl'
KILL=ROOT/'data/run/LIVE_KILL_SWITCH'
STOP=False

def stop(sig, frame):
    global STOP
    STOP=True
signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)

def call(args, timeout=120):
    try:
        p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=timeout)
        try: detail=json.loads(p.stdout) if p.stdout.strip().startswith('{') else {'stdout_tail':p.stdout[-500:]}
        except ValueError: detail={'stdout_tail':p.stdout[-500:]}
        return {'returncode':p.returncode,'status':'OK' if p.returncode==0 else 'FAILED','detail':detail,'stderr_tail':p.stderr[-500:]}
    except Exception as e:
        return {'status':'FAILED','error':type(e).__name__,'detail':str(e)[:300]}

def inventory():
    try: mtf=json.loads((ROOT/'data/processed/live_multi_timeframe_candles_v1.json').read_text())
    except Exception: mtf={}
    frames=mtf.get('frames',{}) if isinstance(mtf,dict) else {}
    rows=mtf.get('candles',{}) if isinstance(mtf,dict) else {}
    micro=ROOT/'data/processed/live_microstructure_features_v1.jsonl'
    count=bad=0; first=last=None
    if micro.exists():
        with micro.open(encoding='utf-8',errors='replace') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    obj=json.loads(line); count+=1
                    ts=obj.get('ts',obj.get('timestamp'))
                    if ts is not None:
                        first=ts if first is None else min(first,ts)
                        last=ts if last is None else max(last,ts)
                except Exception: bad+=1
    one=rows.get('1m',[]) if isinstance(rows,dict) else []
    n=len(one) if isinstance(one,list) else 0
    frame_counts={}
    if isinstance(rows,dict):
        for k,v in rows.items():
            frame_counts[k]={'count':len(v) if isinstance(v,list) else 0,
                'last_age_seconds':(frames.get(k,{}) or {}).get('last_age_seconds') if isinstance(frames.get(k),dict) else None}
    return {'timestamp':time.time(),'frames':frame_counts,'one_minute_candles':n,
      'microstructure_feature_rows':count,'microstructure_parse_errors':bad,
      'microstructure_first_ts':first,'microstructure_last_ts':last,
      'sample_targets':{'minimum_trade_labels_for_promotion':100,'preferred_1m_candles_for_initial_walk_forward':1000,'preferred_microstructure_rows':10000},
      'sufficiency':{'minimum_candle_floor_met':n>=1000,'microstructure_floor_met':count>=10000,
      'note':'Data volume is necessary but does not establish independent trade count, representativeness, or profitability.'},
      'real_orders':False}

def run(seconds=21600, interval=900, refresh=30, with_paper=True):
    if not 60<=seconds<=86400: raise ValueError('seconds must be 60..86400')
    if not 60<=interval<=3600: raise ValueError('interval must be 60..3600')
    if not 5<=refresh<=300: raise ValueError('refresh must be 5..300')
    children=[]; started=time.time(); history=[]
    try:
        if KILL.exists(): raise RuntimeError('LIVE_KILL_SWITCH_PRESENT; fail closed')
        children.append(subprocess.Popen([PY,str(ROOT/'paper/live_shadow_feed_v1.py'),'--seconds',str(seconds)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
        children.append(subprocess.Popen([PY,str(ROOT/'research/candle_history_sync_v1.py'),'--interval',str(refresh),'--seconds',str(seconds)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
        # Append timestamped features only when the source state changes; no raw event archive.
        children.append(subprocess.Popen([PY,str(ROOT/'research/live_microstructure_feature_tape_v1.py')],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
        if with_paper:
            children.append(subprocess.Popen([PY,str(ROOT/'paper/live_execution_paper_v3.py'),'--seconds',str(seconds)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
        next_eval=0
        while not STOP and time.time()-started<seconds:
            if KILL.exists():
                history.append({'event':'HALT','reason':'LIVE_KILL_SWITCH_PRESENT'})
                break
            now=time.time()
            if now>=next_eval:
                reg=call([PY,str(ROOT/'research/prediction_hypothesis_registry_v1.py')],30)
                pred=call([PY,str(ROOT/'research/prediction_layer_v1.py')],120)
                event={'ts':now,'event':'RESEARCH_CHECKPOINT','registry':reg['status'],'prediction':pred['status'],'inventory':inventory()}
                history.append(event); next_eval=now+interval
                LOG.parent.mkdir(parents=True,exist_ok=True)
                with LOG.open('a',encoding='utf-8') as f: f.write(json.dumps(event,separators=(',',':'))+'\n')
            time.sleep(1)
    finally:
        for p in children:
            if p.poll() is None:
                p.terminate()
                try: p.wait(timeout=3)
                except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=2)
    report={'version':'autonomous_data_collection_v1','status':'STOPPED' if STOP else 'COMPLETED',
      'duration_s':round(time.time()-started,2),'checkpoints':len(history),
      'latest':history[-1] if history else None,'history':history[-20:],
      'real_orders':False,'execution':'PAPER_ONLY' if with_paper else 'OBSERVATION_ONLY'}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(report,indent=2,allow_nan=False))
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds',type=int,default=21600)
    p.add_argument('--interval',type=int,default=900)
    p.add_argument('--refresh',type=int,default=30)
    p.add_argument('--no-paper',action='store_true')
    a=p.parse_args()
    run(a.seconds,a.interval,a.refresh,not a.no_paper)

if __name__=='__main__': main()
