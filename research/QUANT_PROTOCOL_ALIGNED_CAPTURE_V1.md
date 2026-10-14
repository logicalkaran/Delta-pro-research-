# Quantitative Protocol Aligned Capture v1

This sidecar captures flow features and L5 price/size levels from the same local state refresh, so future analysis can align them without joining disjoint historical windows.

Run only while the existing Delta public WebSocket collector is active:
```sh
cd ~/btc_fisher_trader
.venv/bin/python -m pytest research/test_quant_protocol_aligned_capture_v1.py -q
.venv/bin/python research/quant_protocol_aligned_capture_v1.py --seconds 21600
```

The default capture is six hours, one unique output file per session, max 20 MB, no overwrite, and stops when the file cap is reached. Output is under `data/raw/quant_protocol_aligned/`. Use `--seconds` to select a shorter smoke test. The script reads the local state file only; it does not start or control the WebSocket collector.

Important limitations: `updated_at_epoch` is a local state-refresh timestamp, not an exchange-native event timestamp. OFI computed from these samples is sampled-state delta, not event-level OFI. Trade-side semantics must be independently verified. The capture is research-only and has no order/execution access.
