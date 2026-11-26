"""
MusicFinder regression tests: admin permissions + upload flow (audio, covers, unreleased, ownership,
large files, storage/database failures, retries, duplicate prevention).

Policy under test (decided by the owner):
  * owner AND admins can do everything with tracks (create, upload, finalize, edit, status, delete);
  * ONLY managing administrators (add / revoke / list) and the owner row is owner-only.

Nothing here touches the network, Supabase or Google: admin._rest, the storage helpers and the Google
token check are replaced with an in-memory fake, so the tests exercise the real FastAPI routes,
the real validation (mf_policy) and the real upload state machine in admin.py.

Run from the project root:
    pip install -r requirements.txt -r requirements-dev.txt pytest
    pytest tests/test_admin_permissions.py -v
(requirements-dev.txt only lists httpx; pytest has to be installed too.)
"""
import copy
import os
import sys
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import admin as adm  # noqa: E402
import mf_policy as policy  # noqa: E402
from library import err  # noqa: E402

OWNER_EMAIL = "owner@example.com"
ADMIN_EMAIL = "admin@example.com"
ADMIN2_EMAIL = "admin2@example.com"
REVOKED_EMAIL = "revoked@example.com"

T_OWNER, T_ADMIN, T_ADMIN2, T_REVOKED, T_STRANGER = "t-owner", "t-admin", "t-admin2", "t-revoked", "t-stranger"
IDENTITIES = {
    T_OWNER: OWNER_EMAIL, T_ADMIN: ADMIN_EMAIL, T_ADMIN2: ADMIN2_EMAIL,
    T_REVOKED: REVOKED_EMAIL, T_STRANGER: "stranger@example.com",
}
EITHER_ROLE = [T_OWNER, T_ADMIN]

MP3_HEAD = b"ID3\x04\x00" + b"\x00" * 59
JPG_HEAD = b"\xff\xd8\xff\xe0" + b"\x00" * 60
GARBAGE_HEAD = b"this is definitely not media" + b"\x00" * 36
AUDIO_TOTAL, COVER_TOTAL = 1_000_000, 50_000
TS = "2026-01-01T00:00:00+00:00"


# =====================================================================
# In-memory fake of Supabase (database + storage) and Google identity
# =====================================================================
def _match(row, params):
    for key, value in (params or {}).items():
        if key in ("select", "order", "limit", "offset", "or", "on_conflict"):
            continue
        if value.startswith("eq."):
            if str(row.get(key)) != value[3:]:
                return False
        elif value == "is.null":
            if row.get(key) is not None:
                return False
        elif value == "not.is.null":
            if row.get(key) is None:
                return False
    return True


