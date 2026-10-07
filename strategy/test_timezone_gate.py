from strategy.timezone_gate import session_state, gate
from datetime import datetime, timezone

def ts(h, weekday=1):
    return datetime(2026, 10, 7, h, 0, tzinfo=timezone.utc).timestamp()

assert session_state(ts(14))["session"] == "LONDON_NY_CORE"
assert gate(ts(14))["allowed"] is True
assert gate(ts(3))["allowed"] is False
assert gate(datetime(2026, 10, 10, 14, tzinfo=timezone.utc).timestamp())["allowed"] is False
print("TIMEZONE GATE TESTS: 3/3 PASS")
