from research.delta_product_margin_schema_audit_v1 import resolve_product_margin_metadata


def product(**overrides):
    row = {
        "id": 27, "symbol": "BTCUSD", "state": "live", "trading_status": "operational",
        "notional_type": "inverse", "contract_type": "perpetual_futures",
        "contract_value": "0.001", "contract_unit_currency": "BTC",
        "maintenance_margin": "0.25", "maintenance_margin_scaling_factor": "0.00000125",
        "initial_margin": "0.5", "initial_margin_scaling_factor": "0.0000025",
        "product_specs": {},
    }
    row.update(overrides)
    return row


def test_resolves_exact_product_and_preserves_raw_margin_units():
    result = resolve_product_margin_metadata({"success": True, "result": [product()]}, "btcusd")
    assert result.status == "METADATA_RESOLVED_RATE_NOT_CERTIFIED"
    assert result.product_id == 27
    assert result.notional_type == "inverse"
    assert result.contract_value == 0.001
    assert result.maintenance_margin_raw == 0.25
    assert result.maintenance_margin_scaling_factor_raw == 0.00000125
    assert result.rate_conversion_status == "UNRESOLVED_UNITS_AND_FORMULA"


def test_rejects_missing_and_duplicate_product_matches():
    missing = resolve_product_margin_metadata({"success": True, "result": [product()]}, "ETHUSD")
    duplicate = resolve_product_margin_metadata({"success": True, "result": [product(), product()]}, "BTCUSD")
    assert missing.reason == "PRODUCT_NOT_FOUND"
    assert duplicate.reason == "AMBIGUOUS_PRODUCT_MATCH"


def test_rejects_product_that_is_not_live_and_operational():
    result = resolve_product_margin_metadata({"success": True, "result": product(state="expired")}, "BTCUSD")
    assert result.reason == "PRODUCT_NOT_LIVE_AND_OPERATIONAL"


def test_rejects_missing_margin_scaling_factor_without_guessing():
    result = resolve_product_margin_metadata({"success": True, "result": product(maintenance_margin_scaling_factor=None)}, "BTCUSD")
    assert result.reason == "MISSING_OR_INVALID_MAINTENANCE_SCALING_FACTOR"


def test_rejects_unknown_contract_denominator():
    result = resolve_product_margin_metadata({"success": True, "result": product(contract_unit_currency=None)}, "BTCUSD")
    assert result.reason == "MISSING_CONTRACT_UNIT_CURRENCY"


def test_rejects_unsupported_notional_type_and_invalid_numbers():
    a = resolve_product_margin_metadata({"success": True, "result": product(notional_type="unknown")}, "BTCUSD")
    b = resolve_product_margin_metadata({"success": True, "result": product(maintenance_margin="NaN")}, "BTCUSD")
    assert a.reason == "UNKNOWN_NOTIONAL_TYPE"
    assert b.reason == "MISSING_OR_INVALID_MAINTENANCE_MARGIN"
