from execution.delta_reconciler import DeltaReconciler


def reconciler():
    return DeltaReconciler(client=object())


def test_rejects_explicit_order_api_failure():
    assert reconciler().assert_consistent(
        {"success": False, "result": []}, {"success": True, "result": []}
    ) == (False, "ORDER_STATE_UNAVAILABLE")


def test_rejects_explicit_position_api_failure():
    assert reconciler().assert_consistent(
        {"success": True, "result": []}, {"success": False, "result": []}
    ) == (False, "POSITION_STATE_UNAVAILABLE")


def test_rejects_malformed_order_and_position_shapes():
    assert reconciler().assert_consistent(
        {"success": True, "result": {}}, {"success": True, "result": []}
    ) == (False, "INVALID_ORDER_STATE")
    assert reconciler().assert_consistent(
        {"success": True, "result": []}, {"success": True, "result": None}
    ) == (False, "INVALID_POSITION_STATE")
    assert reconciler().assert_consistent(
        {"success": True, "result": [None]}, {"success": True, "result": []}
    ) == (False, "INVALID_ORDER_STATE")


def test_expected_order_must_be_confirmed():
    assert reconciler().assert_consistent(
        {"success": True, "result": []}, {"success": True, "result": []}, "client-1"
    ) == (False, "ORDER_NOT_CONFIRMED")


def test_valid_empty_state_without_expected_order_is_consistent():
    assert reconciler().assert_consistent(
        {"success": True, "result": []}, {"success": True, "result": []}
    ) == (True, "RECONCILED")


def test_invalid_client_order_id_fails_closed():
    assert reconciler().assert_consistent(
        {"success": True, "result": [{"client_order_id": 123}]},
        {"success": True, "result": []},
    ) == (False, "INVALID_CLIENT_ORDER_ID")