class Backend:
    def __init__(self):
        self.tables = {
            "mf_admins": [
                {"email": OWNER_EMAIL, "role": "owner", "revoked_at": None, "created_at": TS, "added_by": None},
                {"email": ADMIN_EMAIL, "role": "admin", "revoked_at": None, "created_at": TS, "added_by": OWNER_EMAIL},
                {"email": ADMIN2_EMAIL, "role": "admin", "revoked_at": None, "created_at": TS, "added_by": OWNER_EMAIL},
                {"email": REVOKED_EMAIL, "role": "admin", "revoked_at": TS, "created_at": TS, "added_by": OWNER_EMAIL},
            ],
            "mf_tracks": [],
            "mf_rights_ack": [],
        }
        self.store = {}          # (bucket, key) -> (head_bytes, total_size)
        self.removed = []        # every storage key that was deleted
        self.sign_calls = 0
        self.fail = {}           # (method, table) -> HTTPException to raise

    @property
    def tracks(self):
        return self.tables["mf_tracks"]

    def row(self, tid):
        return next((r for r in self.tracks if r["id"] == tid), None)

    # ---- database ----
    def rest(self, method, table, params=None, json=None, prefer="return=representation", conflict_ok=False):
        if (method, table) in self.fail:
            raise self.fail[(method, table)]
        rows = self.tables[table]
        params = params or {}
        if method == "GET":
            return [copy.deepcopy(r) for r in rows if _match(r, params)]
        if method == "POST":
            if table == "mf_tracks":
                rid = json.get("client_request_id")
                if rid and any(r.get("client_request_id") == rid and r.get("created_by") == json.get("created_by") for r in rows):
                    if conflict_ok:
                        return None
                    raise err(502, "storage_failed")
                new = {"id": str(uuid.uuid4()), "album": "", "description": "", "audio_path": None, "cover_path": None,
                       "audio_path_new": None, "cover_path_new": None, "audio_ext": None, "cover_ext": None,
                       "audio_ext_new": None, "cover_ext_new": None, "audio_size": None, "published_at": None,
                       "created_at": TS, "updated_at": TS, **copy.deepcopy(json)}
            elif table == "mf_rights_ack":
                if any(r["email"] == json["email"] for r in rows):
                    return []
                new = dict(json)
            else:
                new = {"created_at": TS, "revoked_at": None, **copy.deepcopy(json)}
            rows.append(new)
            return [copy.deepcopy(new)]
        if method == "PATCH":
            hit = [r for r in rows if _match(r, params)]
            for r in hit:
                r.update(copy.deepcopy(json))
            return [copy.deepcopy(r) for r in hit]
        if method == "DELETE":
            self.tables[table] = [r for r in rows if not _match(r, params)]
            return []
        raise AssertionError(f"unexpected {method} {table}")

    # ---- storage ----
    def sign_upload(self, bucket, key):
        self.sign_calls += 1
        return f"https://storage.test/upload/{bucket}/{key}?token=x"

    def sign_download(self, bucket, keys, ttl, download_name=None):
        return {k: f"https://storage.test/{bucket}/{k}?token=x" for k in keys if k}

    def read_head(self, bucket, key, n=64):
        return self.store.get((bucket, key))

    def remove_objects(self, bucket, keys):
        for k in keys:
            if k:
                self.removed.append(k)
                self.store.pop((bucket, k), None)

    # ---- identity ----
    def verify(self, token):
        if token not in IDENTITIES:
            raise err(401, "session_expired")
        return {"sub": token, "email": IDENTITIES[token], "name": token}

    # ---- test helper: what the browser does after receiving the signed URL ----
    def put(self, tid, kind, head=None, total=None):
        key = self.row(tid)[f"{kind}_path_new"]
        bucket = adm.AUDIO_BUCKET if kind == "audio" else adm.COVER_BUCKET
        self.store[(bucket, key)] = (head or (MP3_HEAD if kind == "audio" else JPG_HEAD),
                                     total or (AUDIO_TOTAL if kind == "audio" else COVER_TOTAL))
        return key


@pytest.fixture
def be(monkeypatch):
    b = Backend()
    monkeypatch.setattr(adm, "_rest", b.rest)
    monkeypatch.setattr(adm, "_verify_google", b.verify)
    monkeypatch.setattr(adm, "sign_upload", b.sign_upload)
    monkeypatch.setattr(adm, "sign_download", b.sign_download)
    monkeypatch.setattr(adm, "read_head", b.read_head)
    monkeypatch.setattr(adm, "remove_objects", b.remove_objects)
    adm._hits.clear()
    return b


@pytest.fixture
def api(be):
    app = FastAPI()
    app.include_router(adm.admin_router)
    app.include_router(adm.public_router)
    client = TestClient(app)

    def call(method, path, who=None, **kw):
        headers = {"Authorization": f"Bearer {who}"} if who else {}
        return client.request(method, path, headers=headers, **kw)
    return call


# =====================================================================
# helpers
# =====================================================================
def code(resp):
    return resp.json()["detail"]["code"]


def body(**over):
    b = {"title": "Song", "artist": "Artist", "rights_confirmed": True, "client_request_id": "req-12345678",
         "audio": {"filename": "a.mp3", "size": AUDIO_TOTAL, "content_type": "audio/mpeg"},
         "cover": {"filename": "c.jpg", "size": COVER_TOTAL, "content_type": "image/jpeg"}}
    b.update(over)
    return b


def create(api, who, **over):
    r = api("POST", "/admin/tracks", who, json=body(**over))
    assert r.status_code in (200, 201), r.text
    return r.json()["track"]["id"]


def create_uploaded(api, be, who, **over):
    """create -> browser uploads both files -> finalize; returns track id"""
    tid = create(api, who, **over)
    be.put(tid, "audio")
    if be.row(tid)["cover_path_new"]:
        be.put(tid, "cover")
    r = api("POST", f"/admin/tracks/{tid}/finalize", who, json={"audio": True, "cover": True})
    assert r.status_code == 200, r.text
    return tid


