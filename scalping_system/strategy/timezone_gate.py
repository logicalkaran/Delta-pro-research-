"""UTC session gate for BTC microstructure research/execution.

This is an eligibility filter, not a profitability guarantee. UTC is used so
DST changes in London/New York do not silently shift the strategy.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass(frozen=True)
class SessionConfig:
    # Primary liquidity/price-discovery window.
    core_start_utc: int = 13
    core_end_utc: int = 17
    # Secondary European window; useful for measuring pre-overlap continuation.
    secondary_start_utc: int = 8
    secondary_end_utc: int = 13
    # Avoid thin weekend conditions by default.
    weekdays_only: bool = True

def session_state(ts=None, cfg=SessionConfig()):
    dt = datetime.now(timezone.utc) if ts is None else datetime.fromtimestamp(float(ts), timezone.utc)
    h = dt.hour + dt.minute / 60.0
    weekday = dt.weekday() < 5
    if cfg.weekdays_only and not weekday:
        return {"allowed": False, "session": "WEEKEND", "utc_hour": h, "weekday": False}
    if cfg.core_start_utc <= h < cfg.core_end_utc:
        return {"allowed": True, "session": "LONDON_NY_CORE", "utc_hour": h, "weekday": True}
    if cfg.secondary_start_utc <= h < cfg.secondary_end_utc:
        return {"allowed": True, "session": "EUROPE_SECONDARY", "utc_hour": h, "weekday": True}
    return {"allowed": False, "session": "LOW_PRIORITY", "utc_hour": h, "weekday": True}

def gate(ts=None, cfg=SessionConfig()):
    s = session_state(ts, cfg)
    if not s["allowed"]:
        return {"allowed": False, "reason": "TIMEZONE_BLOCK", **s}
    return {"allowed": True, "reason": "SESSION_ALLOWED", **s}
