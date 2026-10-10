from __future__ import annotations

import hashlib
import hmac
from urllib.parse import urlsplit

import pytest

from exchange.delta_state_adapter import DeltaReadOnlyStateAdapter
from execution.delta_signer import sign


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_signature_matches_delta_signer_and_signed_query_is_exact():
    captured = {}
    def transport(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response({"success": True, "result": []})
    adapter = DeltaReadOnlyStateAdapter(api_key="key-secret", api_secret="test-secret", base_url=DeltaReadOnlyStateAdapter.DEMO,
                                        transport=transport, clock=lambda: 1000.0)
    adapter._get("/v2/orders", {"product_symbol": "BTC-PERP", "page_size": 10})
    parsed = urlsplit(captured["url"])
    assert parsed.query == "page_size=10&product_symbol=BTC-PERP"
    headers = captured["headers"]
    assert headers["api-key"] == "key-secret"
    expected = sign("test-secret", "GET", "1000", "/v2/orders", parsed.query, "")
    assert hmac.compare_digest(headers["signature"], expected)
    assert headers["timestamp"] == "1000"


def test_signature_timestamp_must_be_within_five_seconds():
    adapter = DeltaReadOnlyStateAdapter(api_key="k", api_secret="s", clock=lambda: 1000.0, transport=lambda *a, **k: Response({}))
    assert adapter._headers("/v2/wallets", "", timestamp=995)["timestamp"] == "995"
    with pytest.raises(ValueError, match="5-second"):
        adapter._headers("/v2/wallets", "", timestamp=994)
    with pytest.raises(ValueError, match="5-second"):
        adapter._headers("/v2/wallets", "", timestamp=1006)


def test_only_allowlisted_get_paths_are_available():
    adapter = DeltaReadOnlyStateAdapter(api_key="k", api_secret="s", transport=lambda *a, **k: Response({}), clock=lambda: 1000.0)
    with pytest.raises(ValueError, match="allowlisted"):
        adapter._get("/v2/orders/1/cancel")
    assert not hasattr(adapter, "place_order")
    assert not hasattr(adapter, "cancel_order")
    assert not hasattr(adapter, "request")


def test_transport_exception_redacts_url_and_credentials():
    def failing(url, **kwargs):
        raise OSError("failed for https://host/path?secret=key-secret API_SECRET=test-secret")
    adapter = DeltaReadOnlyStateAdapter(api_key="key-secret", api_secret="test-secret", transport=failing, clock=lambda: 1000.0)
    with pytest.raises(RuntimeError) as error:
        adapter.get_wallets()
    assert "key-secret" not in str(error.value)
    assert "test-secret" not in str(error.value)
    assert "https://" not in str(error.value)


def test_missing_account_fields_are_marked_incomplete_not_fabricated():
    def transport(url, **kwargs):
        return Response({"success": True, "result": [{"asset_symbol": "USD"}]})
    adapter = DeltaReadOnlyStateAdapter(api_key="k", api_secret="s", transport=transport, clock=lambda: 1000.0)
    state = adapter.account_state(observed_at_ms=1000000)
    assert state.available_balance is None
    assert state.equity is None
    assert state.maintenance_margin is None
    assert state.open_interest is None
    assert state.complete is False
    assert set(state.missing_fields) == {"available_balance", "equity", "maintenance_margin"}
    assert state.observed_at_ms == 1000000


def test_schema_failure_does_not_echo_secrets():
    adapter = DeltaReadOnlyStateAdapter(api_key="k", api_secret="s", transport=lambda *a, **k: Response(["unexpected"]), clock=lambda: 1000.0)
    with pytest.raises(ValueError, match="schema invalid"):
        adapter.get_wallets()


def test_authoritative_equity_anchor_is_hourly_idempotent_and_hash_chained(tmp_path):
    from exchange.delta_state_adapter import AccountState
    from storage.event_journal import EventJournal
    adapter = DeltaReadOnlyStateAdapter(api_key="k", api_secret="s", transport=lambda *a, **k: Response({}), clock=lambda: 1000.0)
    with EventJournal(tmp_path / "anchors.sqlite") as journal:
        state = AccountState(available_balance=90.0, equity=100.0, maintenance_margin=2.0,
                             open_interest=None, complete=False, missing_fields=("open_interest",),
                             observed_at_ms=3_600_100)
        first = adapter.checkpoint_equity_hourly(state, journal)
        again = adapter.checkpoint_equity_hourly(state, journal)
        assert first["event_id"] == again["event_id"]
        assert len(journal.replay()) == 1
        assert journal.replay()[0]["event_type"] == "AUTHORITATIVE_EQUITY_ANCHOR"
        later = AccountState(available_balance=90.0, equity=101.0, maintenance_margin=2.0,
                             open_interest=None, complete=False, missing_fields=("open_interest",),
                             observed_at_ms=7_200_100)
        adapter.checkpoint_equity_hourly(later, journal)
        assert len(journal.replay()) == 2
        assert journal.verify()["valid"] is True


def test_equity_anchor_is_skipped_when_equity_is_missing(tmp_path):
    from exchange.delta_state_adapter import AccountState
    from storage.event_journal import EventJournal
    adapter = DeltaReadOnlyStateAdapter(api_key="k", api_secret="s", transport=lambda *a, **k: Response({}), clock=lambda: 1000.0)
    with EventJournal(tmp_path / "anchors.sqlite") as journal:
        state = AccountState(None, None, None, None, False,
                             ("available_balance", "equity", "maintenance_margin", "open_interest"), 3_600_100)
        assert adapter.checkpoint_equity_hourly(state, journal) is None
        assert journal.replay() == []