def set_status(api, who, tid, status):
    return api("POST", f"/admin/tracks/{tid}/status", who, json={"status": status})


def publish(api, who, tid):
    assert set_status(api, who, tid, "review").status_code == 200
    r = set_status(api, who, tid, "published")
    assert r.status_code == 200, r.text


# =====================================================================
# 1. Permissions: owner and admins share all track rights
# =====================================================================
@pytest.mark.parametrize("who", EITHER_ROLE)
def test_owner_and_admin_have_full_track_lifecycle(api, be, who):
    tid = create_uploaded(api, be, who, is_unreleased=True)
    assert api("PATCH", f"/admin/tracks/{tid}", who, json={"title": "Renamed", "download_enabled": True}).status_code == 200
    publish(api, who, tid)
    assert set_status(api, who, tid, "unpublished").status_code == 200
    assert api("DELETE", f"/admin/tracks/{tid}", who).status_code == 200
    assert be.row(tid) is None


def test_admin_can_edit_and_delete_tracks_made_by_someone_else(api, be):
    tid = create_uploaded(api, be, T_ADMIN)
    r = api("PATCH", f"/admin/tracks/{tid}", T_ADMIN2, json={"title": "Fixed by admin2"})
    assert r.status_code == 200
    assert r.json()["track"]["updated_by"] == ADMIN2_EMAIL
    assert r.json()["track"]["created_by"] == ADMIN_EMAIL
    assert api("DELETE", f"/admin/tracks/{tid}", T_ADMIN2).status_code == 200


def test_track_records_who_created_and_who_changed_it(api, be):
    tid = create(api, T_ADMIN)
    assert be.row(tid)["created_by"] == ADMIN_EMAIL
    api("PATCH", f"/admin/tracks/{tid}", T_OWNER, json={"album": "LP"})
    assert be.row(tid)["updated_by"] == OWNER_EMAIL
    assert be.row(tid)["created_by"] == ADMIN_EMAIL


def test_admin_cannot_manage_administrators(api, be):
    assert code(api("GET", "/admin/admins", T_ADMIN)) == "forbidden"
    assert code(api("POST", "/admin/admins", T_ADMIN, json={"email": "x@example.com"})) == "forbidden"
    assert code(api("DELETE", f"/admin/admins/{ADMIN2_EMAIL}", T_ADMIN)) == "forbidden"
    assert [r["email"] for r in be.tables["mf_admins"] if r["revoked_at"] is None] == [OWNER_EMAIL, ADMIN_EMAIL, ADMIN2_EMAIL]


def test_owner_can_add_and_revoke_admins(api, be):
    r = api("POST", "/admin/admins", T_OWNER, json={"email": "New.Admin@Example.com"})
    assert r.status_code == 201 and r.json()["email"] == "new.admin@example.com"
    added = next(x for x in be.tables["mf_admins"] if x["email"] == "new.admin@example.com")
    assert added["role"] == "admin" and added["added_by"] == OWNER_EMAIL
    assert api("DELETE", "/admin/admins/new.admin@example.com", T_OWNER).status_code == 200
    assert added["revoked_at"] is not None


def test_owner_row_is_protected_even_from_the_owner(api, be):
    assert code(api("POST", "/admin/admins", T_OWNER, json={"email": OWNER_EMAIL})) == "owner_protected"
    assert code(api("DELETE", f"/admin/admins/{OWNER_EMAIL}", T_OWNER)) == "owner_protected"
    assert next(x for x in be.tables["mf_admins"] if x["email"] == OWNER_EMAIL)["revoked_at"] is None


def test_readding_a_revoked_admin_restores_access(api, be):
    assert api("GET", "/admin/tracks", T_REVOKED).status_code == 403
    assert api("POST", "/admin/admins", T_OWNER, json={"email": REVOKED_EMAIL}).status_code == 201
    assert api("GET", "/admin/tracks", T_REVOKED).status_code == 200


def test_revoked_admin_is_denied_everywhere(api, be):
    for method, path, kw in (("GET", "/admin/tracks", {}), ("GET", "/admin/stats", {}),
                             ("POST", "/admin/tracks", {"json": body()})):
        r = api(method, path, T_REVOKED, **kw)
        assert r.status_code == 403 and code(r) == "not_authorized"
    assert be.tracks == []


