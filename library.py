"""
Favorites & playlists API for MusicFinder (additive module; existing routes are untouched).

Identity: the existing site signs in with Google Identity Services, so the browser sends the
Google ID token as `Authorization: Bearer <id_token>`. The server verifies it with Google
(audience must equal GOOGLE_CLIENT_ID) and uses the verified `sub` as the owner. The browser
never supplies a user id. Data lives in Supabase tables accessed ONLY from this server with
the service-role key (env, never sent to the browser); RLS is enabled with no policies, so the
public/anon key cannot read or write these tables.

Env: GOOGLE_CLIENT_ID, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

import requests
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/library", tags=["library"])

MAX_TRACKS = 500
MAX_FAVORITES = 5000
_token_cache: dict = {}


def err(status: int, code: str):
    """Safe, machine-readable error: the frontend maps `code` to a localized message."""
    return HTTPException(status_code=status, detail={"code": code})


# ---------- identity ----------
def current_user(authorization: Optional[str] = Header(default=None)) -> str:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise err(503, "cloud_not_configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise err(401, "auth_required")
    token = authorization[7:].strip()
    hit = _token_cache.get(token)
    if hit and hit[1] > time.time():
        return hit[0]
    try:
        r = requests.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": token}, timeout=10)
    except requests.RequestException:
        raise err(502, "auth_unavailable")
    if r.status_code != 200:
        raise err(401, "session_expired")
    info = r.json()
    if info.get("aud") != client_id or not info.get("sub") or int(info.get("exp", 0)) < time.time():
        raise err(401, "session_expired")
    _token_cache[token] = (info["sub"], min(float(info["exp"]), time.time() + 300))
    return info["sub"]


# ---------- storage (Supabase PostgREST, server side only) ----------
def _db(method: str, table: str, params: Optional[dict] = None, json: Any = None, prefer: str = "return=representation"):
    base, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not base or not key:
        raise err(503, "cloud_not_configured")
    try:
        r = requests.request(
            method, f"{base.rstrip('/')}/rest/v1/{table}", params=params, json=json, timeout=15,
            headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": prefer},
        )
    except requests.RequestException as e:
        print("Supabase request error:", e)
        raise err(502, "storage_unavailable")
    if r.status_code >= 400:
        print("Supabase error", r.status_code, r.text[:300])   # logged server-side only
        raise err(502, "storage_failed")
    return r.json() if r.text else []


# ---------- schemas ----------
class Song(BaseModel):
    id: str = Field(min_length=1, max_length=64)            # Spotify track id
    name: str = Field(max_length=300)
    artists: List[dict] = Field(default_factory=list, max_length=20)
    album: dict = Field(default_factory=dict)
    external_urls: dict = Field(default_factory=dict)
    preview_url: Optional[str] = None
    added_at: Optional[str] = None


class PlaylistIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=300)


class PlaylistPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    description: Optional[str] = Field(default=None, max_length=300)
    order: Optional[List[str]] = None                        # full list of song ids in the new order


class PlaylistFull(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=300)
    tracks: List[Song] = Field(default_factory=list, max_length=MAX_TRACKS)
    updated_at: Optional[str] = None


class MergeIn(BaseModel):
    favorites: List[Song] = Field(default_factory=list, max_length=MAX_FAVORITES)
    playlists: List[dict] = Field(default_factory=list, max_length=100)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise err(404, "not_found")


def _get_playlist(user: str, pid: str) -> dict:
    rows = _db("GET", "mf_playlists", {"id": f"eq.{_uuid(pid)}", "user_sub": f"eq.{user}", "select": "*"})
    if not rows:
        raise err(404, "not_found")
    return rows[0]


def _save_tracks(user: str, pid: str, tracks: list) -> dict:
    rows = _db("PATCH", "mf_playlists", {"id": f"eq.{pid}", "user_sub": f"eq.{user}"},
               {"tracks": tracks, "updated_at": _now()})
    return rows[0]


# ---------- favorites ----------
@router.get("/favorites")
def list_favorites(user: str = Depends(current_user)):
    rows = _db("GET", "mf_favorites", {"user_sub": f"eq.{user}", "select": "song,added_at", "order": "added_at.desc", "limit": MAX_FAVORITES})
    return {"favorites": [{**r["song"], "added_at": r["added_at"]} for r in rows]}


@router.post("/favorites", status_code=201)
def add_favorite(song: Song, user: str = Depends(current_user)):
    _db("POST", "mf_favorites", {"on_conflict": "user_sub,song_id"},
        {"user_sub": user, "song_id": song.id, "song": song.model_dump(exclude={"added_at"})},
        prefer="resolution=ignore-duplicates,return=minimal")   # duplicates are ignored, never error
    return {"ok": True}


@router.delete("/favorites/{song_id}")
def remove_favorite(song_id: str, user: str = Depends(current_user)):
    _db("DELETE", "mf_favorites", {"user_sub": f"eq.{user}", "song_id": f"eq.{song_id}"}, prefer="return=minimal")
    return {"ok": True}          # playlists are never touched


# ---------- playlists ----------
@router.get("/playlists")
def list_playlists(user: str = Depends(current_user)):
    return {"playlists": _db("GET", "mf_playlists", {"user_sub": f"eq.{user}", "select": "id,name,description,tracks,created_at,updated_at", "order": "created_at.asc"})}


@router.post("/playlists", status_code=201)
def create_playlist(body: PlaylistIn, user: str = Depends(current_user)):
    name = _clean(body.name)
    if not name:
        raise err(422, "name_required")
    return _db("POST", "mf_playlists", None, {"user_sub": user, "name": name, "description": _clean(body.description), "tracks": []})[0]


@router.put("/playlists/{pid}")
def upsert_playlist(pid: str, body: PlaylistFull, user: str = Depends(current_user)):
    """Idempotent save used by the frontend (client-generated uuid). Never touches another user's row."""
    pid = _uuid(pid)
    name = _clean(body.name)
    if not name:
        raise err(422, "name_required")
    seen, tracks = set(), []
    for t in body.tracks:                                    # drop duplicate songs, keep order
        if t.id not in seen:
            seen.add(t.id)
            tracks.append(t.model_dump())
    data = {"name": name, "description": _clean(body.description), "tracks": tracks, "updated_at": body.updated_at or _now()}
    rows = _db("GET", "mf_playlists", {"id": f"eq.{pid}", "select": "user_sub"})
    if rows and rows[0]["user_sub"] != user:
        raise err(409, "id_conflict")
    if rows:
        return _db("PATCH", "mf_playlists", {"id": f"eq.{pid}", "user_sub": f"eq.{user}"}, data)[0]
    return _db("POST", "mf_playlists", None, {"id": pid, "user_sub": user, **data})[0]


