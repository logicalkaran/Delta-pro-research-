#!/usr/bin/env python3
"""Manual research-only snapshot archiver; never places trades or changes collector."""
import argparse, hashlib, json, os, tempfile
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / 'data/raw/delta_btc_raw.jsonl'
DEFAULT_ARCHIVE_DIR = ROOT / 'data/raw/session_archive'
RECEIVE_FIELDS = ('receive_at','received_at','receive_time','received_ts','receive_ts','recv_ts','local_timestamp','local_ts')
class SnapshotError(RuntimeError): pass

def _hash(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def _details(path):
    count=bad=0; times=[]
    with path.open('rb') as f:
        for raw in f:
            count+=1
            try: row=json.loads(raw)
            except (json.JSONDecodeError,UnicodeDecodeError): bad+=1; continue
            if not isinstance(row,dict): continue
            for k in RECEIVE_FIELDS:
                v=row.get(k)
                if isinstance(v,(int,float)) and not isinstance(v,bool):
                    v=float(v)
                    if v>1e17:v/=1e9
                    elif v>1e14:v/=1e6
                    elif v>1e11:v/=1e3
                    times.append(v); break
                if isinstance(v,str):
                    try:
                        from datetime import datetime
                        dt=datetime.fromisoformat(v.replace('Z','+00:00'))
                        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                        times.append(dt.timestamp()); break
                    except ValueError: pass
    return count,bad,(str(times[0]) if times else None),(str(times[-1]) if times else None)
def archive_snapshot(source, archive_dir):
    source=Path(source).expanduser().resolve(); d=Path(archive_dir).expanduser().resolve()
    if not source.is_file(): raise SnapshotError(f'Source file does not exist: {source}')
    before=source.stat()
    if not before.st_size: raise SnapshotError(f'Source file is empty: {source}')
    d.mkdir(parents=True,exist_ok=True); now=datetime.now(timezone.utc); stamp=now.strftime('%Y%m%dT%H%M%S%fZ')
    n=0
    while True:
        suf='' if n==0 else f'_{n:03d}'
        dest=d/f'delta_btc_raw_{stamp}{suf}.jsonl'; metap=d/f'delta_btc_raw_{stamp}{suf}.metadata.json'
        if not dest.exists() and not metap.exists(): break
        n+=1
    at=mt=None; reserved_dest=reserved_meta=False; published_dest=False
    try:
        fd,name=tempfile.mkstemp(prefix='.capture-snapshot-',suffix='.tmp',dir=d); at=Path(name); sh=hashlib.sha256()
        with os.fdopen(fd,'wb') as out, source.open('rb') as inp:
            remaining=before.st_size
            while remaining:
                b=inp.read(min(1024*1024,remaining))
                if not b: raise SnapshotError('Source was truncated during copy; nothing published.')
                out.write(b); sh.update(b); remaining-=len(b)
            out.flush(); os.fsync(out.fileno())
        # Append-only growth is expected while the websocket collector runs. Verify that
        # the exact initial prefix is still present, which detects the collector's reset.
        after=source.stat()
        if (before.st_dev,before.st_ino)!=(after.st_dev,after.st_ino) or after.st_size < before.st_size:
            raise SnapshotError('Source rotated or truncated during copy; nothing published.')
        prefix=hashlib.sha256()
        with source.open('rb') as check:
            remaining=before.st_size
            while remaining:
                b=check.read(min(1024*1024,remaining))
                if not b: raise SnapshotError('Source prefix disappeared during verification; nothing published.')
                prefix.update(b); remaining-=len(b)
        if prefix.hexdigest()!=sh.hexdigest(): raise SnapshotError('Source prefix changed during copy; nothing published.')
        digest=_hash(at)
        if digest!=sh.hexdigest() or at.stat().st_size!=before.st_size: raise SnapshotError('Snapshot hash/size verification failed.')
        lines,bad,first,last=_details(at)
        meta={'archive_file':dest.name,'created_at_utc':now.isoformat(),'source_path':str(source),'byte_size':at.stat().st_size,'line_count':lines,'sha256':digest,'first_receive_timestamp_epoch_seconds':first,'last_receive_timestamp_epoch_seconds':last,'malformed_json_lines':bad,'coverage_note':'Consistent prefix of the retained source file as observed at copy start; appended records after that point are excluded. Does not prove a complete session or recover rotated/truncated history.','research_only':True,'real_orders':False}
        fd,name=tempfile.mkstemp(prefix='.capture-metadata-',suffix='.tmp',dir=d); mt=Path(name)
        with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(meta,f,indent=2,sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
        laststat=source.stat()
        if (before.st_dev,before.st_ino)!=(laststat.st_dev,laststat.st_ino) or laststat.st_size < before.st_size:
            raise SnapshotError('Source rotated or truncated before publish; nothing published.')
        prefix=hashlib.sha256()
        with source.open('rb') as check:
            remaining=before.st_size
            while remaining:
                b=check.read(min(1024*1024,remaining))
                if not b: raise SnapshotError('Source prefix disappeared before publish; nothing published.')
                prefix.update(b); remaining-=len(b)
        if prefix.hexdigest()!=sh.hexdigest(): raise SnapshotError('Source prefix changed before publish; nothing published.')
        # Reserve both names exclusively, then atomically replace our own placeholders.
        for target, flag in ((dest, 'dest'), (metap, 'meta')):
            fd=os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(fd)
            if flag == 'dest': reserved_dest=True
            else: reserved_meta=True
        os.replace(at,dest); at=None; reserved_dest=False; published_dest=True
        os.replace(mt,metap); mt=None; reserved_meta=False
        return dest,metap,meta
    finally:
        for p in (at,mt):
            if p is not None: p.unlink(missing_ok=True)
        if reserved_dest: dest.unlink(missing_ok=True)
        if reserved_meta: metap.unlink(missing_ok=True)
        # If metadata publication failed, remove only the archive published by this call.
        if published_dest and not metap.exists(): dest.unlink(missing_ok=True)
def main():
    p=argparse.ArgumentParser(description='Manually archive a stable research-only Delta BTC capture snapshot.')
    p.add_argument('--source',type=Path,default=DEFAULT_SOURCE); p.add_argument('--archive-dir',type=Path,default=DEFAULT_ARCHIVE_DIR); a=p.parse_args()
    try: dest,meta_path,m=archive_snapshot(a.source,a.archive_dir)
    except (OSError,SnapshotError) as e: p.exit(2,f'snapshot failed: {e}\n')
    print(json.dumps({'archive':str(dest),'metadata':str(meta_path),'sha256':m['sha256'],'bytes':m['byte_size'],'lines':m['line_count'],'research_only':True},indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