def test_verified_google_user_who_is_not_an_admin_is_denied(api, be):
    r = api("POST", "/admin/tracks", T_STRANGER, json=body())
    assert r.status_code == 403 and code(r) == "not_authorized"
    assert be.tracks == [] and be.sign_calls == 0


def test_missing_or_invalid_token(api):
    assert code(api("GET", "/admin/tracks")) == "auth_required"
    r = api("GET", "/admin/tracks", "garbage")
    assert r.status_code == 401 and code(r) == "session_expired"


def test_revocation_takes_effect_on_the_very_next_request(api, be):
    assert api("GET", "/admin/stats", T_ADMIN).status_code == 200
    assert api("DELETE", f"/admin/admins/{ADMIN_EMAIL}", T_OWNER).status_code == 200
    r = api("GET", "/admin/stats", T_ADMIN)
    assert r.status_code == 403 and code(r) == "not_authorized"


def test_one_time_rights_ack_covers_later_uploads(api, be):
    assert api("GET", "/admin/me", T_ADMIN).json()["rights_ack"] is False
    assert api("POST", "/admin/rights-ack", T_ADMIN).status_code == 200
    assert api("GET", "/admin/me", T_ADMIN).json()["rights_ack"] is True
    tid = create(api, T_ADMIN, rights_confirmed=False)
    assert be.row(tid)["rights_confirmed"] is True


def test_cannot_publish_without_rights_confirmation(api, be):
    tid = create_uploaded(api, be, T_ADMIN, rights_confirmed=False)
    assert set_status(api, T_ADMIN, tid, "review").status_code == 200
    r = set_status(api, T_ADMIN, tid, "published")
    assert r.status_code == 422 and code(r) == "rights_not_confirmed"


# =====================================================================
# 2. Audio, covers, unreleased
# =====================================================================
@pytest.mark.parametrize("who", EITHER_ROLE)
def test_audio_and_cover_upload_end_to_end(api, be, who):
    r = api("POST", "/admin/tracks", who, json=body())
    assert r.status_code == 201
    data = r.json()
    assert set(data["uploads"]) == {"audio", "cover"}
    assert data["uploads"]["audio"]["content_type"] == "audio/mpeg"
    assert data["uploads"]["cover"]["content_type"] == "image/jpeg"
    tid = data["track"]["id"]
    assert data["track"]["has_audio"] is False          # nothing is live before finalize
    be.put(tid, "audio")
    be.put(tid, "cover")
    r = api("POST", f"/admin/tracks/{tid}/finalize", who, json={"audio": True, "cover": True})
    assert r.status_code == 200
    track = r.json()["track"]
    assert track["has_audio"] and track["has_cover"] and not track["audio_pending"] and not track["cover_pending"]
    assert track["audio_size"] == AUDIO_TOTAL and track["status"] == "draft"


def test_audio_only_upload_without_cover(api, be):
    tid = create_uploaded(api, be, T_ADMIN, cover=None)
    row = be.row(tid)
    assert row["audio_path"] and row["cover_path"] is None


def test_unreleased_flag_is_stored_toggled_and_exposed_publicly(api, be):
    tid = create_uploaded(api, be, T_ADMIN, is_unreleased=True, title="Leaked Demo")
    assert be.row(tid)["is_unreleased"] is True
    publish(api, T_ADMIN, tid)
    pub = api("GET", "/tracks/search").json()["tracks"]
    assert [(t["id"], t["is_unreleased"]) for t in pub] == [(f"mf:{tid}", True)]
    api("PATCH", f"/admin/tracks/{tid}", T_ADMIN, json={"is_unreleased": False})
    assert api("GET", "/tracks/search").json()["tracks"][0]["is_unreleased"] is False


