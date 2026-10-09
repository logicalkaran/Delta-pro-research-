import time,json
from pathlib import Path
from paper.pro_scalper_v6_paper import Engine,read,STATE,OUT
e=Engine()
while True:
 if e.pending_trade is not None:
  e.flush_pending_trade()
  time.sleep(1)
  continue
 r=e.step(read(STATE,{}));e.log_result(r);time.sleep(1)
