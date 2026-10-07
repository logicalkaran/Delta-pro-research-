"""Live-data paper tester for Microstructure Scalper V2.
Public Delta data only. No order API and no production execution.
One position at a time; entry on the event after a signal; exit after 30s.
"""
import json,time,os,sys
from collections import deque
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from strategy.microstructure_scalper_v2 import evaluate
RAW=ROOT/"data/raw/delta_btc_raw.jsonl"
OUT=ROOT/"data/processed/microstructure_scalper_v2_live_paper.jsonl"
SUMMARY=ROOT/"data/processed/microstructure_scalper_v2_live_summary.json"
q5=deque(); q30=deque(); pts=[]; l1={}; bids={}; asks={}
buy5=sell5=buy30=sell30=0.0
position=None; pending=None; trades=[]; last_report=time.time()
W5=5_000_000; W30=30_000_000; HOLD=30_000_000

def n(x,d=0.0):
 try:return float(x)
 except:return d

def book():
 bs=sorted(((p,s) for p,s in bids.items() if s>0),reverse=True)
 a=sorted(((p,s) for p,s in asks.items() if s>0))
 if not bs and n(l1.get("bp"))>0: bs=[(n(l1.get("bp")),n(l1.get("bs")))]
 if not a and n(l1.get("ap"))>0: a=[(n(l1.get("ap")),n(l1.get("as")))]
 bb=bs[0][0] if bs else 0; aa=a[0][0] if a else 0
 b5=sum(s for _,s in bs[:5]); a5=sum(s for _,s in a[:5])
 return bb,aa,(b5-a5)/(b5+a5) if b5+a5 else 0.0

def classify(m):
 p=n(m.get("p")); s=abs(n(m.get("s")))
 if p<=0 or s<=0:return None
 bid=n(l1.get("bp")); ask=n(l1.get("ap"))
 if ask>0 and p>=ask:return "buy",s,p
 if bid>0 and p<=bid:return "sell",s,p
 if m.get("r")=="m":return "sell",s,p
 if m.get("r")=="t":return "buy",s,p
 return None

def expire(ts):
 global buy5,sell5,buy30,sell30
 while q5 and q5[0][0]<ts-W5:
  _,side,s=q5.popleft()
  if side=="buy":buy5-=s
  else:sell5-=s
 while q30 and q30[0][0]<ts-W30:
  _,side,s=q30.popleft()
  if side=="buy":buy30-=s
  else:sell30-=s

def state(ts,price):
 bb,aa,imb=book()
 total5=buy5+sell5; total30=buy30+sell30
 old=next((p for t,p in pts if t>=ts-W5),price)
 ret=(price/old-1)*100 if old else 0
 return {"windows":{
  "5":{"delta_pct":(buy5-sell5)/total5 if total5 else 0,"delta":buy5-sell5,"trades":len(q5)},
  "30":{"delta_pct":(buy30-sell30)/total30 if total30 else 0,"delta":buy30-sell30,"trades":len(q30)}},
  "price":{"5":{"return_pct":ret}},"order_book":{
  "mid_price":(bb+aa)/2 if bb and aa else price,"spread":aa-bb if bb and aa else 0,
  "imbalance_5":imb},"quality":{"fresh_seconds":0.0}}

def log(row):
 OUT.parent.mkdir(parents=True,exist_ok=True)
 with OUT.open("a") as f:f.write(json.dumps(row,separators=(",",":"))+"\n")

def manage(ts):
 global position
 if position is None or ts-position["entry_ts"]<HOLD:return
 bb,aa,_=book()
 if bb<=0:return
 exit_price=bb if position["side"]=="LONG" else aa
 raw=(exit_price/position["entry_price"]-1)*100
 signed=raw if position["side"]=="LONG" else -raw
 row={**position,"exit_ts":ts,"exit_price":exit_price,"return_pct":signed,"reason":"30S_EXIT"}
 log(row);trades.append(row);position=None

def process(m):
 global l1,bids,asks,buy5,sell5,buy30,sell30,pending,position
 typ=m.get("type"); ts=int(n(m.get("ts") or m.get("t")))
 if not ts:return
 if typ=="ob_l1":
  l1=m
 elif typ=="ob_l2":
  bids={n(p):n(s) for p,s in m.get("b",[]) if n(s)>0}; asks={n(p):n(s) for p,s in m.get("a",[]) if n(s)>0}
 elif typ=="trades":
  c=classify(m)
  if c:
   side,size,price=c; q5.append((ts,side,size));q30.append((ts,side,size));pts.append((ts,price))
   if side=="buy":buy5+=size;buy30+=size
   else:sell5+=size;sell30+=size
   expire(ts)
   if pending and position is None:
    bb,aa,_=book(); ep=aa if pending=="LONG" else bb
    if ep>0:
     position={"side":pending,"entry_ts":ts,"entry_price":ep}
     print(f"PAPER ENTRY {pending} price={ep:.2f}",flush=True);pending=None
   if position is None and pending is None and len(q5)>=3:
    sig=evaluate(state(ts,price))
    if sig.action in ("LONG","SHORT"):
     pending=sig.action
     print(f"SIGNAL {sig.action} score={sig.score} expected={sig.expected_move_pct:.4f}",flush=True)
 manage(ts)

def summary():
 wins=sum(x["return_pct"]>0 for x in trades); vals=[x["return_pct"] for x in trades]
 data={"timestamp":int(time.time()),"closed_trades":len(trades),"wins":wins,
       "win_rate":wins/len(trades) if trades else 0,"avg_return_pct":sum(vals)/len(vals) if vals else 0,
       "total_return_pct":sum(vals),"open_position":position}
 SUMMARY.write_text(json.dumps(data,indent=2))
 print("PAPER_SUMMARY",json.dumps(data,separators=(",",":")),flush=True)

def main():
 print("LIVE PAPER V2 STARTED; REAL ORDERS: OFF",flush=True)
 with RAW.open("r") as f:
  f.seek(0,os.SEEK_END)
  while True:
   line=f.readline()
   if line:
    try:
     r=json.loads(line); process(r.get("message",r))
    except Exception as e: print("PARSE",e,flush=True)
   else:
    if time.time()-last_report>30:
     summary()
     globals()["last_report"]=time.time()
    time.sleep(.05)

if __name__=="__main__":main()
