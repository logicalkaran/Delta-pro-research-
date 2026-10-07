import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from execution.delta_signer import sign
from execution.delta_executor import DeltaExecutor, LiveExecutionBlocked
from execution.delta_private_ws import auth_message

def main():
    s = sign("secret", "GET", "123", "/live")
    assert len(s) == 64
    os.environ["DELTA_API_KEY"] = "demo-key"
    os.environ["DELTA_API_SECRET"] = "demo-secret"
    msg = auth_message("demo")
    assert msg["type"] == "key-auth"
    assert msg["payload"]["timestamp"] == 123 or isinstance(msg["payload"]["timestamp"], int)

    ex = DeltaExecutor()
    result = ex.submit_market(
        product_id=27, product_symbol="BTCUSD", side="buy",
        size=1, client_order_id="TEST-DRY-001", dry_run=True
    )
    assert result["dry_run"] is True

    os.environ["BTC_LIVE_EXECUTION"] = "true"
    try:
        ex.submit_market(
            product_id=27, product_symbol="BTCUSD", side="buy",
            size=1, client_order_id="TEST-BLOCKED", dry_run=False
        )
    except LiveExecutionBlocked:
        pass
    else:
        raise AssertionError("live execution was not blocked")
    print("Delta execution safety tests: PASS")

if __name__ == "__main__":
    main()
