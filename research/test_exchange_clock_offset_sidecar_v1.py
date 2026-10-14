import unittest
from research.exchange_clock_offset_sidecar_v1 import parse_server_epoch_ms


class ClockOffsetTests(unittest.TestCase):
    def test_binance_server_time_ms(self):
        self.assertEqual(parse_server_epoch_ms({"serverTime": 1700000000123}), 1700000000123)

    def test_generic_timestamp_is_not_mislabelled_as_server_time(self):
        self.assertIsNone(parse_server_epoch_ms({"success": True, "result": {"timestamp": 1700000000123}}))

    def test_missing_time_is_none(self):
        self.assertIsNone(parse_server_epoch_ms({"success": True, "result": {"message": "ok"}}))


if __name__ == "__main__":
    unittest.main()
