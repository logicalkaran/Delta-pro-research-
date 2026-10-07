"""Delta Exchange v2 request signing."""
from __future__ import annotations
import hashlib, hmac

def sign(secret: str, method: str, timestamp: str, request_path: str,
         query_string: str = "", body: str = "") -> str:
    if not secret:
        raise ValueError("API secret is required")
    query_part = ("?" + query_string) if query_string else ""
    prehash = method.upper() + timestamp + request_path + query_part + body
    return hmac.new(secret.encode(), prehash.encode(), hashlib.sha256).hexdigest()
