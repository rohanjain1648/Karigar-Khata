"""Minimal signed tokens. A karigar's token is bound to his id, and every /api/me route reads
only that id, so he sees his full account and nobody else's (the brief's access boundary)."""
import base64
import hashlib
import hmac
import json
import time

from fastapi import Header, HTTPException

from . import config

TTL = 7 * 24 * 3600


def issue(role: str, karigar_id: int | None = None) -> str:
    body = base64.urlsafe_b64encode(json.dumps(
        {"role": role, "kid": karigar_id, "exp": int(time.time()) + TTL}).encode()).decode()
    sig = hmac.new(config.SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def decode(token: str) -> dict:
    try:
        body, sig = token.split(".", 1)
        good = hmac.new(config.SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            raise ValueError
        data = json.loads(base64.urlsafe_b64decode(body))
        if data["exp"] < time.time():
            raise ValueError
        return data
    except Exception:
        raise HTTPException(401, "invalid or expired session")


def _bearer(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "login required")
    return decode(authorization[7:])


def jeweller(authorization: str | None = Header(None)) -> dict:
    s = _bearer(authorization)
    if s["role"] != "jeweller":
        raise HTTPException(403, "jeweller only")
    return s


def karigar_or_jeweller(authorization: str | None = Header(None)) -> dict:
    return _bearer(authorization)


def karigar(authorization: str | None = Header(None)) -> dict:
    s = _bearer(authorization)
    if s["role"] != "karigar" or not s.get("kid"):
        raise HTTPException(403, "karigar only")
    return s
