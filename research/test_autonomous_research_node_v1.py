import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import research.autonomous_research_node_v1 as node

class AutonomousResearchNodeTests(unittest.TestCase):
    def test_missing_state_fails_closed(self):
        with patch.object(node, 'STATE', Path('/does/not/exist/state.json')), \
             patch.object(node, 'CANDLES', Path('/does/not/exist/candles.json')), \
             patch.object(node, 'POLICY', Path('/does/not/exist/policy.json')), \
             patch.object(node, 'KILL', Path('/does/not/exist/kill')):
            h = node.health_snapshot(now=100)
        self.assertEqual(h['state'], 'HALT_FAIL_CLOSED')
        self.assertIn('STATE_MISSING', h['reasons'])
        self.assertFalse(h['real_orders'])

    def test_fresh_valid_state_passes_market_checks_but_never_orders(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            state = p/'state.json'; candles = p/'candles.json'; policy = p/'policy.json'; kill = p/'kill'
            state.write_text(json.dumps({'updated_at_epoch': 99.9, 'quality': {'fresh_seconds': .1},
                'order_book': {'best_bid': 100, 'best_ask': 101, 'mid_price': 100.5}, 'regime': 'BALANCED'}))
            candles.write_text('[{"timestamp":1},{"timestamp":2}]')
            policy.write_text('{"status":"BLOCKED_UNTIL_VALIDATED"}')
            with patch.object(node, 'STATE', state), patch.object(node, 'CANDLES', candles), \
                 patch.object(node, 'POLICY', policy), patch.object(node, 'KILL', kill):
                h = node.health_snapshot(now=100)
        self.assertEqual(h['state'], 'HEALTHY')
        self.assertFalse(h['real_orders'])

    def test_promotion_needs_sample_edge_and_profit_factor(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); policy = p/'policy.json'; summary = p/'summary.json'
            policy.write_text('{"status":"BLOCKED_UNTIL_VALIDATED","minimum_labeled_trades":100,"minimum_profit_factor":1.2}')
            summary.write_text('{"trades":6,"avg_net_bps":-9.2,"profit_factor":0.02,"real_orders":false}')
            with patch.object(node, 'POLICY', policy), patch.object(node, 'PAPER_SUMMARY', summary):
                e = node.evaluate_evidence()
        self.assertEqual(e['status'], 'INSUFFICIENT_OR_NEGATIVE_EVIDENCE')
        self.assertIn('MINIMUM_100_TRADES_NOT_MET', e['blockers'])
        self.assertIn('POSITIVE_NET_EXPECTANCY_NOT_MET', e['blockers'])
        self.assertFalse(e['real_orders'])

if __name__ == '__main__': unittest.main()
