from pathlib import Path
import hashlib, json, random, time, os, math
from research.pro_scalper_v6 import ensemble

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "research/pro_scalper_v6_config.json"
V5_CONFIG = ROOT / "research/pro_scalper_v5_config.json"
STATE = ROOT / "data/live_microstructure_state.json"
OUT = ROOT / "data/processed/pro_scalper_v6_paper.jsonl"
PAPER_RUNTIME_STATE = ROOT / "data/processed/pro_scalper_v6_runtime_state.json"

def _tuplify(value):
    return tuple(_tuplify(x) for x in value) if isinstance(value, list) else value

def _valid_position(position):
    if position is None:
        return True
    if not isinstance(position, dict) or position.get("paper_only") is not True:
        return False
    try:
        entry_px = float(position["entry_px"])
        entry_ts = float(position["entry_ts"])
        quantity = float(position["quantity_btc"])
        return (position.get("side") in ("LONG", "SHORT")
                and math.isfinite(entry_px) and entry_px > 0
                and math.isfinite(entry_ts) and entry_ts > 0
                and math.isfinite(quantity) and quantity > 0
                and position.get("real_orders", False) is False)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False

def _last_logged_position():
    """Recover the latest position by scanning the JSONL log backwards in bounded chunks."""
    if not OUT.exists():
        return None
    chunk_size = 65536
    carry = b""
    try:
        with OUT.open("rb") as f:
            f.seek(0, os.SEEK_END)
            offset = f.tell()
            if offset == 0:
                raise RuntimeError("paper log is empty; refusing to assume flat position")
            f.seek(max(0, offset - 65536))
            tail_lines = f.read().splitlines()
            if tail_lines and tail_lines[-1].strip():
                try:
                    tail_record = json.loads(tail_lines[-1])
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise RuntimeError("paper log ends with malformed/partial JSONL; refusing position recovery") from exc
                if not isinstance(tail_record, dict) or "position" not in tail_record:
                    raise RuntimeError("paper log tail lacks a position field; refusing position recovery")
            while offset > 0:
                read_size = min(chunk_size, offset)
                offset -= read_size
                f.seek(offset)
                chunk = f.read(read_size) + carry
                lines = chunk.split(b"\n")
                carry = lines[0]
                for line in reversed(lines[1:]):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    if isinstance(record, dict) and "position" in record:
                        position = record["position"]
                        if not _valid_position(position):
                            raise RuntimeError("latest logged paper position is invalid; refusing recovery")
                        return position
            if carry.strip():
                try:
                    record = json.loads(carry)
                    if isinstance(record, dict) and "position" in record:
                        position = record["position"]
                        if not _valid_position(position):
                            raise RuntimeError("latest logged paper position is invalid; refusing recovery")
                        return position
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise RuntimeError("paper log has malformed leading record; refusing recovery") from exc
    except OSError as exc:
        raise RuntimeError("cannot read paper log; refusing to assume flat position") from exc
    raise RuntimeError("paper log has no recoverable position record; refusing to assume flat position")

def read(p, d):
    try:
        return json.loads(p.read_text())
    except Exception:
        return d