@router.patch("/playlists/{pid}")
def update_playlist(pid: str, body: PlaylistPatch, user: str = Depends(current_user)):
    pl = _get_playlist(user, pid)
    patch: dict = {"updated_at": _now()}
    if body.name is not None:
        if not _clean(body.name):
            raise err(422, "name_required")
        patch["name"] = _clean(body.name)
    if body.description is not None:
        patch["description"] = _clean(body.description)
    if body.order is not None:
        by_id = {t["id"]: t for t in pl["tracks"]}
        if sorted(body.order) != sorted(by_id):
            raise err(409, "order_conflict")                 # client list is stale
        patch["tracks"] = [by_id[i] for i in body.order]
    return _db("PATCH", "mf_playlists", {"id": f"eq.{pl['id']}", "user_sub": f"eq.{user}"}, patch)[0]


@router.delete("/playlists/{pid}")
def delete_playlist(pid: str, user: str = Depends(current_user)):
    pl = _get_playlist(user, pid)
    _db("DELETE", "mf_playlists", {"id": f"eq.{pl['id']}", "user_sub": f"eq.{user}"}, prefer="return=minimal")
    return {"ok": True}          # favorites are never touched


@router.post("/playlists/{pid}/tracks")
def add_track(pid: str, song: Song, user: str = Depends(current_user)):
    pl = _get_playlist(user, pid)
    if any(t["id"] == song.id for t in pl["tracks"]):
        raise err(409, "duplicate_track")
    if len(pl["tracks"]) >= MAX_TRACKS:
        raise err(422, "playlist_full")
    return _save_tracks(user, pl["id"], pl["tracks"] + [song.model_dump()])


@router.delete("/playlists/{pid}/tracks/{song_id}")
def remove_track(pid: str, song_id: str, user: str = Depends(current_user)):
    pl = _get_playlist(user, pid)
    return _save_tracks(user, pl["id"], [t for t in pl["tracks"] if t["id"] != song_id])


# ---------- explicit, additive merge of local data ----------
@router.post("/merge")
def merge_local(body: MergeIn, user: str = Depends(current_user)):
    """Only ADDS: existing cloud favorites/playlists are never overwritten or removed."""
    if body.favorites:
        _db("POST", "mf_favorites", {"on_conflict": "user_sub,song_id"},
            [{"user_sub": user, "song_id": s.id, "song": s.model_dump(exclude={"added_at"})} for s in body.favorites],
            prefer="resolution=ignore-duplicates,return=minimal")
    added = 0
    for p in body.playlists:
        name = _clean(str(p.get("name", "")))[:60]
        if not name:
            continue
        tracks = []
        for t in (p.get("tracks") or [])[:MAX_TRACKS]:
            try:
                tracks.append(Song(**t).model_dump())
            except Exception:
                continue
        _db("POST", "mf_playlists", None, {"user_sub": user, "name": name, "description": _clean(str(p.get("description", "")))[:300], "tracks": tracks})
        added += 1
    return {"ok": True, "playlists_added": added}
