"""Shared MusicFinder identity verification for Supabase Auth and staged Google compatibility.

The browser never supplies a user id or role. Supabase validates access tokens through
/auth/v1/user; verified email and identity metadata are read only from that response.
"""
import os
import re
import uuid
from urllib.parse import urlsplit

import requests
from fastapi import HTTPException

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _error(status: int, code: str):
    return HTTPException(status_code=status, detail={"code": code})


def _config():
    base = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()
    if not base or not key:
        return None
    try:
        parsed = urlsplit(base)
        valid = (parsed.scheme == "https" and bool(parsed.hostname) and
                 not parsed.username and not parsed.password and
                 parsed.path in ("", "/") and not parsed.query and
                 not parsed.fragment and parsed.port in (None, 443))
    except ValueError:
        valid = False
    if not valid:
        raise _error(503, "cloud_configuration_invalid")
    return base, key


def verify_supabase_access_token(token: str) -> dict:
    if not isinstance(token, str) or not token or len(token) > 8192:
        raise _error(401, "auth_required")
    cfg = _config()
    if not cfg:
        raise _error(503, "cloud_not_configured")
    base, key = cfg
    try:
        response = requests.get(
            f"{base}/auth/v1/user",
            headers={"apikey": key, "Authorization": f"Bearer {token}"},
            timeout=10,
            allow_redirects=False,
        )
    except requests.RequestException:
        raise _error(502, "auth_unavailable")
    if response.status_code in (400, 401, 403):
        raise _error(401, "session_expired")
    if response.status_code >= 500:
        raise _error(502, "auth_unavailable")
    if response.status_code != 200:
        raise _error(401, "session_expired")
    try:
        user = response.json()
    except ValueError:
        raise _error(502, "auth_unavailable")
    if not isinstance(user, dict):
        raise _error(401, "session_expired")
    try:
        user_id = str(uuid.UUID(str(user.get("id", ""))))
    except (ValueError, TypeError, AttributeError):
        raise _error(401, "session_expired")
    email = str(user.get("email") or "").strip().lower()
    if not email or len(email) > 254 or not _EMAIL.fullmatch(email):
        raise _error(401, "session_expired")
    if not (user.get("email_confirmed_at") or user.get("confirmed_at")):
        raise _error(403, "email_not_verified")

    metadata = user.get("user_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    app_metadata = user.get("app_metadata")
    app_metadata = app_metadata if isinstance(app_metadata, dict) else {}
    primary_provider = app_metadata.get("provider")
    primary_provider = primary_provider if primary_provider in ("email", "google") else None
    identities = user.get("identities")
    identities = identities if isinstance(identities, list) else []
    google_sub = None
    for identity in identities:
        if not isinstance(identity, dict) or identity.get("provider") != "google":
            continue
        data = identity.get("identity_data")
        data = data if isinstance(data, dict) else {}
        candidate = data.get("sub") or identity.get("id")
        if isinstance(candidate, str) and 1 <= len(candidate) <= 255:
            google_sub = candidate
            break

    name = metadata.get("full_name") or metadata.get("name") or metadata.get("display_name") or email.split("@", 1)[0]
    picture = metadata.get("avatar_url") or metadata.get("picture")
    if not isinstance(name, str):
        name = email.split("@", 1)[0]
    if not isinstance(picture, str) or len(picture) > 2048 or not picture.startswith("https://"):
        picture = None
    return {
        "id": user_id,
        "sub": user_id,
        "legacy_google_sub": google_sub,
        "primary_provider": primary_provider,
        "email": email,
        "name": name.strip()[:100] or email.split("@", 1)[0],
        "picture": picture,
        "provider": "supabase",
    }


def verify_access_token(token: str) -> dict:
    """Verify the new Supabase session, while preserving old verified Google tokens during rollout."""
    try:
        return verify_supabase_access_token(token)
    except HTTPException as exc:
        if exc.status_code == 503 and exc.detail == {"code": "cloud_not_configured"}:
            pass
        elif exc.status_code == 401:
            pass
        else:
            raise

    try:
        import auth_google
        ident = auth_google.verify_google(token)
    except HTTPException:
        raise
    return {
        "id": ident["sub"],
        "sub": ident["sub"],
        "legacy_google_sub": ident["sub"],
        "email": ident["email"],
        "name": ident["name"],
        "picture": None,
        "provider": "google_legacy",
    }