def test_finalize_without_upload_reports_missing_and_never_goes_live(api, be):
    tid = create(api, T_ADMIN)
    r = api("POST", f"/admin/tracks/{tid}/finalize", T_ADMIN, json={"audio": True, "cover": True})
    assert r.status_code == 422 and code(r) == "finalize_failed"
    assert r.json()["detail"]["files"] == {"audio": "upload_missing", "cover": "upload_missing"}
    assert be.row(tid)["audio_path"] is None
    assert api("GET", "/admin/tracks", T_ADMIN).json()["tracks"] == []
    r = set_status(api, T_ADMIN, tid, "review")
    assert r.status_code == 422 and code(r) == "audio_missing"
    r = set_status(api, T_ADMIN, tid, "published")
    assert r.status_code == 409 and code(r) == "bad_transition"


def test_finalize_cannot_skip_audio_by_omitting_the_upload_url_step(api, be):
    tid = create(api, T_ADMIN)
    row = be.row(tid)
    # Simulate a caller that jumps directly from draft creation to finalize,
    # without requesting or transferring an audio object.
    row["audio_path_new"] = None
    row["audio_ext_new"] = None
    r = api("POST", f"/admin/tracks/{tid}/finalize", T_ADMIN, json={"audio": False, "cover": False})
    assert r.status_code == 422 and code(r) == "finalize_failed"
    assert r.json()["detail"]["files"] == {"audio": "upload_missing"}
    assert be.row(tid)["audio_path"] is None
    assert api("GET", "/admin/tracks", T_ADMIN).json()["tracks"] == []


def test_tracks_list_hides_upload_drafts_until_audio_is_verified(api, be):
    incomplete = create(api, T_ADMIN, client_request_id="req-incomplete01")
    complete = create_uploaded(api, be, T_ADMIN, title="Ready Track", client_request_id="req-complete001")
    rows = api("GET", "/admin/tracks", T_ADMIN).json()["tracks"]
    assert [row["id"] for row in rows] == [complete]
    assert be.row(incomplete)["audio_path"] is None


def test_audio_replacement_swaps_only_after_server_verification(api, be):
    tid = create_uploaded(api, be, T_ADMIN, client_request_id="req-audiorepl01")
    old_audio = be.row(tid)["audio_path"]
    old_size = be.row(tid)["audio_size"]
    r = api("POST", f"/admin/tracks/{tid}/upload-urls", T_ADMIN,
            json={"audio": {"filename": "replacement.mp3", "size": 2000, "content_type": "audio/mpeg"}})
    assert r.status_code == 200 and "audio" in r.json()["uploads"]
    new_audio = be.row(tid)["audio_path_new"]
    assert new_audio and new_audio != old_audio
    assert be.row(tid)["audio_path"] == old_audio
    be.put(tid, "audio", total=2000)
    r = api("POST", f"/admin/tracks/{tid}/finalize", T_ADMIN, json={"audio": True, "cover": False})
    assert r.status_code == 200, r.text
    row = be.row(tid)
    assert row["audio_path"] == new_audio and row["audio_size"] == 2000
    assert old_audio in be.removed and row["cover_path"] is not None
    assert old_size != row["audio_size"]


def test_failed_audio_replacement_preserves_the_live_audio(api, be):
    tid = create_uploaded(api, be, T_ADMIN, client_request_id="req-audiobad001")
    old_audio = be.row(tid)["audio_path"]
    old_cover = be.row(tid)["cover_path"]
    api("POST", f"/admin/tracks/{tid}/upload-urls", T_ADMIN,
        json={"audio": {"filename": "bad.mp3", "size": 2000, "content_type": "audio/mpeg"}})
    new_audio = be.row(tid)["audio_path_new"]
    be.put(tid, "audio", head=GARBAGE_HEAD, total=2000)
    r = api("POST", f"/admin/tracks/{tid}/finalize", T_ADMIN, json={"audio": True, "cover": False})
    assert r.status_code == 422 and r.json()["detail"]["files"] == {"audio": "bad_audio_file"}
    row = be.row(tid)
    assert row["audio_path"] == old_audio and row["cover_path"] == old_cover
    assert row["audio_path_new"] is None and new_audio in be.removed
    assert old_audio not in be.removed


def test_finalize_rejects_file_whose_content_does_not_match_its_type(api, be):
    tid = create(api, T_ADMIN, cover=None)
    key = be.put(tid, "audio", head=GARBAGE_HEAD)
    r = api("POST", f"/admin/tracks/{tid}/finalize", T_ADMIN, json={"audio": True, "cover": False})
    assert r.status_code == 422 and r.json()["detail"]["files"] == {"audio": "bad_audio_file"}
    assert key in be.removed                               # the bad object is deleted
    row = be.row(tid)
    assert row["audio_path"] is None and row["audio_path_new"] is None


