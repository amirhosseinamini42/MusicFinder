"""
Pure policy helpers for the MusicFinder upload/admin system.
No FastAPI / network imports, so everything here is unit-testable on its own.
"""
import os
import re
import secrets
from typing import Optional

# ---------- limits ----------
_MB = 1024 * 1024
MAX_AUDIO_BYTES = min(int(os.getenv("MF_MAX_AUDIO_MB", "30")), 50) * _MB   # Supabase free plan cap: 50 MB/file
MAX_COVER_BYTES = 5 * _MB

# extension -> canonical MIME (this is what we tell storage; the client-declared type is never trusted)
AUDIO_EXT = {"mp3": "audio/mpeg", "m4a": "audio/mp4", "wav": "audio/wav", "ogg": "audio/ogg", "flac": "audio/flac"}
IMAGE_EXT = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}

# acceptable client-declared types per extension (browsers vary); empty / octet-stream also tolerated
_AUDIO_ALIASES = {
    "mp3": {"audio/mpeg", "audio/mp3"},
    "m4a": {"audio/mp4", "audio/x-m4a", "audio/m4a", "audio/aac"},
    "wav": {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"},
    "ogg": {"audio/ogg", "application/ogg"},
    "flac": {"audio/flac", "audio/x-flac"},
}
_IMAGE_ALIASES = {"jpg": {"image/jpeg"}, "jpeg": {"image/jpeg"}, "png": {"image/png"}, "webp": {"image/webp"}}

STATUSES = ("draft", "review", "published", "unpublished")
# publishing requires passing through review (or re-publishing something previously unpublished)
TRANSITIONS = {
    "draft": {"review"},
    "review": {"draft", "published"},
    "published": {"unpublished"},
    "unpublished": {"published", "draft", "review"},
}

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PolicyError(ValueError):
    """Carries a machine-readable error code the API maps to HTTP + frontend text."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# ---------- identity / roles ----------
def normalize_email(value: Optional[str]) -> Optional[str]:
    v = (value or "").strip().lower()
    if not v or len(v) > 254 or not _EMAIL.match(v):
        return None
    return v


def check_admin_change(actor_role: str, action: str, target_role: Optional[str]) -> Optional[str]:
    """
    Authorization rule for the admin-management endpoints. Returns an error code, or None if allowed.
      actor_role  : role of the authenticated caller ('owner' / 'admin')
      action      : 'add' | 'revoke'
      target_role : existing role of the target email ('owner' / 'admin' / None if not in table)
    Only the owner may manage administrators; the owner row is never a valid target; nobody can create an owner.
    """
    if actor_role != "owner":
        return "forbidden"
    if target_role == "owner":
        return "owner_protected"
    if action not in ("add", "revoke"):
        return "bad_action"
    return None


def can_transition(current: str, new: str) -> bool:
    return new in TRANSITIONS.get(current, set())


# ---------- text ----------
def clean_line(text: Optional[str], max_len: int) -> str:
    t = _CTRL.sub("", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:max_len]


def clean_block(text: Optional[str], max_len: int) -> str:
    t = _CTRL.sub("", (text or "").replace("\r\n", "\n").replace("\r", "\n"))
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t[:max_len]


def safe_search_term(q: Optional[str]) -> str:
    """Make user text safe to embed in a PostgREST ilike filter (no reserved chars / wildcards)."""
    t = (q or "").replace("'", "_")
    t = re.sub(r"[^\w\s\-]", " ", t, flags=re.UNICODE)
    return re.sub(r"\s+", " ", t).strip()[:80]


# ---------- files ----------
def file_ext(filename: str) -> str:
    base = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[-1].lower() if "." in base else ""


def check_declared_file(kind: str, filename: str, size: int, declared_type: Optional[str]) -> str:
    """Validate what the client *claims* before issuing an upload URL. Returns the extension."""
    table = AUDIO_EXT if kind == "audio" else IMAGE_EXT
    aliases = _AUDIO_ALIASES if kind == "audio" else _IMAGE_ALIASES
    ext = file_ext(filename)
    if ext not in table:
        raise PolicyError("bad_audio_type" if kind == "audio" else "bad_cover_type")
    limit = MAX_AUDIO_BYTES if kind == "audio" else MAX_COVER_BYTES
    if size <= 0:
        raise PolicyError("empty_file")
    if size > limit:
        raise PolicyError("audio_too_large" if kind == "audio" else "cover_too_large")
    dt = (declared_type or "").split(";")[0].strip().lower()
    if dt and dt != "application/octet-stream" and dt not in aliases[ext]:
        raise PolicyError("bad_audio_type" if kind == "audio" else "bad_cover_type")
    return "jpg" if ext == "jpeg" else ext


def canonical_mime(kind: str, ext: str) -> str:
    return (AUDIO_EXT if kind == "audio" else IMAGE_EXT)[ext]


def sniff_audio(head: bytes) -> Optional[str]:
    """Identify an audio container from its first bytes. Returns an extension key or None."""
    if len(head) < 12:
        return None
    if head[:3] == b"ID3" or (head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "mp3"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"fLaC":
        return "flac"
    if head[4:8] == b"ftyp":
        return "m4a"
    return None


def sniff_image(head: bytes) -> Optional[str]:
    if head[:3] == b"\xff\xd8\xff":
        return "jpg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def validate_signature(kind: str, ext: str, head: bytes, total_size: int) -> None:
    """Server-side verification of an object that was uploaded directly to storage."""
    limit = MAX_AUDIO_BYTES if kind == "audio" else MAX_COVER_BYTES
    if total_size <= 0:
        raise PolicyError("empty_file")
    if total_size > limit:
        raise PolicyError("audio_too_large" if kind == "audio" else "cover_too_large")
    found = sniff_audio(head) if kind == "audio" else sniff_image(head)
    if found != ext:
        raise PolicyError("bad_audio_file" if kind == "audio" else "bad_cover_file")


def make_key(kind: str, track_id: str, ext: str) -> str:
    """Server-generated, unguessable storage key. User filenames are never used."""
    return f"{track_id}/{secrets.token_hex(16)}.{ext}"
