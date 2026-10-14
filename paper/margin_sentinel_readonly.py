#!/usr/bin/env python3
"""Read-only Delta isolated-margin sentinel.

Consumes a saved JSON response/snapshot; deliberately has no network client,
credentials, background loop, or margin/order mutation capability.
"""
from __future__ import annotations

import argparse
import json
import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

LOG = logging.getLogger("MarginSentinelReadOnly")


def dec(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field}") from exc
    if not result.is_finite():
        raise ValueError(f"non-finite {field}")
    return result


def extract_positions(payload: Any) -> list[dict[str, Any]]:
    """Accept either an API-style {'result': [...]} or a raw position list."""
    if isinstance(payload, dict):
        payload = payload.get("result")
    if not isinstance(payload, list) or any(not isinstance(p, dict) for p in payload):
        raise ValueError("snapshot must be a list of position objects or an object with list 'result'")
    return payload


def evaluate_position(
    pos: dict[str, Any],
    *,
    symbol: str = "BTCUSD",
    utilization_threshold: Decimal = Decimal("0.75"),
    liquidation_distance_threshold_pct: Decimal = Decimal("5.0"),
) -> dict[str, Any]:
    """Return a diagnostic only; never recommends or performs a collateral transfer."""
    found_symbol = str(pos.get("product_symbol", pos.get("symbol", ""))).upper()
    if found_symbol != symbol.upper():
        return {"symbol": found_symbol, "status": "IGNORED_SYMBOL", "paper_only": True}

    size = dec(pos.get("size", "0"), "size")
    if size == 0:
        return {"symbol": found_symbol, "status": "NO_OPEN_POSITION", "paper_only": True}

    margin_mode = str(pos.get("margin_mode", "")).lower()
    if margin_mode != "isolated":
        return {
            "symbol": found_symbol,
            "status": "REVIEW_MARGIN_MODE",
            "margin_mode": margin_mode or "unknown",
            "paper_only": True,
        }

    # Fail closed on missing/invalid core prices and margin fields.
    mark = dec(pos.get("mark_price"), "mark_price")
    liq = dec(pos.get("liquidation_price"), "liquidation_price")
    margin = dec(pos.get("margin"), "margin")
    mm_raw = pos.get("maintenance_margin")
    mm = dec(mm_raw, "maintenance_margin") if mm_raw is not None else None
    upnl = dec(pos.get("unrealized_pnl", "0"), "unrealized_pnl")
    if mark <= 0 or liq <= 0 or margin < 0 or (mm is not None and mm < 0):
        raise ValueError("mark/liquidation prices must be positive; margin fields cannot be negative")

    side_raw = str(pos.get("side", "")).lower()
    # If the API omits side, infer only from signed size when available.
    side = side_raw if side_raw in ("long", "short") else (
        "long" if size > 0 else "short" if size < 0 else "unknown"
    )
    effective_margin = margin + upnl
    utilization = (
        (mm / effective_margin) if effective_margin > 0 else Decimal("Infinity")
    ) if mm is not None else None
    distance_pct = abs(mark - liq) / mark * Decimal("100")
    if side == "long":
        toward_liquidation = mark <= liq
    elif side == "short":
        toward_liquidation = mark >= liq
    else:
        toward_liquidation = False

    reasons: list[str] = []
    if effective_margin <= 0:
        reasons.append("NON_POSITIVE_EFFECTIVE_MARGIN")
    if utilization is None:
        reasons.append("MAINTENANCE_MARGIN_METRIC_UNAVAILABLE")
    elif utilization >= utilization_threshold:
        reasons.append("MARGIN_UTILIZATION_THRESHOLD")
    if distance_pct <= liquidation_distance_threshold_pct:
        reasons.append("LIQUIDATION_DISTANCE_THRESHOLD")
    if toward_liquidation:
        reasons.append("MARK_AT_OR_BEYOND_LIQUIDATION_ESTIMATE")

    status = "ALERT" if any(r != "MAINTENANCE_MARGIN_METRIC_UNAVAILABLE" for r in reasons) else (
        "REVIEW_INCOMPLETE_METRICS" if reasons else "OK"
    )
    return {
        "symbol": found_symbol,
        "side": side,
        "size": str(size),
        "mark_price": str(mark),
        "liquidation_price_reported": str(liq),
        "liquidation_distance_pct": str(distance_pct),
        "allocated_margin": str(margin),
        "unrealized_pnl": str(upnl),
        "maintenance_margin_reported": str(mm) if mm is not None else None,
        "effective_margin_estimate": str(effective_margin),
        "utilization_estimate": str(utilization) if utilization is not None else None,
        "status": status,
        "reasons": reasons,
        "action": "ALERT_ONLY_NO_COLLATERAL_TRANSFER",
        "paper_only": True,
        "real_orders": False,
        "warning": (
            "Diagnostic estimates only. Verify Delta's current API schema, margin mode, "
            "position side/sign, maintenance-margin definition, and official liquidation rules. "
            "No collateral transfer is performed."
        ),
    }


def evaluate_snapshot(payload: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return [evaluate_position(pos, **kwargs) for pos in extract_positions(payload)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="JSON file containing a positions response/snapshot")
    parser.add_argument("--symbol", default="BTCUSD")
    parser.add_argument("--utilization-threshold", default="0.75")
    parser.add_argument("--liquidation-distance-pct", default="5.0")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        payload = json.loads(args.snapshot.read_text(encoding="utf-8"))
        results = evaluate_snapshot(
            payload,
            symbol=args.symbol,
            utilization_threshold=dec(args.utilization_threshold, "utilization threshold"),
            liquidation_distance_threshold_pct=dec(args.liquidation_distance_pct, "liquidation distance threshold"),
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        LOG.error("Fail-closed: %s", exc)
        return 2
    print(json.dumps({
        "mode": "READ_ONLY_DIAGNOSTIC",
        "positions": results,
        "network_enabled": False,
        "collateral_transfer_enabled": False,
        "real_orders": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
