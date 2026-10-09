"""Authenticated Delta read-only balance check. Never submits orders."""
import os,time,hmac,hashlib,json,urllib.request,urllib.error
from pathlib import Path
root=Path(__file__).resolve().parents[1]
env=root/".env"
for line in env.read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k,v=line.split("=",1); os.environ.setdefault(k,v)
key=os.environ["DELTA_API_KEY"]; secret=os.environ["DELTA_API_SECRET"]
base=os.environ.get("DELTA_API_BASE","https://api.india.delta.exchange")
method="GET"; path="/v2/wallet/balances"; ts=str(int(time.time()))
msg=method+ts+path
sig=hmac.new(secret.encode(),msg.encode(),hashlib.sha256).hexdigest()
req=urllib.request.Request(base+path,method=method,headers={
 "Accept":"application/json","User-Agent":"btc-fisher-trader-readonly",
 "api-key":key,"signature":sig,"timestamp":ts})
try:
    with urllib.request.urlopen(req,timeout=10) as resp:
        data=json.loads(resp.read().decode())
    safe=[]
    for x in data.get("result",[]):
        safe.append({"asset_symbol":x.get("asset_symbol"),
                     "available_balance":x.get("available_balance"),
                     "balance":x.get("balance"),
                     "blocked_margin":x.get("blocked_margin"),
                     "position_margin":x.get("position_margin"),
                     "order_margin":x.get("order_margin")})
    print(json.dumps({"success":data.get("success"),"wallets":safe},indent=2))
except urllib.error.HTTPError as e:
    body=e.read().decode(errors="replace")
    print("HTTP_ERROR",e.code,body[:500])
except Exception as e:
    print("ERROR",type(e).__name__,str(e))