def test_finalize_rejects_oversized_stored_object(api, be):
    tid = create(api, T_ADMIN, cover=None)
    be.put(tid, "audio", total=policy.MAX_AUDIO_BYTES + 1)
    r = api("POST", f"/admin/tracks/{tid}/finalize", T_ADMIN, json={"audio": True, "cover": False})
    assert r.json()["detail"]["files"] == {"audio": "audio_too_large"}
    assert be.row(tid)["audio_path"] is None


def test_wrong_cover_does_not_destroy_the_live_cover_or_metadata(api, be):
    tid = create_uploaded(api, be, T_ADMIN, title="Keep Me")
    old_cover = be.row(tid)["cover_path"]
    old_audio = be.row(tid)["audio_path"]
    assert api("POST", f"/admin/tracks/{tid}/upload-urls", T_ADMIN,
               json={"cover": {"filename": "n.png", "size": 1000, "content_type": "image/png"}}).status_code == 200
    be.put(tid, "cover", head=GARBAGE_HEAD, total=100)
    r = api("POST", f"/admin/tracks/{tid}/finalize", T_ADMIN, json={"audio": False, "cover": True})
    assert r.status_code == 422 and r.json()["detail"]["files"] == {"cover": "bad_cover_file"}
    row = be.row(tid)
    assert row["cover_path"] == old_cover and row["audio_path"] == old_audio and row["title"] == "Keep Me"
    assert old_cover not in be.removed and old_audio not in be.removed


def test_cover_replacement_swaps_only_after_verification(api, be):
    tid = create_uploaded(api, be, T_ADMIN)
    old_cover = be.row(tid)["cover_path"]
    api("POST", f"/admin/tracks/{tid}/upload-urls", T_ADMIN,
        json={"cover": {"filename": "n.png", "size": 1000, "content_type": "image/png"}})
    assert be.row(tid)["cover_path"] == old_cover          # old one still live while the new one uploads
    be.put(tid, "cover", head=b"\x89PNG\r\n\x1a\n" + b"\x00" * 56, total=1000)
    assert api("POST", f"/admin/tracks/{tid}/finalize", T_ADMIN, json={"audio": False, "cover": True}).status_code == 200
    row = be.row(tid)
    assert row["cover_path"] != old_cover and row["cover_ext"] == "png"
    assert old_cover in be.removed


def test_remove_cover_keeps_audio_and_metadata(api, be):
    tid = create_uploaded(api, be, T_ADMIN, title="T")
    audio = be.row(tid)["audio_path"]
    r = api("DELETE", f"/admin/tracks/{tid}/cover", T_ADMIN)
    assert r.status_code == 200 and r.json()["track"]["has_cover"] is False
    row = be.row(tid)
    assert row["audio_path"] == audio and row["title"] == "T"


def test_audio_cannot_be_swapped_under_a_published_track(api, be):
    tid = create_uploaded(api, be, T_ADMIN)
    publish(api, T_ADMIN, tid)
    r = api("POST", f"/admin/tracks/{tid}/upload-urls", T_ADMIN,
            json={"audio": {"filename": "b.mp3", "size": 1000, "content_type": "audio/mpeg"}})
    assert r.status_code == 409 and code(r) == "unpublish_first"


# =====================================================================
# 3. Large files and declared-file validation (rejected before any DB write)
# =====================================================================
def test_audio_over_limit_is_rejected_before_any_record_or_url_exists(api, be):
    big = {"filename": "a.mp3", "size": policy.MAX_AUDIO_BYTES + 1, "content_type": "audio/mpeg"}
    r = api("POST", "/admin/tracks", T_ADMIN, json=body(audio=big))
    assert r.status_code == 422 and code(r) == "audio_too_large"
    assert be.tracks == [] and be.sign_calls == 0


def test_audio_exactly_at_the_limit_is_accepted(api, be):
    at_limit = {"filename": "a.mp3", "size": policy.MAX_AUDIO_BYTES, "content_type": "audio/mpeg"}
    assert api("POST", "/admin/tracks", T_ADMIN, json=body(audio=at_limit)).status_code == 201


