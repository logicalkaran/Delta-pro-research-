import json,time
from datetime import datetime,timezone
from pathlib import Path
import websocket
from .config import WS_URL,SYMBOL,CHANNELS,RAW_FILE
from .live_state import update as update_live_state
RAW_MAX_BYTES=10_000_000
def utc_now(): return datetime.now(timezone.utc).isoformat()
def save_raw(message):
    path=Path(RAW_FILE); path.parent.mkdir(parents=True,exist_ok=True)
    record=json.dumps({"received_at":utc_now(),"message":message},separators=(",",":"))+"\n"
    try:
        if path.exists() and path.stat().st_size+len(record.encode())>RAW_MAX_BYTES:
            path.write_text(record,encoding="utf-8")
            return
    except OSError: pass
    with path.open("a",encoding="utf-8") as f:f.write(record)
def on_open(ws):
    print("[CONNECTED] Delta WebSocket",flush=True)
    for channel in CHANNELS:
        ws.send(json.dumps({"type":"subscribe","payload":{"channels":[{"name":channel,"symbols":[SYMBOL]}]}}))
        print(f"[SUBSCRIBED] {channel}",flush=True)
def on_message(ws,message):
    try:
        data=json.loads(message); save_raw(data)
        if data.get("type") in {"trades","ob_l1","ob_l2"}: update_live_state(data)
    except Exception as exc: print(f"[PARSE ERROR] {exc}",flush=True)
def on_error(ws,error): print(f"[WEBSOCKET ERROR] {error}",flush=True)
def on_close(ws,code,msg): print(f"[CLOSED] code={code} message={msg}",flush=True)
def run():
    while True:
        try:
            ws=websocket.WebSocketApp(WS_URL,on_open=on_open,on_message=on_message,on_error=on_error,on_close=on_close)
            ws.run_forever(ping_interval=20,ping_timeout=10)
        except KeyboardInterrupt: break
        except Exception as exc: print(f"[FATAL] {exc}",flush=True)
        time.sleep(5)
if __name__=="__main__": run()
