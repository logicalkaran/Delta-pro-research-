"""V4.3 public BTC cross-venue collector. Research-only; no credentials/orders."""
import json,time,urllib.request,urllib.parse,os
from datetime import datetime,timezone
from strategy.cross_venue_v41 import VenueSnapshot,compare
from strategy.cross_venue_edge_v42 import classify
OUT="data/processed/cross_venue_btc_v43.jsonl"

def get(url,timeout=3):
    req=urllib.request.Request(url,headers={"User-Agent":"btc-research-v43/1.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode())

def binance():
    p=get("https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT")
    b=get("https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol=BTCUSDT")
    oi=get("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT")
    prem=get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT")
    return VenueSnapshot("binance",float(p["price"]),float(b["bidPrice"]),float(b["askPrice"]),
        open_interest=float(oi["openInterest"]),funding=float(prem.get("lastFundingRate",0)))

def bybit():
    q=urllib.parse.urlencode({"category":"linear","symbol":"BTCUSDT"})
    x=get("https://api.bybit.com/v5/market/tickers?"+q)["result"]["list"][0]
    return VenueSnapshot("bybit",float(x["lastPrice"]),float(x["bid1Price"]),float(x["ask1Price"]),
        volume=float(x.get("volume24h",0)),open_interest=float(x.get("openInterest",0)),
        funding=float(x.get("fundingRate",0)))

def okx():
    q=urllib.parse.urlencode({"instId":"BTC-USDT-SWAP"})
    x=get("https://www.okx.com/api/v5/market/ticker?"+q)["data"][0]
    return VenueSnapshot("okx",float(x["last"]),float(x["bidPx"]),float(x["askPx"]),
        volume=float(x.get("vol24h") or 0))

def delta():
    x=get("https://api.india.delta.exchange/v2/tickers/BTCUSD")["result"]
    if isinstance(x,list): x=x[0]
    price=float(x.get("mark_price") or x.get("close") or x.get("spot_price"))
    return VenueSnapshot("delta",price,float(x.get("best_bid") or x.get("bid") or 0),
        float(x.get("best_ask") or x.get("ask") or 0),volume=float(x.get("volume") or 0))

def poll():
    snaps=[]; errors={}
    for name,fn in (("binance",binance),("bybit",bybit),("okx",okx),("delta",delta)):
        try: snaps.append(fn())
        except Exception as e: errors[name]=type(e).__name__+":"+str(e)[:120]
    c=compare(snaps) if snaps else {"valid":False,"reason":"NO_DATA"}
    edge=classify(snaps)
    row={"ts_utc":datetime.now(timezone.utc).isoformat(),"epoch_ms":int(time.time()*1000),
         "venues_ok":len(snaps),"errors":errors,"comparison":c,"edge_v42":edge}
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    with open(OUT,"a") as f: f.write(json.dumps(row,separators=(",",":"))+"\n")
    return row

if __name__=="__main__":
    interval=float(os.getenv("CROSS_V43_INTERVAL","5"))
    while True:
        row=poll()
        print(json.dumps({"ts_utc":row["ts_utc"],"venues_ok":row["venues_ok"],
            "errors":row["errors"],"state":row["edge_v42"].get("state"),
            "spread_bps":row["edge_v42"].get("spread_bps")},separators=(",",":")),flush=True)
        time.sleep(interval)
