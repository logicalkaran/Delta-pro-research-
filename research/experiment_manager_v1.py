"""Research-only experiment registry and chronological validation utilities."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/'data'/'processed'/'experiment_registry_v1.json'

def fingerprint(obj: Any)->str:
    if isinstance(obj,(str,bytes)):
        raw=obj.encode() if isinstance(obj,str) else obj
    else: raw=json.dumps(obj,sort_keys=True,separators=(',',':'),default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:16]

def chronological_split(rows:list[dict], holdout_ratio:float=.30, time_key:str='ts'):
    rows=sorted(rows,key=lambda r:r.get(time_key,0))
    cut=max(1,min(len(rows)-1,round(len(rows)*(1-holdout_ratio)))) if len(rows)>1 else len(rows)
    return rows[:cut],rows[cut:]

def register(name:str,dataset:Any,config:Any,cost_model:dict,metrics:dict|None=None,status:str='RUNNING'):
    REGISTRY.parent.mkdir(parents=True,exist_ok=True)
    payload={'experiment_id':fingerprint({'name':name,'dataset':fingerprint(dataset),'config':fingerprint(config)}),'name':name,'dataset_fingerprint':fingerprint(dataset),'config_fingerprint':fingerprint(config),'cost_model':cost_model,'metrics':metrics or {},'status':status}
    data=json.loads(REGISTRY.read_text()) if REGISTRY.exists() else []
    if not isinstance(data,list): data=[]
    data=[x for x in data if x.get('experiment_id')!=payload['experiment_id']]
    data.append(payload); REGISTRY.write_text(json.dumps(data,indent=2,sort_keys=True)); return payload

if __name__=='__main__':
    print(json.dumps({'registry':str(REGISTRY),'status':'READY','utility':'research_only'}))
