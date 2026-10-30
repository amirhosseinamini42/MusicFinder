"""
MusicFinder uploads + administration (additive module; existing routes are untouched).

Identity   : Google ID token (same GIS sign-in as the site) -> verified with Google (aud == GOOGLE_CLIENT_ID,
             email_verified == true). The role is looked up in `mf_admins` on EVERY request (no role caching),
             so a revoked admin is denied on the very next call. An email in the table is never enough alone.
Uploads    : files go browser -> Supabase Storage directly through short-lived signed upload URLs issued here
             (Vercel functions cap request bodies at ~4.5 MB, so audio cannot pass through this API).
             /finalize re-reads the stored object server-side (size + magic bytes) before it becomes live.
Storage    : private buckets `mf-audio` / `mf-covers`; public playback only via short-lived signed URLs that
             /tracks/* issues for PUBLISHED tracks. Service-role key stays server side.
Env        : GOOGLE_CLIENT_ID, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   (all already used by library.py)
"""
import hashlib
import os
import re
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

import mf_policy as policy
from library import err          # same {"code": ...} error shape as the rest of the API

admin_router = APIRouter(prefix="/admin", tags=["admin"])
public_router = APIRouter(prefix="/tracks", tags=["tracks"])

AUDIO_BUCKET = os.getenv("MF_AUDIO_BUCKET", "mf-audio")
COVER_BUCKET = os.getenv("MF_COVER_BUCKET", "mf-covers")
PUBLIC_URL_TTL = 3600       # seconds a public signed URL lives
ADMIN_URL_TTL = 600

