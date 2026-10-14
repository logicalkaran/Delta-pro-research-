"""Persistent forward tournament runner; research only."""
from pathlib import Path
import subprocess,time
ROOT=Path(__file__).resolve().parents[1]; LOG=ROOT/"data/processed/strategy_forward_tournament_runner.log"
while True:
 r=subprocess.run([str(ROOT/".venv/bin/python"),str(ROOT/"research/strategy_forward_tournament_v1.py")],capture_output=True,text=True)
 with LOG.open("a") as f:f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())+" "+r.stdout.strip()+"\n")
 time.sleep(10)
