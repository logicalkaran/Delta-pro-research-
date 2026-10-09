import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path

from paper.delta_margin_sentinel_api import (
    AlertJournal,
    DeltaReadOnlyClient,
    DeltaReadOnlyError,
    signature,
    wallet_summary,
)
from paper.margin_sentinel_readonly import evaluate_position


class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self.payload = json.dumps(payload).encode()

    def read(self):
        return self.payload


class FakeConnection:
    def __init__(self, host, port, timeout, response=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.response = response or FakeResponse(200, {"success": True, "result": []})
        self.calls = []
        self.closed = False

    def request(self, method, path, headers):
        self.calls.append((method, path, headers))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class DeltaMarginSentinelApiTests(unittest.TestCase):
    def test_signature_matches_hmac_sha256(self):
        expected = hmac.new(b"secret", b"GET123/v2/positions/margined", hashlib.sha256).hexdigest()
        self.assertEqual(signature("secret", "GET", "123", "/v2/positions/margined"), expected)

    def test_host_allowlist_rejects_untrusted_origin(self):
        with self.assertRaises(ValueError):
            DeltaReadOnlyClient("key", "secret", "https://evil.example")

    def test_endpoint_allowlist_rejects_mutating_path(self):
        client = DeltaReadOnlyClient("key", "secret")
        with self.assertRaises(ValueError):
            client.get_json("/v2/positions/change_margin")

    def test_client_sends_get_only_and_closes_connection(self):
        conn = FakeConnection("api.india.delta.exchange", 443, 8.0)
        client = DeltaReadOnlyClient("key", "secret", connection_factory=lambda *a, **k: conn)
        result = client.get_json("/v2/positions/margined")
        self.assertTrue(result["success"])
        self.assertEqual(conn.calls[0][0], "GET")
        self.assertEqual(conn.calls[0][1], "/v2/positions/margined")
        self.assertIn("signature", conn.calls[0][2])
        self.assertTrue(conn.closed)

    def test_http_error_does_not_return_body(self):
        conn = FakeConnection("api.india.delta.exchange", 443, 8.0, FakeResponse(403, {"private": "account data"}))
        client = DeltaReadOnlyClient("key", "secret", connection_factory=lambda *a, **k: conn)
        with self.assertRaisesRegex(DeltaReadOnlyError, "HTTP 403") as cm:
            client.get_json("/v2/wallet/balances")
        self.assertNotIn("account data", str(cm.exception))

    def test_wallet_summary_does_not_claim_available_collateral(self):
        rows = wallet_summary({"success": True, "result": [{
            "asset": {"symbol": "USDT"},
            "balance": "100",
            "order_margin": "10",
            "position_margin": "50",
        }]})
        self.assertEqual(rows[0]["asset"], "USDT")
        self.assertIn("balance", rows[0]["balance_fields_present"])
        self.assertTrue(rows[0]["account_values_withheld"])
        self.assertNotIn("balance", rows[0])
        self.assertNotIn("available_collateral", rows[0])

    def test_missing_maintenance_margin_is_review_not_false_utilization(self):
        pos = {
            "product_symbol": "BTCUSD", "size": 1, "margin_mode": "isolated",
            "mark_price": "100", "liquidation_price": "96", "margin": "20",
            "unrealized_pnl": "0",
        }
        result = evaluate_position(pos)
        self.assertEqual(result["status"], "ALERT")
        self.assertIsNone(result["utilization_estimate"])
        self.assertIn("MAINTENANCE_MARGIN_METRIC_UNAVAILABLE", result["reasons"])

    def test_missing_maintenance_margin_without_other_breach_requires_review(self):
        pos = {
            "product_symbol": "BTCUSD", "size": 1, "margin_mode": "isolated",
            "mark_price": "100", "liquidation_price": "80", "margin": "20",
            "unrealized_pnl": "0",
        }
        result = evaluate_position(pos)
        self.assertEqual(result["status"], "REVIEW_INCOMPLETE_METRICS")
        self.assertIsNone(result["utilization_estimate"])

    def test_journal_deduplicates_unchanged_state_and_records_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = AlertJournal(Path(tmp) / "events.sqlite3")
            first = {"symbol": "BTCUSD", "status": "ALERT", "reasons": ["LIQUIDATION_DISTANCE_THRESHOLD"]}
            self.assertEqual(journal.record_changes([first]), 1)
            self.assertEqual(journal.record_changes([first]), 0)
            changed = {"symbol": "BTCUSD", "status": "OK", "reasons": []}
            self.assertEqual(journal.record_changes([changed]), 1)
            count = journal.db.execute("SELECT COUNT(*) FROM sentinel_events").fetchone()[0]
            self.assertEqual(count, 2)
            journal.close()

    def test_source_contains_no_mutating_http_verb(self):
        import inspect
        import paper.delta_margin_sentinel_api as module
        source = inspect.getsource(module)
        self.assertNotIn('conn.request("POST"', source)
        self.assertNotIn('conn.request("PUT"', source)
        self.assertNotIn('conn.request("DELETE"', source)


if __name__ == "__main__":
    unittest.main()
