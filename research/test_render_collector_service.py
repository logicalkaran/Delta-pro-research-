import importlib.util
import json
import time
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "render_collector_service.py"
SPEC = importlib.util.spec_from_file_location("render_collector_service", P)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def test_missing_state_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(M, "STATE_FILES", (tmp_path / "missing.json",))
    assert M.latest_state()["ok"] is False
    assert M.latest_state()["reason"] == "NO_VALID_STATE_FILE"


def test_fresh_valid_local_state_is_ready(monkeypatch, tmp_path):
    p = tmp_path / "live_market_state.json"
    p.write_text(json.dumps({"updated_at": time.time(), "symbol": "BTCUSD", "mid_price": 80000}))
    monkeypatch.setattr(M, "STATE_FILES", (p,))
    result = M.latest_state()
    assert result["ok"] is True
    assert result["mid_or_last_price_present"] is True
    assert "not_exchange_event_time" in result["timestamp_kind"]


def test_stale_state_is_not_ready(monkeypatch, tmp_path):
    p = tmp_path / "live_market_state.json"
    p.write_text(json.dumps({"updated_at": time.time() - 1000, "symbol": "BTCUSD", "mid_price": 80000}))
    monkeypatch.setattr(M, "STATE_FILES", (p,))
    result = M.latest_state()
    assert result["ok"] is False
    assert result["reason"] == "STALE_STATE"


def test_invalid_price_fails_closed(monkeypatch, tmp_path):
    p = tmp_path / "live_market_state.json"
    p.write_text(json.dumps({"updated_at": time.time(), "symbol": "BTCUSD", "mid_price": 0}))
    monkeypatch.setattr(M, "STATE_FILES", (p,))
    result = M.latest_state()
    assert result["ok"] is False
    assert result["reason"] == "INVALID_PRICE"


def test_liveness_is_separate_from_readiness():
    # Liveness endpoint is designed to respond even when feed is stale;
    # readiness endpoint uses the feed status and collector process state.
    assert M.MAX_STALE_SECONDS >= 5
    assert "live_orders_enabled" in M.status_payload()
    assert M.status_payload()["live_orders_enabled"] is False


def _http_status(monkeypatch, state_file, path):
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from urllib.request import urlopen
    import urllib.error

    class FakeChild:
        pid = 123
        def poll(self):
            return None

    monkeypatch.setattr(M, "STATE_FILES", (state_file,))
    monkeypatch.setattr(M, "_child", FakeChild())
    server = ThreadingHTTPServer(("127.0.0.1", 0), M.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}{path}"
        try:
            with urlopen(url, timeout=2) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_healthz_is_liveness_not_feed_readiness(monkeypatch, tmp_path):
    p = tmp_path / "stale.json"
    p.write_text(json.dumps({"updated_at": time.time() - 1000, "symbol": "BTCUSD", "mid_price": 80000}))
    code, body = _http_status(monkeypatch, p, "/healthz")
    assert code == 200
    assert body["ok"] is True
    code, body = _http_status(monkeypatch, p, "/readyz")
    assert code == 503
    assert body["feed"]["reason"] == "STALE_STATE"


def test_http_readyz_200_for_fresh_state(monkeypatch, tmp_path):
    p = tmp_path / "fresh.json"
    p.write_text(json.dumps({"updated_at": time.time(), "symbol": "BTCUSD", "mid_price": 80000}))
    code, body = _http_status(monkeypatch, p, "/readyz")
    assert code == 200
    assert body["feed"]["ok"] is True
    assert body["live_orders_enabled"] is False
