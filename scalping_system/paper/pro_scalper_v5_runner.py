from pathlib import Path
import json,time,traceback
from paper.pro_scalper_v5_paper import PaperEngine,read,STATE,OUT
ROOT=Path(__file__).resolve().parents[1]
INTERVAL=1.0
MAX_BYTES=20_000_000
def main():
    e=PaperEngine()
    while True:
        try:
            s=read(STATE,{})
            r=e.step(s)
            OUT.parent.mkdir(parents=True,exist_ok=True)
            with OUT.open("a") as f:f.write(json.dumps({"ts":time.time(),**r},separators=(",",":"))+"\n")
            if OUT.stat().st_size>MAX_BYTES:
                lines=OUT.read_text().splitlines()
                OUT.write_text("\n".join(lines[-10000:])+"\n")
        except Exception as exc:
            print("PAPER_V5_ERROR",type(exc).__name__,str(exc))
            traceback.print_exc()
        time.sleep(INTERVAL)
if __name__=="__main__": main()
