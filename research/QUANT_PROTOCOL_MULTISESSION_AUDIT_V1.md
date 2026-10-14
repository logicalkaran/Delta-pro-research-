# Multi-session bounded capture audit v1

Run this only after bounded sessions have been captured separately. It does not start or schedule capture.

```sh
cd ~/btc_fisher_trader
PYTHONPATH=. pytest -q research/test_quant_protocol_multisession_audit_v1.py
PYTHONPATH=. python research/quant_protocol_multisession_audit_v1.py
```

For every manifest, the audit checks session ID uniqueness, 300-second runtime bound, raw and aligned file caps, aligned SHA-256, raw artifact existence, row accounting, clean collector shutdown, and order-book checksum reconstruction within that session. Each session is independently replayed so state is not carried between sessions.

A PASS means only that the capture artifacts passed these integrity checks. It does not prove continuity across reconnects, predictive signal, profitability, or live-trading readiness. Capture is intentionally not launched by this script.
