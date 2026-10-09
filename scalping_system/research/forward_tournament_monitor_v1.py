"""Periodic forward tournament + evaluator."""
from pathlib import Path
import subprocess,time
ROOT=Path(__file__).resolve().parents[1]; PY=str(ROOT/".venv/bin/python")
def run(x):
 return subprocess.run([PY,str(ROOT/x)],capture_output=True,text=True).stdout.strip()
while True:
 a=run("research/strategy_forward_tournament_v1.py")
 b=run("research/forward_tournament_evaluator_v1.py")
 with (ROOT/"data/processed/forward_tournament_monitor_v1.log").open("a") as f:
  f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())+" | "+a+" | "+b+"\n")
 time.sleep(10)