class Engine:
    def __init__(self):
        self.cfg = read(CONFIG, {})
        self.pos = None
        self.pending_trade = None
        self.rng = random.Random()
        if PAPER_RUNTIME_STATE.exists():
            try:
                saved=json.loads(PAPER_RUNTIME_STATE.read_text())
                if (saved.get("schema") != "pro_scalper_v6_runtime_state_v1"
                        or saved.get("paper_only") is not True
                        or saved.get("real_orders") is not False):
                    raise ValueError("runtime state schema/order-authority mismatch")
                position=saved.get("position")
                if not _valid_position(position):
                    raise ValueError("invalid persisted paper position")
                self.pos=position
                pending=saved.get("pending_trade")
                if pending is not None:
                    if (not isinstance(pending,dict) or not isinstance(pending.get("trade"),dict)
                            or not isinstance(pending.get("trade_id"),str) or len(pending["trade_id"]) != 64):
                        raise ValueError("invalid pending trade outbox")
                    trade=pending["trade"]
                    trade_id=pending["trade_id"]
                    if any(ch not in "0123456789abcdef" for ch in trade_id):
                        raise ValueError("invalid pending trade ID encoding")
                    if trade.get("paper_only") is not True or trade.get("real_orders") is not False:
                        raise ValueError("pending trade order-authority mismatch")
                    canonical=json.dumps(trade,sort_keys=True,separators=(",",":"),allow_nan=False)
                    expected_id=hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                    if trade_id != expected_id:
                        raise ValueError("pending trade ID does not match trade payload")
                self.pending_trade=pending
                if "rng_state" in saved:
                    self.rng.setstate(_tuplify(saved["rng_state"]))
            except Exception as exc:
                raise RuntimeError(f"Refusing to start V6 paper runner with invalid runtime state: {exc}") from exc
        else:
            # One-time migration: recover the latest logged paper position before
            # creating the runtime state file, so restart cannot silently drop it.
            self.pos=_last_logged_position()
            self._save_runtime_state()

    def _save_runtime_state(self):
        """Atomically persist paper position and RNG state; never authorizes orders."""
        PAPER_RUNTIME_STATE.parent.mkdir(parents=True, exist_ok=True)
        payload={
            "schema":"pro_scalper_v6_runtime_state_v1",
            "updated_at_epoch":time.time(),
            "position":self.pos,
            "pending_trade":self.pending_trade,
            "rng_state":self.rng.getstate(),
            "paper_only":True,
            "real_orders":False,
        }
        tmp=PAPER_RUNTIME_STATE.with_name(PAPER_RUNTIME_STATE.name+f".tmp.{os.getpid()}")
        try:
            with tmp.open("x",encoding="utf-8") as f:
                json.dump(payload,f,separators=(",",":"))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp,PAPER_RUNTIME_STATE)
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    def _cost_bps(self):
        maker = float(self.cfg.get("venue", {}).get("effective_maker_bps", 2.36))
        taker = float(self.cfg.get("venue", {}).get("effective_taker_bps", 5.90))
        slip = float(self.cfg.get("taker_slippage_bps", 1.0))
        adverse = float(self.cfg.get("maker_adverse_selection_bps", 1.5))
        # Apply the same configured round-trip floor used by the entry gate.
        floor = float(read(V5_CONFIG, {}).get("cost_floor_bps", 0.0))
        return max(floor, maker + taker + slip + adverse)

    def _exit_check(self, state, now):
        if not self.pos:
            return None
        ob = state.get("order_book", {})
        bid = float(ob.get("best_bid") or 0)
        ask = float(ob.get("best_ask") or 0)
        if bid <= 0 or ask <= 0:
            return None

        side = self.pos["side"]
        entry = float(self.pos["entry_px"])
        exit_px = bid if side == "LONG" else ask
        raw_bps = ((exit_px - entry) / entry * 10000.0) if side == "LONG" else ((entry - exit_px) / entry * 10000.0)

        target = float(self.cfg.get("paper_target_bps", 20.0))
        stop = float(self.cfg.get("paper_stop_bps", 10.0))
        max_hold = float(self.cfg.get("max_hold_seconds", 120.0))
        age = now - float(self.pos["entry_ts"])

        reason = None
        if raw_bps >= target:
            reason = "TARGET"
        elif raw_bps <= -stop:
            reason = "STOP"
        elif age >= max_hold:
            reason = "TIMEOUT"
        if reason is None:
            return None

        net_bps = raw_bps - self._cost_bps()
        notional = float(self.pos["entry_px"]) * float(self.pos["quantity_btc"])
        pnl_usd = notional * net_bps / 10000.0
        trade = {
            "side": side,
            "entry_px": entry,
            "exit_px": exit_px,
            "entry_ts": float(self.pos["entry_ts"]),
            "exit_ts": now,
            "hold_seconds": age,
            "raw_bps": raw_bps,
            "cost_bps": self._cost_bps(),
            "net_bps": net_bps,
            "pnl_usd": pnl_usd,
            "exit_reason": reason,
            "quantity_btc": float(self.pos["quantity_btc"]),
            "paper_only": True,
            "real_orders": False,
        }
        self.pos = None
        return trade

    def step(self, state, now=None):
        if self.pending_trade is not None:
            raise RuntimeError("Pending paper trade must be durably logged before another step")
        result=self._step(state,now=now)
        if result.get("trade"):
            trade_json=json.dumps(result["trade"],sort_keys=True,separators=(",",":"),allow_nan=False)
            trade_id=hashlib.sha256(trade_json.encode("utf-8")).hexdigest()
            self.pending_trade={"trade_id":trade_id,"ts":float(now or time.time()),**result}
        self._save_runtime_state()
        return result

    def flush_pending_trade(self):
        """Idempotently flush the durable trade outbox to the JSONL paper log."""
        record=self.pending_trade
        if record is None:
            return False
        OUT.parent.mkdir(parents=True,exist_ok=True)
        trade_id=record["trade_id"]
        # Scan existing records so a crash after append but before acknowledgement
        # cannot duplicate the trade on restart.
        if OUT.exists():
            with OUT.open("r",encoding="utf-8",errors="replace") as f:
                for line in f:
                    try:
                        if json.loads(line).get("trade_id")==trade_id:
                            break
                    except (json.JSONDecodeError,AttributeError):
                        continue
                else:
                    self._append_pending_record(record)
        else:
            self._append_pending_record(record)
        self.pending_trade=None
        self._save_runtime_state()
        return True

    @staticmethod
    def _append_pending_record(record):
        with OUT.open("a",encoding="utf-8") as f:
            f.write(json.dumps(record,separators=(",",":"),allow_nan=False)+"\n")
            f.flush()
            os.fsync(f.fileno())

    def log_result(self,result):
        """Durably log a step result; trades use the persisted idempotent outbox."""
        if self.pending_trade is not None:
            return self.flush_pending_trade()
        OUT.parent.mkdir(parents=True,exist_ok=True)
        with OUT.open("a",encoding="utf-8") as f:
            f.write(json.dumps({"ts":time.time(),**result},separators=(",",":"),allow_nan=False)+"\n")
            f.flush()
            os.fsync(f.fileno())
        return True

    def _step(self, state, now=None):
        now = float(now or time.time())

        closed = self._exit_check(state, now)
        if closed:
            return {"signal": None, "position": None, "trade": closed, "real_orders": False}

        sig = ensemble(
            state,
            now_ts=now,
            config={**self.cfg, **read(V5_CONFIG, {})},
        )

        if self.pos:
            return {"signal": sig, "position": self.pos, "trade": None, "real_orders": False}

        if sig["action"] not in ("LONG", "SHORT"):
            return {"signal": sig, "position": None, "trade": None, "real_orders": False}

        if self.rng.random() > float(self.cfg.get("maker_fill_probability", 0.30)):
            return {"signal": sig, "position": None, "trade": None, "reason": "MAKER_MISSED", "real_orders": False}

        ob = state.get("order_book", {})
        px = float(ob.get("best_bid") if sig["action"] == "LONG" else ob.get("best_ask"))
        if px <= 0:
            return {"signal": sig, "position": None, "trade": None, "reason": "NO_EXECUTABLE_PRICE", "real_orders": False}

        qty = 0.001
        self.pos = {
            "side": sig["action"],
            "entry_px": px,
            "entry_ts": now,
            "quantity_btc": qty,
            "entry_type": "MAKER",
            "paper_only": True,
        }
        return {"signal": sig, "position": self.pos, "trade": None, "real_orders": False}

def main():
    e = Engine()
    r = e.step(read(STATE, {}))
    e.log_result(r)
    print(json.dumps(r))

if __name__ == "__main__":
    main()
