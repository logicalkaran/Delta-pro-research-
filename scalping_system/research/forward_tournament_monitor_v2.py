"""Continuous forward tournament with v2 evaluation."""
from pathlib import Path
import subprocess,time
ROOT=Path(__file__).resolve().parents[1]; PY=str(ROOT/".venv/bin/python")
while True:
 a=subprocess.run([PY,str(ROOT/"research/strategy_forward_tournament_v1.py")],capture_output=True,text=True).stdout.strip()
 b=subprocess.run([PY,str(ROOT/"research/forward_tournament_evaluator_v2.py")],capture_output=True,text=True).stdout.strip()
 with (ROOT/"data/processed/forward_tournament_v2.log").open("a") as f:f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())+" | "+a+" | "+b+"\n")
 time.sleep(10)