def test_cover_over_5mb_is_rejected(api, be):
    big = {"filename": "c.jpg", "size": policy.MAX_COVER_BYTES + 1, "content_type": "image/jpeg"}
    r = api("POST", "/admin/tracks", T_ADMIN, json=body(cover=big))
    assert r.status_code == 422 and code(r) == "cover_too_large" and be.tracks == []


@pytest.mark.parametrize("audio,expected", [
    ({"filename": "a.exe", "size": 100, "content_type": "audio/mpeg"}, "bad_audio_type"),
    ({"filename": "a.mp3", "size": 100, "content_type": "video/mp4"}, "bad_audio_type"),
    ({"filename": "noext", "size": 100, "content_type": None}, "bad_audio_type"),
])
def test_bad_audio_declarations_rejected(api, be, audio, expected):
    r = api("POST", "/admin/tracks", T_ADMIN, json=body(audio=audio))
    assert r.status_code == 422 and code(r) == expected and be.tracks == []


def test_bad_cover_type_rejected(api, be):
    r = api("POST", "/admin/tracks", T_ADMIN, json=body(cover={"filename": "c.gif", "size": 100, "content_type": "image/gif"}))
    assert r.status_code == 422 and code(r) == "bad_cover_type" and be.tracks == []


def test_empty_title_or_artist_rejected(api, be):
    assert code(api("POST", "/admin/tracks", T_ADMIN, json=body(title="   "))) == "title_required"
    assert code(api("POST", "/admin/tracks", T_ADMIN, json=body(artist="   "))) == "artist_required"
    assert be.tracks == []


# =====================================================================
# 4. Duplicates, retries, storage / database failures
# =====================================================================
def test_double_submit_with_same_request_id_creates_one_track(api, be):
    r1 = api("POST", "/admin/tracks", T_ADMIN, json=body())
    first_key = be.row(r1.json()["track"]["id"])["audio_path_new"]
    r2 = api("POST", "/admin/tracks", T_ADMIN, json=body())
    assert r1.status_code == 201 and r2.status_code == 200
    assert r1.json()["track"]["id"] == r2.json()["track"]["id"]
    assert len(be.tracks) == 1
    assert first_key in be.removed                          # stale never-finalized upload cleaned up
    assert be.row(r1.json()["track"]["id"])["audio_path_new"] != first_key


def test_same_request_id_from_two_admins_does_not_collide(api, be):
    a = api("POST", "/admin/tracks", T_ADMIN, json=body())
    b = api("POST", "/admin/tracks", T_ADMIN2, json=body())
    assert a.json()["track"]["id"] != b.json()["track"]["id"] and len(be.tracks) == 2


def test_retry_after_failed_upload_gets_fresh_urls_and_cleans_the_old_key(api, be):
    tid = create(api, T_ADMIN, cover=None)
    k1 = be.row(tid)["audio_path_new"]
    r = api("POST", f"/admin/tracks/{tid}/upload-urls", T_ADMIN,
            json={"audio": {"filename": "a.mp3", "size": AUDIO_TOTAL, "content_type": "audio/mpeg"}})
    assert r.status_code == 200
    k2 = be.row(tid)["audio_path_new"]
    assert k2 != k1 and k1 in be.removed
    be.put(tid, "audio")
    assert api("POST", f"/admin/tracks/{tid}/finalize", T_ADMIN, json={"audio": True, "cover": False}).status_code == 200
    assert be.row(tid)["audio_path"] == k2 and len(be.tracks) == 1


def test_finalize_is_safe_to_call_twice(api, be):
    tid = create_uploaded(api, be, T_ADMIN)
    audio = be.row(tid)["audio_path"]
    r = api("POST", f"/admin/tracks/{tid}/finalize", T_ADMIN, json={"audio": True, "cover": True})
    assert r.status_code == 200 and be.row(tid)["audio_path"] == audio


def test_reissue_with_nothing_to_upload_is_rejected(api, be):
    tid = create(api, T_ADMIN)
    r = api("POST", f"/admin/tracks/{tid}/upload-urls", T_ADMIN, json={})
    assert r.status_code == 422 and code(r) == "nothing_to_upload"


