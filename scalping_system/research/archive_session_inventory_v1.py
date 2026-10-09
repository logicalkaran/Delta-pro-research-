#!/usr/bin/env python3
"""Read-only research audit of archived Delta capture snapshots; no trade execution."""
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEFAULT_DIR=ROOT/'data/raw/session_archive'
DEFAULT_OUT=ROOT/'data/processed/archive_session_inventory_v1.json'
GAP_SECONDS=30.0
REQUIRED_SESSIONS=3
REQUIRED_HOURS=6.0

def sha256(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
 return h.hexdigest()
def inspect_archive(path):
 meta_path=path.with_name(path.stem+'.metadata.json')
 result={'file':path.name,'metadata_file':meta_path.name,'integrity':'INVALID','byte_size':path.stat().st_size,'sha256':None,'first_receive_timestamp':None,'last_receive_timestamp':None,'line_count':None,'malformed_json_lines':None}
 if not meta_path.is_file(): result['error']='metadata_missing'; return result
 try: meta=json.loads(meta_path.read_text(encoding='utf-8'))
 except (OSError,json.JSONDecodeError) as e: result['error']='metadata_unreadable'; return result
 actual=sha256(path); result['sha256']=actual
 result['first_receive_timestamp']=_num(meta.get('first_receive_timestamp_epoch_seconds'))
 result['last_receive_timestamp']=_num(meta.get('last_receive_timestamp_epoch_seconds'))
 result['line_count']=meta.get('line_count'); result['malformed_json_lines']=meta.get('malformed_json_lines')
 checks=(meta.get('archive_file')==path.name,meta.get('byte_size')==path.stat().st_size,meta.get('sha256')==actual,meta.get('research_only') is True,meta.get('real_orders') is False)
 if all(checks): result['integrity']='VALID'
 else: result['error']='metadata_mismatch'
 return result
def _num(x):
 try:
  n=float(x)
  return n if n==n and abs(n)!=float('inf') else None
 except (TypeError,ValueError): return None
def evaluate(directory):
 files=sorted(p for p in directory.glob('*.jsonl') if p.is_file()) if directory.exists() else []
 items=[inspect_archive(p) for p in files]
 valid=sorted((x for x in items if x['integrity']=='VALID' and x['first_receive_timestamp'] is not None and x['last_receive_timestamp'] is not None and x['last_receive_timestamp']>=x['first_receive_timestamp']),key=lambda x:x['first_receive_timestamp'])
 # Merge time intervals; overlapping snapshots do not count their shared duration twice.
 merged=[]
 for x in valid:
  start,end=x['first_receive_timestamp'],x['last_receive_timestamp']
  if not merged or start-merged[-1]['end']>GAP_SECONDS: merged.append({'start':start,'end':end,'files':[x['file']]})
  else:
   merged[-1]['end']=max(merged[-1]['end'],end); merged[-1]['files'].append(x['file'])
 sessions=[{'start':s['start'],'end':s['end'],'duration_seconds':max(0,s['end']-s['start']),'archive_files':s['files']} for s in merged]
 hours=sum(s['duration_seconds'] for s in sessions)/3600
 ready=len(sessions)>=REQUIRED_SESSIONS and hours>=REQUIRED_HOURS
 return {'schema':'archive_session_inventory_v1','created_at_utc':datetime.now(timezone.utc).isoformat(),'research_only':True,'real_orders':False,'archive_directory':str(directory.resolve()),'session_gap_threshold_seconds':GAP_SECONDS,'archive_count':len(items),'valid_archive_count':sum(x['integrity']=='VALID' for x in items),'invalid_archive_count':sum(x['integrity']!='VALID' for x in items),'archives':items,'merged_sessions':sessions,'session_count':len(sessions),'summed_unique_session_hours':hours,'readiness':{'verdict':'READY_FOR_MULTI_SESSION_RESEARCH' if ready else 'NOT_READY','required_sessions':REQUIRED_SESSIONS,'required_hours':REQUIRED_HOURS,'observed_sessions':len(sessions),'observed_hours':hours,'note':'Intervals are merged to avoid counting overlapping snapshot time twice. This is coverage readiness only, not evidence of profitable trading edge.'}}
def main():
 p=argparse.ArgumentParser(description='Read-only integrity and multi-session coverage audit for archived Delta snapshots.')
 p.add_argument('--archive-dir',type=Path,default=DEFAULT_DIR); p.add_argument('--output',type=Path,default=DEFAULT_OUT); a=p.parse_args()
 report=evaluate(a.archive_dir); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'archive_count':report['archive_count'],'valid_archive_count':report['valid_archive_count'],'invalid_archive_count':report['invalid_archive_count'],'session_count':report['session_count'],'summed_unique_session_hours':report['summed_unique_session_hours'],'verdict':report['readiness']['verdict'],'report':str(a.output)},indent=2))
if __name__=='__main__': main()
