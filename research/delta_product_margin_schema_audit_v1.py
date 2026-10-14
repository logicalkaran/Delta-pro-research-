"""Research-only Delta product margin schema resolver.

No production margin rate is calculated and no exchange state is mutated.
Raw product fields are resolved while uncertain units/formulas fail closed.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
from typing import Any, Mapping

@dataclass(frozen=True)
class ProductMarginMetadata:
    status: str
    symbol: str
    product_id: int | None = None
    notional_type: str | None = None
    contract_type: str | None = None
    contract_value: float | None = None
    contract_unit_currency: str | None = None
    maintenance_margin_raw: float | None = None
    maintenance_margin_scaling_factor_raw: float | None = None
    initial_margin_raw: float | None = None
    initial_margin_scaling_factor_raw: float | None = None
    source: str = "Delta product metadata response"
    rate_conversion_status: str = "UNRESOLVED_UNITS_AND_FORMULA"
    reason: str | None = None
    def to_dict(self) -> dict[str, Any]: return asdict(self)

def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None: return None
    try: n = float(value)
    except (TypeError, ValueError): return None
    return n if math.isfinite(n) else None

def resolve_product_margin_metadata(payload: Mapping[str, Any], symbol: str) -> ProductMarginMetadata:
    """Resolve exactly one live/operational product, preserving raw field units."""
    wanted = str(symbol).strip().upper()
    if not wanted or not isinstance(payload, Mapping) or payload.get("success") is False:
        return ProductMarginMetadata("REJECTED", wanted, reason="INVALID_PRODUCT_RESPONSE")
    result = payload.get("result")
    rows = [result] if isinstance(result, Mapping) else result if isinstance(result, list) else None
    if rows is None: return ProductMarginMetadata("REJECTED", wanted, reason="MALFORMED_PRODUCT_RESULT")
    matches = [r for r in rows if isinstance(r, Mapping) and str(r.get("symbol", "")).strip().upper() == wanted]
    if len(matches) != 1:
        return ProductMarginMetadata("REJECTED", wanted, reason="PRODUCT_NOT_FOUND" if not matches else "AMBIGUOUS_PRODUCT_MATCH")
    row = matches[0]
    if str(row.get("state", "")).lower() != "live" or str(row.get("trading_status", "")).lower() != "operational":
        return ProductMarginMetadata("REJECTED", wanted, reason="PRODUCT_NOT_LIVE_AND_OPERATIONAL")
    pid = row.get("id")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return ProductMarginMetadata("REJECTED", wanted, reason="INVALID_PRODUCT_ID")
    specs = row.get("product_specs")
    if specs is not None and not isinstance(specs, Mapping):
        return ProductMarginMetadata("REJECTED", wanted, reason="MALFORMED_PRODUCT_SPECS")
    mm, mms = _number(row.get("maintenance_margin")), _number(row.get("maintenance_margin_scaling_factor"))
    im, ims = _number(row.get("initial_margin")), _number(row.get("initial_margin_scaling_factor"))
    cv = _number(row.get("contract_value"))
    if mm is None or mm <= 0: return ProductMarginMetadata("REJECTED", wanted, reason="MISSING_OR_INVALID_MAINTENANCE_MARGIN")
    if mms is None or mms < 0: return ProductMarginMetadata("REJECTED", wanted, reason="MISSING_OR_INVALID_MAINTENANCE_SCALING_FACTOR")
    if im is None or im <= 0 or ims is None or ims < 0:
        return ProductMarginMetadata("REJECTED", wanted, reason="MISSING_OR_INVALID_INITIAL_MARGIN_METADATA")
    if cv is None or cv <= 0: return ProductMarginMetadata("REJECTED", wanted, reason="MISSING_OR_INVALID_CONTRACT_VALUE")
    nt = str(row.get("notional_type", "")).lower()
    if nt not in {"vanilla", "inverse"}: return ProductMarginMetadata("REJECTED", wanted, reason="UNKNOWN_NOTIONAL_TYPE")
    unit = row.get("contract_unit_currency")
    if not isinstance(unit, str) or not unit.strip():
        return ProductMarginMetadata("REJECTED", wanted, reason="MISSING_CONTRACT_UNIT_CURRENCY")
    return ProductMarginMetadata(
        status="METADATA_RESOLVED_RATE_NOT_CERTIFIED", symbol=wanted, product_id=pid,
        notional_type=nt, contract_type=str(row["contract_type"]) if row.get("contract_type") else None,
        contract_value=cv, contract_unit_currency=unit.strip().upper(),
        maintenance_margin_raw=mm, maintenance_margin_scaling_factor_raw=mms,
        initial_margin_raw=im, initial_margin_scaling_factor_raw=ims,
        reason="RAW_FIELDS_RESOLVED_BUT_RATE_FORMULA_AND_UNITS_REQUIRE_VERIFICATION")
