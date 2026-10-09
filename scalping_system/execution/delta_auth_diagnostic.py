#!/usr/bin/env python3
"""Run a single read-only Delta authentication diagnostic without printing secrets/account data."""
from __future__ import annotations
import json
import os
from pathlib import Path
from requests import HTTPError, RequestException
from execution.delta_client_private import DeltaAuthClient


def load_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key and key.replace("_", "").isalnum():
            os.environ.setdefault(key, value)


def main() -> int:
    load_env()
    if not os.getenv("DELTA_API_KEY") or not os.getenv("DELTA_API_SECRET"):
        print("AUTH_DIAGNOSTIC=FAILED")
        print("REASON=credentials_missing_from_environment_and_repo_env")
        return 2
    base = os.getenv("DELTA_API_BASE", "")
    if base == DeltaAuthClient.PROD:
        env = "prod"
    elif base == DeltaAuthClient.DEMO:
        env = "demo"
    else:
        env = os.getenv("DELTA_ENV", "demo").lower()
    print("CONFIGURED_ENV=" + env)
    try:
        client = DeltaAuthClient(environment=env, timeout=8)
        # Use the documented read-only endpoint with no query parameters.
        # GET /v2/positions requires product_id or underlying_asset_symbol;
        # product_symbol is not a valid query parameter for that endpoint.
        client.request("GET", "/v2/positions/margined")
        print("AUTHENTICATION=SUCCESS")
        print("READ_ONLY_ENDPOINT=GET /v2/positions/margined")
        print("ACCOUNT_DETAILS=withheld")
        return 0
    except HTTPError as exc:
        response = exc.response
        print("AUTHENTICATION=HTTP_ERROR")
        print("HTTP_STATUS=" + str(response.status_code if response is not None else "unknown"))
        if response is not None:
            try:
                payload = response.json()
                err = payload.get("error", {}) if isinstance(payload, dict) else {}
                code = err.get("code", payload.get("code", "unknown")) if isinstance(err, dict) else "unknown"
                message = err.get("message", payload.get("message", "")) if isinstance(err, dict) else ""
                print("API_ERROR_CODE=" + str(code)[:100])
                if message:
                    print("API_ERROR_MESSAGE=" + str(message)[:160])
                if str(code).lower() in {"ip_not_whitelisted_for_api_key", "ip_not_whitelisted"}:
                    print("NEXT_STEP=Add this device/network's current public IPv4 address to this API key's IP whitelist in Delta API Management.")
                elif str(code).lower() in {"invalid_api_key", "invalid_api_key_error"}:
                    print("NEXT_STEP=Verify the key is active and belongs to the configured environment; rotate it if it was exposed.")
                elif "signature" in str(code).lower():
                    print("NEXT_STEP=Check device clock synchronization and regenerate/replace the API key-secret pair if needed.")
            except (ValueError, json.JSONDecodeError):
                print("API_ERROR_DETAILS=non_json_response")
        return 1
    except RequestException as exc:
        print("AUTHENTICATION=NETWORK_ERROR")
        print("ERROR_TYPE=" + type(exc).__name__)
        return 2
    except Exception as exc:
        print("AUTHENTICATION=FAILED")
        print("ERROR_TYPE=" + type(exc).__name__)
        print("ERROR=" + str(exc)[:160])
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
