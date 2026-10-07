import os
import unittest
from unittest.mock import patch

from execution.live_execution_gate import check, require, LiveExecutionBlocked


class TestLiveExecutionGate(unittest.TestCase):
    def test_default_is_locked(self):
        os.environ.pop("BTC_LIVE_EXECUTION", None)
        os.environ.pop("BTC_LIVE_OPERATOR_APPROVED", None)
        result = check()
        self.assertFalse(result["eligible"])
        self.assertIn("PROMOTION_POLICY_BLOCKED", result["reasons"])
        self.assertIn("BTC_LIVE_EXECUTION_NOT_ENABLED", result["reasons"])
        self.assertIn("BTC_LIVE_OPERATOR_APPROVED_NOT_ENABLED", result["reasons"])

    def test_require_blocks_when_policy_is_blocked(self):
        with patch.dict(os.environ, {
            "BTC_LIVE_EXECUTION": "true",
            "BTC_LIVE_OPERATOR_APPROVED": "true",
        }, clear=False):
            with self.assertRaises(LiveExecutionBlocked):
                require()


if __name__ == "__main__":
    unittest.main()