def test_storage_failure_while_signing_leaves_no_orphan_record(api, be, monkeypatch):
    def boom(bucket, key):
        raise err(502, "storage_failed")
    monkeypatch.setattr(adm, "sign_upload", boom)
    r = api("POST", "/admin/tracks", T_ADMIN, json=body())
    assert r.status_code == 502 and code(r) == "storage_failed"
    assert be.tracks == []


def test_database_failure_on_create_issues_no_upload_urls(api, be):
    be.fail[("POST", "mf_tracks")] = err(502, "storage_failed")
    r = api("POST", "/admin/tracks", T_ADMIN, json=body())
    assert r.status_code == 502 and code(r) == "storage_failed"
    assert be.tracks == [] and be.sign_calls == 0


def test_database_failure_during_finalize_never_reports_success(api, be):
    tid = create(api, T_ADMIN)
    be.put(tid, "audio")
    be.put(tid, "cover")
    be.fail[("PATCH", "mf_tracks")] = err(502, "storage_failed")
    r = api("POST", f"/admin/tracks/{tid}/finalize", T_ADMIN, json={"audio": True, "cover": True})
    assert r.status_code == 502
    assert be.row(tid)["audio_path"] is None               # not live: the record was never switched over


def test_storage_unavailable_during_delete_keeps_the_record(api, be, monkeypatch):
    tid = create_uploaded(api, be, T_ADMIN)

    def boom(bucket, keys):
        raise err(502, "storage_failed")
    monkeypatch.setattr(adm, "remove_objects", boom)
    r = api("DELETE", f"/admin/tracks/{tid}", T_ADMIN)
    assert r.status_code == 502 and be.row(tid) is not None   # nothing half-deleted: the row survives for a retry


def test_delete_removes_row_and_all_files(api, be):
    tid = create_uploaded(api, be, T_ADMIN)
    keys = {be.row(tid)["audio_path"], be.row(tid)["cover_path"]}
    assert api("DELETE", f"/admin/tracks/{tid}", T_ADMIN).status_code == 200
    assert be.row(tid) is None and keys <= set(be.removed)
    assert api("DELETE", f"/admin/tracks/{tid}", T_ADMIN).status_code == 404


def test_unknown_or_malformed_track_id_is_404(api):
    assert api("GET", f"/admin/tracks/{uuid.uuid4()}/preview", T_ADMIN).status_code == 404
    assert api("DELETE", "/admin/tracks/not-a-uuid", T_ADMIN).status_code == 404


# =====================================================================
# 5. Public side: only published tracks are visible
# =====================================================================
def test_play_is_available_only_while_published(api, be):
    tid = create_uploaded(api, be, T_ADMIN)
    assert api("GET", f"/tracks/{tid}/play").status_code == 404           # draft
    publish(api, T_ADMIN, tid)
    r = api("GET", f"/tracks/{tid}/play")
    assert r.status_code == 200 and r.json()["url"].startswith("https://storage.test/")
    set_status(api, T_ADMIN, tid, "unpublished")
    assert api("GET", f"/tracks/{tid}/play").status_code == 404


def test_public_search_hides_drafts(api, be):
    draft = create_uploaded(api, be, T_ADMIN, title="Draft One", client_request_id="req-draft0001")
    live = create_uploaded(api, be, T_ADMIN, title="Live One", client_request_id="req-live00001")
    publish(api, T_ADMIN, live)
    ids = [t["id"] for t in api("GET", "/tracks/search").json()["tracks"]]
    assert ids == [f"mf:{live}"] and f"mf:{draft}" not in ids


def test_download_respects_the_download_flag(api, be):
    tid = create_uploaded(api, be, T_ADMIN)
    publish(api, T_ADMIN, tid)
    r = api("GET", f"/tracks/{tid}/download")
    assert r.status_code == 403 and code(r) == "download_disabled"
    api("PATCH", f"/admin/tracks/{tid}", T_ADMIN, json={"download_enabled": True})
    assert api("GET", f"/tracks/{tid}/download").status_code == 200


def test_status_transitions_are_enforced(api, be):
    tid = create_uploaded(api, be, T_ADMIN)
    r = set_status(api, T_ADMIN, tid, "published")          # draft -> published must pass through review
    assert r.status_code == 409 and code(r) == "bad_transition"
    r = set_status(api, T_ADMIN, tid, "nonsense")
    assert r.status_code == 422 and code(r) == "bad_status"
