"""
Shared Google ID-token verification (used by admin.py; library.py keeps its own inline copy, untouched).

Validation (all must pass): Google's tokeninfo accepts the token (signature + expiry), aud == GOOGLE_CLIENT_ID,
iss is Google, exp is in the future, `sub` and `email` are present, email_verified is true.
Only the verified identity is cached (<= 5 minutes, never past token expiry). Roles are NEVER cached here.

Env: GOOGLE_CLIENT_ID
"""
import hashlib
import os
import time
from typing import Optional

import requests
from fastapi import HTTPException

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
ISSUERS = ("accounts.google.com", "https://accounts.google.com")
MAX_TOKEN_CHARS = 4096
CACHE_SECONDS = 300
_cache: dict = {}


def _err(status: int, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code})


def bearer_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _err(401, "auth_required")
    token = authorization[7:].strip()
    if not token:
        raise _err(401, "auth_required")
    if len(token) > MAX_TOKEN_CHARS:
        raise _err(401, "session_expired")
    return token


def verify_google(token: str) -> dict:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        raise _err(503, "cloud_not_configured")

    key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    hit = _cache.get(key)
    if hit and hit[1] > time.time():
        return dict(hit[0])

    try:
        r = requests.get(TOKENINFO_URL, params={"id_token": token}, timeout=10, allow_redirects=False)
    except requests.RequestException:
        raise _err(502, "auth_unavailable")
    if r.status_code != 200:
        raise _err(401, "session_expired")
    try:
        info = r.json()
    except ValueError:
        raise _err(502, "auth_unavailable")
    if not isinstance(info, dict):
        raise _err(401, "session_expired")

    try:
        exp = int(info.get("exp", 0))
    except (TypeError, ValueError):
        raise _err(401, "session_expired")
    if info.get("aud") != client_id or info.get("iss") not in ISSUERS or exp <= time.time():
        raise _err(401, "session_expired")

    sub = info.get("sub")
    email = str(info.get("email") or "").strip().lower()
    if not isinstance(sub, str) or not sub or not email:
        raise _err(401, "session_expired")
    if str(info.get("email_verified")).strip().lower() != "true":
        raise _err(401, "email_not_verified")

    ident = {"sub": sub, "email": email, "name": str(info.get("name") or email)[:200]}
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (ident, min(float(exp), time.time() + CACHE_SECONDS))
    return dict(ident)