_ident_cache: Dict[str, tuple] = {}
_hits: Dict[str, deque] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# =====================================================================
# Identity + roles
# =====================================================================
def _verify_google(token: str) -> dict:
    """Verified identity from a Google ID token. Raises HTTPException on any failure (fail closed)."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise err(503, "cloud_not_configured")
    key = hashlib.sha256(token.encode()).hexdigest()
    hit = _ident_cache.get(key)
    if hit and hit["exp"] > time.time():
        return hit
    try:
        r = requests.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": token}, timeout=10)
    except requests.RequestException:
        raise err(502, "auth_unavailable")
    if r.status_code != 200:
        raise err(401, "session_expired")
    info = r.json()
    email = policy.normalize_email(info.get("email"))
    verified = str(info.get("email_verified", "")).lower() == "true"
    try:
        exp = float(info.get("exp", 0))
    except (TypeError, ValueError):
        exp = 0
    if (info.get("aud") != client_id or not info.get("sub") or exp < time.time()
            or info.get("iss") not in ("accounts.google.com", "https://accounts.google.com")):
        raise err(401, "session_expired")
    if not email or not verified:
        raise err(403, "email_not_verified")
    ident = {"sub": info["sub"], "email": email, "name": info.get("name") or email,
             "exp": min(exp, time.time() + 120)}      # identity cache only; roles are never cached
    if len(_ident_cache) > 500:
        _ident_cache.clear()
    _ident_cache[key] = ident
    return ident


def _bearer(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise err(401, "auth_required")
    token = authorization[7:].strip()
    if not token:
        raise err(401, "auth_required")
    return token


def current_admin(authorization: Optional[str] = Header(default=None)) -> dict:
    ident = _verify_google(_bearer(authorization))
    rows = _rest("GET", "mf_admins", {"email": f"eq.{ident['email']}", "revoked_at": "is.null", "select": "email,role"})
    if not rows or rows[0]["role"] not in ("owner", "admin"):
        raise err(403, "not_authorized")
    return {"email": ident["email"], "name": ident["name"], "role": rows[0]["role"]}


def require_owner(admin: dict = Depends(current_admin)) -> dict:
    if admin["role"] != "owner":
        raise err(403, "forbidden")
    return admin


# =====================================================================
# Supabase helpers (server side only)
# =====================================================================
def _cfg():
    base, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not base or not key:
        raise err(503, "cloud_not_configured")
    return base.rstrip("/"), key


def _rest(method: str, table: str, params: Optional[dict] = None, json: Any = None,
          prefer: str = "return=representation", conflict_ok: bool = False):
    base, key = _cfg()
    try:
        r = requests.request(method, f"{base}/rest/v1/{table}", params=params, json=json, timeout=15,
                             headers={"apikey": key, "Authorization": f"Bearer {key}",
                                      "Content-Type": "application/json", "Prefer": prefer})
    except requests.RequestException as e:
        print("Supabase request error:", type(e).__name__)
        raise err(502, "storage_unavailable")
    if r.status_code == 409 and conflict_ok:
        return None
    if r.status_code >= 400:
        print("Supabase error", r.status_code, r.text[:200])      # no tokens/URLs are ever logged
        raise err(502, "storage_failed")
    return r.json() if r.text else []


def _storage(method: str, path: str, json: Any = None, headers: Optional[dict] = None, stream: bool = False):
    base, key = _cfg()
    try:
        return requests.request(method, f"{base}/storage/v1/{path}", json=json, timeout=20, stream=stream,
                                headers={"apikey": key, "Authorization": f"Bearer {key}", **(headers or {})})
    except requests.RequestException as e:
        print("Supabase storage error:", type(e).__name__)
        raise err(502, "storage_unavailable")


def _qpath(bucket: str, key: str) -> str:
    return f"{quote(bucket, safe='')}/{quote(key, safe='/')}"


def sign_upload(bucket: str, key: str) -> str:
    r = _storage("POST", f"object/upload/sign/{_qpath(bucket, key)}")
    if r.status_code >= 400:
        print("sign_upload failed", r.status_code)
        raise err(502, "storage_failed")
    base, _ = _cfg()
    return f"{base}/storage/v1{r.json()['url']}"


def sign_download(bucket: str, keys: List[str], ttl: int, download_name: Optional[str] = None) -> Dict[str, str]:
    """Batch-sign existing objects. Returns {key: full_url}; keys that failed are omitted."""
    keys = [k for k in keys if k]
    if not keys:
        return {}
    r = _storage("POST", f"object/sign/{quote(bucket, safe='')}", json={"expiresIn": ttl, "paths": keys})
    if r.status_code >= 400:
        print("sign_download failed", r.status_code)
        raise err(502, "storage_failed")
    base, _ = _cfg()
    out = {}
    for item in r.json():
        if item.get("signedURL") and not item.get("error"):
            url = f"{base}/storage/v1{item['signedURL']}"
            if download_name:
                url += "&download=" + quote(download_name, safe="")
            out[item["path"]] = url
    return out


def read_head(bucket: str, key: str, n: int = 64):
    """Read the first bytes + total size of a stored object. Returns None if it does not exist."""
    r = _storage("GET", f"object/authenticated/{_qpath(bucket, key)}", headers={"Range": f"bytes=0-{n - 1}"}, stream=True)
    try:
        if r.status_code in (400, 404):
            return None
        if r.status_code not in (200, 206):
            raise err(502, "storage_failed")
        head = b""
        for chunk in r.iter_content(chunk_size=n):
            head += chunk
            if len(head) >= n:
                break
        head = head[:n]
        m = re.match(r"bytes \d+-\d+/(\d+)", r.headers.get("Content-Range", ""))
        total = int(m.group(1)) if m else int(r.headers.get("Content-Length") or 0)
        return head, total
    finally:
        r.close()


def remove_objects(bucket: str, keys: List[str]) -> None:
    keys = [k for k in keys if k]
    if not keys:
        return
    r = _storage("DELETE", quote(bucket, safe=""), json={"prefixes": keys})
    if r.status_code >= 400:
        print("remove_objects failed", r.status_code)
        raise err(502, "storage_failed")


def _try_remove(bucket: str, keys: List[str]) -> None:
    try:
        remove_objects(bucket, keys)
    except HTTPException:
        pass            # best effort cleanup of orphaned/old objects


# =====================================================================
# Schemas
# =====================================================================
class FileDecl(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=1)
    content_type: Optional[str] = Field(default=None, max_length=100)


class TrackCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    artist: str = Field(min_length=1, max_length=300)
    album: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=4000)
    download_enabled: bool = False
    rights_confirmed: bool = False
    client_request_id: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")
    audio: FileDecl
    cover: Optional[FileDecl] = None


class UploadUrlsIn(BaseModel):
    audio: Optional[FileDecl] = None
    cover: Optional[FileDecl] = None


class FinalizeIn(BaseModel):
    audio: bool = True
    cover: bool = True


class TrackPatch(BaseModel):
    title: Optional[str] = Field(default=None, max_length=300)
    artist: Optional[str] = Field(default=None, max_length=300)
    album: Optional[str] = Field(default=None, max_length=300)
    description: Optional[str] = Field(default=None, max_length=4000)
    download_enabled: Optional[bool] = None
    rights_confirmed: Optional[bool] = None


class StatusIn(BaseModel):
    status: str


class AdminIn(BaseModel):
    email: str = Field(max_length=254)


def _meta(title, artist, album, description) -> dict:
    out = {}
    if title is not None:
        out["title"] = policy.clean_line(title, 200)
        if not out["title"]:
            raise err(422, "title_required")
    if artist is not None:
        out["artist"] = policy.clean_line(artist, 200)
        if not out["artist"]:
            raise err(422, "artist_required")
    if album is not None:
        out["album"] = policy.clean_line(album, 200)
    if description is not None:
        out["description"] = policy.clean_block(description, 2000)
    return out


def _policy_err(e: policy.PolicyError):
    return err(422, e.code)


def _uuid(value: str) -> str:
    import uuid
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise err(404, "not_found")


PUBLIC_FIELDS = ("id,title,artist,album,description,status,download_enabled,rights_confirmed,audio_size,"
                 "audio_path,cover_path,audio_path_new,cover_path_new,created_by,updated_by,created_at,updated_at,published_at")


def _admin_view(row: dict) -> dict:
    """Admin-facing track: never exposes storage keys."""
    return {
        "id": row["id"], "title": row["title"], "artist": row["artist"], "album": row.get("album", ""),
        "description": row.get("description", ""), "status": row["status"],
        "download_enabled": row["download_enabled"], "rights_confirmed": row["rights_confirmed"],
        "has_audio": bool(row.get("audio_path")), "has_cover": bool(row.get("cover_path")),
        "audio_pending": bool(row.get("audio_path_new")), "cover_pending": bool(row.get("cover_path_new")),
        "audio_size": row.get("audio_size"), "created_by": row.get("created_by"), "updated_by": row.get("updated_by"),
        "created_at": row.get("created_at"), "updated_at": row.get("updated_at"), "published_at": row.get("published_at"),
    }


def _get_track(tid: str) -> dict:
    rows = _rest("GET", "mf_tracks", {"id": f"eq.{_uuid(tid)}", "select": "*"})
    if not rows:
        raise err(404, "not_found")
    return rows[0]


def _issue(track: dict, audio: Optional[FileDecl], cover: Optional[FileDecl]) -> dict:
    """Generate keys, persist them as *_new on the row, sign upload URLs. Validation happens before any write."""
    plan = {}
    try:
        if audio:
            plan["audio"] = (policy.check_declared_file("audio", audio.filename, audio.size, audio.content_type), AUDIO_BUCKET)
        if cover:
            plan["cover"] = (policy.check_declared_file("cover", cover.filename, cover.size, cover.content_type), COVER_BUCKET)
    except policy.PolicyError as e:
        raise _policy_err(e)
    patch, old_new, uploads = {}, {"audio": track.get("audio_path_new"), "cover": track.get("cover_path_new")}, {}
    for kind, (ext, bucket) in plan.items():
        key = policy.make_key(kind, track["id"], ext)
        uploads[kind] = {"url": sign_upload(bucket, key), "content_type": policy.canonical_mime(kind, ext), "ext": ext}
        patch[f"{kind}_path_new"], patch[f"{kind}_ext_new"] = key, ext
    if patch:
        _rest("PATCH", "mf_tracks", {"id": f"eq.{track['id']}"}, {**patch, "updated_at": _now()})
        # stale, never-finalized uploads from earlier attempts are removed
        _try_remove(AUDIO_BUCKET, [old_new["audio"]] if "audio" in plan else [])
        _try_remove(COVER_BUCKET, [old_new["cover"]] if "cover" in plan else [])
    return uploads


# =====================================================================
# Admin: identity + dashboard
# =====================================================================
@admin_router.get("/me")
def me(admin: dict = Depends(current_admin)):
    return {"email": admin["email"], "name": admin["name"], "role": admin["role"]}


@admin_router.get("/stats")
def stats(admin: dict = Depends(current_admin)):
    rows = _rest("GET", "mf_tracks", {"select": "status,audio_path", "limit": 10000})
    counts = {s: 0 for s in policy.STATUSES}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"total": len(rows), "by_status": counts, "awaiting_audio": sum(1 for r in rows if not r.get("audio_path"))}


# =====================================================================
# Admin: tracks
# =====================================================================
@admin_router.get("/tracks")
def list_tracks(status: Optional[str] = None, q: Optional[str] = None, limit: int = 50, offset: int = 0,
                admin: dict = Depends(current_admin)):
    params = {"select": PUBLIC_FIELDS, "order": "created_at.desc", "limit": max(1, min(limit, 100)), "offset": max(0, offset)}
    if status:
        if status not in policy.STATUSES:
            raise err(422, "bad_status")
        params["status"] = f"eq.{status}"
    term = policy.safe_search_term(q)
    if term:
        params["or"] = f"(title.ilike.*{term}*,artist.ilike.*{term}*,album.ilike.*{term}*)"
    return {"tracks": [_admin_view(r) for r in _rest("GET", "mf_tracks", params)]}


@admin_router.post("/tracks", status_code=201)
def create_track(body: TrackCreate, response: Response, admin: dict = Depends(current_admin)):
    meta = _meta(body.title, body.artist, body.album, body.description)
    # validate declared files BEFORE touching the database
    try:
        policy.check_declared_file("audio", body.audio.filename, body.audio.size, body.audio.content_type)
        if body.cover:
            policy.check_declared_file("cover", body.cover.filename, body.cover.size, body.cover.content_type)
    except policy.PolicyError as e:
        raise _policy_err(e)

    row = {**meta, "created_by": admin["email"], "updated_by": admin["email"], "status": "draft",
           "download_enabled": body.download_enabled, "rights_confirmed": body.rights_confirmed,
           "client_request_id": body.client_request_id}
    created = _rest("POST", "mf_tracks", None, row, conflict_ok=True)
    if created is None:                                   # duplicate submission (same client_request_id)
        rows = _rest("GET", "mf_tracks", {"created_by": f"eq.{admin['email']}",
                                          "client_request_id": f"eq.{body.client_request_id}", "select": "*"})
        if not rows:
            raise err(409, "duplicate_request")
        track, response.status_code = rows[0], 200
    else:
        track = created[0]
    try:
        uploads = _issue(track, body.audio, body.cover)
    except HTTPException:
        if created is not None:                           # compensate: no half-created record without upload URLs
            try:
                _rest("DELETE", "mf_tracks", {"id": f"eq.{track['id']}"}, prefer="return=minimal")
            except HTTPException:
                pass
        raise
    return {"track": _admin_view(track), "uploads": uploads}


@admin_router.post("/tracks/{tid}/upload-urls")
def reissue_upload_urls(tid: str, body: UploadUrlsIn, admin: dict = Depends(current_admin)):
    """Retry a failed upload, or replace the audio/cover of an existing track (live file stays until finalize)."""
    if not body.audio and not body.cover:
        raise err(422, "nothing_to_upload")
    track = _get_track(tid)
    if track["status"] == "published" and body.audio:
        raise err(409, "unpublish_first")                 # never swap audio under a live public track
    return {"uploads": _issue(track, body.audio, body.cover)}


@admin_router.post("/tracks/{tid}/finalize")
def finalize(tid: str, body: FinalizeIn, admin: dict = Depends(current_admin)):
    track = _get_track(tid)
    patch, old, errors = {}, {"audio": [], "cover": []}, {}
    for kind, bucket, want in (("audio", AUDIO_BUCKET, body.audio), ("cover", COVER_BUCKET, body.cover)):
        new_key, ext = track.get(f"{kind}_path_new"), track.get(f"{kind}_ext_new")
        if not want or not new_key:
            continue
        got = read_head(bucket, new_key)
        if got is None:
            errors[kind] = "upload_missing"
            continue
        head, total = got
        try:
            policy.validate_signature(kind, ext, head, total)
        except policy.PolicyError as e:
            _try_remove(bucket, [new_key])                # reject + delete the bad object
            patch.update({f"{kind}_path_new": None, f"{kind}_ext_new": None})
            errors[kind] = e.code
            continue
        if track.get(f"{kind}_path"):
            old[kind].append(track[f"{kind}_path"])
        patch.update({f"{kind}_path": new_key, f"{kind}_ext": ext, f"{kind}_path_new": None, f"{kind}_ext_new": None})
        if kind == "audio":
            patch["audio_size"] = total
    if patch:
        patch.update({"updated_at": _now(), "updated_by": admin["email"]})
        track = _rest("PATCH", "mf_tracks", {"id": f"eq.{track['id']}"}, patch)[0]
        _try_remove(AUDIO_BUCKET, old["audio"])
        _try_remove(COVER_BUCKET, old["cover"])
    if errors:
        raise HTTPException(status_code=422, detail={"code": "finalize_failed", "files": errors, "track": _admin_view(track)})
    return {"track": _admin_view(track)}


@admin_router.patch("/tracks/{tid}")
def update_track(tid: str, body: TrackPatch, admin: dict = Depends(current_admin)):
    track = _get_track(tid)
    patch = _meta(body.title, body.artist, body.album, body.description)
    if body.download_enabled is not None:
        patch["download_enabled"] = body.download_enabled
    if body.rights_confirmed is not None:
        patch["rights_confirmed"] = body.rights_confirmed
        if body.rights_confirmed is False and track["status"] == "published":
            raise err(409, "unpublish_first")
    patch.update({"updated_at": _now(), "updated_by": admin["email"]})
    return {"track": _admin_view(_rest("PATCH", "mf_tracks", {"id": f"eq.{track['id']}"}, patch)[0])}


@admin_router.post("/tracks/{tid}/status")
def set_status(tid: str, body: StatusIn, admin: dict = Depends(current_admin)):
    track = _get_track(tid)
    new = body.status
    if new not in policy.STATUSES:
        raise err(422, "bad_status")
    if not policy.can_transition(track["status"], new):
        raise err(409, "bad_transition")
    patch = {"status": new, "updated_at": _now(), "updated_by": admin["email"]}
    if new == "published":
        if not track.get("audio_path"):
            raise err(422, "audio_missing")
        if not track.get("rights_confirmed"):
            raise err(422, "rights_not_confirmed")
        patch["published_at"] = _now()
    # compare-and-set on the current status so concurrent changes cannot interleave
    rows = _rest("PATCH", "mf_tracks", {"id": f"eq.{track['id']}", "status": f"eq.{track['status']}"}, patch)
    if not rows:
        raise err(409, "bad_transition")
    return {"track": _admin_view(rows[0])}


@admin_router.get("/tracks/{tid}/preview")
def preview(tid: str, admin: dict = Depends(current_admin)):
    track = _get_track(tid)
    audio = sign_download(AUDIO_BUCKET, [track.get("audio_path")], ADMIN_URL_TTL).get(track.get("audio_path") or "")
    cover = sign_download(COVER_BUCKET, [track.get("cover_path")], ADMIN_URL_TTL).get(track.get("cover_path") or "")
    return {"audio_url": audio, "cover_url": cover, "expires_in": ADMIN_URL_TTL}


@admin_router.delete("/tracks/{tid}")
def delete_track(tid: str, admin: dict = Depends(current_admin)):
    track = _get_track(tid)
    if track["status"] == "published":                    # public availability ends first
        _rest("PATCH", "mf_tracks", {"id": f"eq.{track['id']}"}, {"status": "unpublished", "updated_at": _now()})
    remove_objects(AUDIO_BUCKET, [track.get("audio_path"), track.get("audio_path_new")])
    remove_objects(COVER_BUCKET, [track.get("cover_path"), track.get("cover_path_new")])
    _rest("DELETE", "mf_tracks", {"id": f"eq.{track['id']}"}, prefer="return=minimal")
    return {"ok": True}


# =====================================================================
# Admin management (owner only)
# =====================================================================
@admin_router.get("/admins")
def list_admins(owner: dict = Depends(require_owner)):
    rows = _rest("GET", "mf_admins", {"select": "email,role,added_by,created_at,revoked_at", "order": "created_at.asc"})
    return {"admins": rows}


@admin_router.post("/admins", status_code=201)
def add_admin(body: AdminIn, owner: dict = Depends(require_owner)):
    email = policy.normalize_email(body.email)
    if not email:
        raise err(422, "bad_email")
    existing = _rest("GET", "mf_admins", {"email": f"eq.{email}", "select": "email,role,revoked_at"})
    target_role = existing[0]["role"] if existing else None
    problem = policy.check_admin_change(owner["role"], "add", target_role)
    if problem:
        raise err(403, problem)
    if existing:
        if existing[0]["revoked_at"] is None:
            raise err(409, "already_admin")
        _rest("PATCH", "mf_admins", {"email": f"eq.{email}", "role": "eq.admin"},
              {"revoked_at": None, "added_by": owner["email"]})
    else:
        _rest("POST", "mf_admins", None, {"email": email, "role": "admin", "added_by": owner["email"]})
    return {"ok": True, "email": email, "role": "admin"}


@admin_router.delete("/admins/{email}")
def revoke_admin(email: str, owner: dict = Depends(require_owner)):
    email = policy.normalize_email(email)
    if not email:
        raise err(422, "bad_email")
    existing = _rest("GET", "mf_admins", {"email": f"eq.{email}", "revoked_at": "is.null", "select": "email,role"})
    if not existing:
        raise err(404, "not_found")
    problem = policy.check_admin_change(owner["role"], "revoke", existing[0]["role"])
    if problem:
        raise err(403, problem)
    _rest("PATCH", "mf_admins", {"email": f"eq.{email}", "role": "eq.admin"}, {"revoked_at": _now()})
    return {"ok": True}


# =====================================================================
# Public: published tracks only
# =====================================================================
def _rate_ok(ip: str, limit: int = 60) -> bool:
    now = time.time()
    if len(_hits) > 2000:
        _hits.clear()
    q = _hits.setdefault(ip, deque())
    while q and q[0] < now - 60:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def _ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return fwd or (request.client.host if request.client else "unknown")


def _public_get(tid: str) -> dict:
    rows = _rest("GET", "mf_tracks", {"id": f"eq.{_uuid(tid)}", "status": "eq.published",
                                      "audio_path": "not.is.null", "select": "*"})
    if not rows:
        raise err(404, "not_found")                      # drafts / unpublished / deleted look identical: not found
    return rows[0]


@public_router.get("/search")
def public_search(request: Request, response: Response, q: str = "", limit: int = 20):
    response.headers["Cache-Control"] = "no-store"        # unpublish must take effect immediately
    if not _rate_ok(_ip(request)):
        raise err(429, "rate_limited")
    params = {"status": "eq.published", "audio_path": "not.is.null", "order": "published_at.desc",
              "limit": max(1, min(limit, 30)), "select": "id,title,artist,album,cover_path,download_enabled"}
    term = policy.safe_search_term(q)
    if term:
        params["or"] = f"(title.ilike.*{term}*,artist.ilike.*{term}*,album.ilike.*{term}*)"
    rows = _rest("GET", "mf_tracks", params)
    covers = sign_download(COVER_BUCKET, [r.get("cover_path") for r in rows], PUBLIC_URL_TTL)
    tracks = []
    for r in rows:
        cover = covers.get(r.get("cover_path") or "")
        tracks.append({
            "id": f"mf:{r['id']}", "name": r["title"], "artists": [{"id": "", "name": r["artist"]}],
            "album": {"name": r.get("album") or "", "images": [{"url": cover}] if cover else []},
            "external_urls": {}, "preview_url": None, "mf_original": True,
            "download_enabled": bool(r["download_enabled"]),
        })
    return {"tracks": tracks}


@public_router.get("/{tid}/play")
def public_play(tid: str, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if not _rate_ok(_ip(request)):
        raise err(429, "rate_limited")
    t = _public_get(tid)
    url = sign_download(AUDIO_BUCKET, [t["audio_path"]], PUBLIC_URL_TTL).get(t["audio_path"])
    if not url:
        raise err(502, "storage_failed")
    return {"url": url, "expires_in": PUBLIC_URL_TTL}


@public_router.get("/{tid}/download")
def public_download(tid: str, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if not _rate_ok(_ip(request), limit=20):
        raise err(429, "rate_limited")
    t = _public_get(tid)
    if not t.get("download_enabled"):
        raise err(403, "download_disabled")
    name = policy.clean_line(f"{t['artist']} - {t['title']}", 120) + "." + (t.get("audio_ext") or "mp3")
    url = sign_download(AUDIO_BUCKET, [t["audio_path"]], 300, download_name=name).get(t["audio_path"])
    if not url:
        raise err(502, "storage_failed")
    return {"url": url, "expires_in": 300}
