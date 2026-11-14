"""Strict allowlisted, read-only tools for MusicFinder admin AI."""

from uuid import UUID
from typing import Any

import mf_policy as policy
from admin import _rest
from fastapi import HTTPException


ROW_CAP = 10000
AGENT_TRACK_SELECT = "id,title,artist,album,status,audio_path,cover_path,created_at,updated_at,published_at"

SAFE_TRACK_FIELDS = (
    "id",
    "title",
    "artist",
    "album",
    "status",
    "has_audio",
    "has_cover",
    "created_at",
    "updated_at",
    "published_at",
)


def _safe_track(row: dict) -> dict:
    """Return only explicitly approved metadata. Never expose storage paths."""
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "artist": row.get("artist"),
        "album": row.get("album") or "",
        "status": row.get("status"),
        "has_audio": bool(row.get("audio_path")),
        "has_cover": bool(row.get("cover_path")),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "published_at": row.get("published_at"),
    }


def _read_track_rows(params: dict) -> list[dict]:
    # Fixed GET method and fixed table. Never accept either from model input.
    return _rest("GET", "mf_tracks", params)


def get_dashboard_stats() -> dict:
    rows = _read_track_rows({
        "select": "status,audio_path",
        "limit": ROW_CAP,
    })

    counts = {status: 0 for status in policy.STATUSES}

    for row in rows:
        status = row.get("status")
        if status in counts:
            counts[status] += 1

    return {
        "rows_returned": len(rows),
        "by_status": counts,
        "awaiting_audio": sum(1 for row in rows if not row.get("audio_path")),
        "may_be_limited_by_database_row_cap": len(rows) >= ROW_CAP,
        "note": "Counts are based on at most 10000 returned rows.",
    }


def get_track_status_summary() -> dict:
    return get_dashboard_stats()


def search_tracks(
    query: str = "",
    status: str | None = None,
    limit: int = 20,
) -> dict:
    if status is not None and status not in policy.STATUSES:
        raise HTTPException(status_code=422, detail="bad_status")

    safe_term = policy.safe_search_term(query)

    params: dict[str, Any] = {
        "select": AGENT_TRACK_SELECT,
        "order": "created_at.desc",
        "limit": max(1, min(int(limit), 50)),
    }

    if status:
        params["status"] = f"eq.{status}"

    if safe_term:
        params["or"] = (
            f"(title.ilike.*{safe_term}*,"
            f"artist.ilike.*{safe_term}*,"
            f"album.ilike.*{safe_term}*)"
        )

    rows = _read_track_rows(params)

    return {
        "tracks": [_safe_track(row) for row in rows],
        "count": len(rows),
    }


def get_track_details(track_id: str) -> dict:
    try:
        normalized_id = str(UUID(track_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=422, detail="invalid_track_id")

    rows = _read_track_rows({
        "select": AGENT_TRACK_SELECT,
        "id": f"eq.{normalized_id}",
        "limit": 1,
    })

    if not rows:
        raise HTTPException(status_code=404, detail="track_not_found")

    return _safe_track(rows[0])


# Only these four functions may ever be exposed as model tools.
READ_ONLY_TOOLS = {
    "get_dashboard_stats": get_dashboard_stats,
    "search_tracks": search_tracks,
    "get_track_details": get_track_details,
    "get_track_status_summary": get_track_status_summary,
}
