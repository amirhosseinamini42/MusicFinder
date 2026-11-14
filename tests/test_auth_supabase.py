import os
import time
import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import auth_supabase


class Response:
    def __init__(self, status=200, body=None, bad_json=False):
        self.status_code = status
        self.body = body
        self.bad_json = bad_json

    def json(self):
        if self.bad_json:
            raise ValueError("bad json")
        return self.body


def valid_user(**overrides):
    body = {
        "id": "a1e9a1c2-7d6f-4e3d-9b7a-2a3f4c5d6e7f",
        "email": "person@example.com",
        "email_confirmed_at": "2026-01-01T00:00:00Z",
        "user_metadata": {"full_name": "Person Example", "avatar_url": "https://cdn.example/avatar.png"},
        "app_metadata": {"provider": "email"},
        "identities": [],
    }
    body.update(overrides)
    return body


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "public-test-key")


def test_valid_supabase_user_and_request_contract():
    with patch.object(auth_supabase.requests, "get", return_value=Response(body=valid_user())) as get:
        ident = auth_supabase.verify_supabase_access_token("access-token")
    assert ident["id"] == "a1e9a1c2-7d6f-4e3d-9b7a-2a3f4c5d6e7f"
    assert ident["sub"] == ident["id"]
    assert ident["email"] == "person@example.com"
    assert ident["name"] == "Person Example"
    assert ident["picture"] == "https://cdn.example/avatar.png"
    assert get.call_args.args[0] == "https://project.supabase.co/auth/v1/user"
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer access-token"
    assert get.call_args.kwargs["allow_redirects"] is False


def test_google_identity_keeps_legacy_google_sub_for_existing_library_data():
    user = valid_user(identities=[{"provider": "google", "id": "google-sub-123", "identity_data": {"sub": "google-sub-123"}}])
    with patch.object(auth_supabase.requests, "get", return_value=Response(body=user)):
        ident = auth_supabase.verify_supabase_access_token("access-token")
    assert ident["sub"] == ident["id"]
    assert ident["legacy_google_sub"] == "google-sub-123"
    assert ident["primary_provider"] == "email"


@pytest.mark.parametrize("user, expected", [
    (valid_user(email_confirmed_at=None, confirmed_at=None), (403, "email_not_verified")),
    (valid_user(email="not-an-email"), (401, "session_expired")),
    (valid_user(id="not-a-uuid"), (401, "session_expired")),
    (valid_user(identities="bad"), (200, "ok")),
])
def test_user_claim_validation(user, expected):
    with patch.object(auth_supabase.requests, "get", return_value=Response(body=user)):
        if expected[0] == 200:
            assert auth_supabase.verify_supabase_access_token("access-token")["email"] == "person@example.com"
        else:
            with pytest.raises(HTTPException) as exc:
                auth_supabase.verify_supabase_access_token("access-token")
            assert (exc.value.status_code, exc.value.detail["code"]) == expected


def test_invalid_or_expired_access_token_is_rejected():
    with patch.object(auth_supabase.requests, "get", return_value=Response(status=401, body={})):
        with pytest.raises(HTTPException) as exc:
            auth_supabase.verify_supabase_access_token("bad-token")
    assert (exc.value.status_code, exc.value.detail["code"]) == (401, "session_expired")


def test_auth_service_failure_fails_closed():
    with patch.object(auth_supabase.requests, "get", return_value=Response(status=503, body={})):
        with pytest.raises(HTTPException) as exc:
            auth_supabase.verify_supabase_access_token("access-token")
    assert (exc.value.status_code, exc.value.detail["code"]) == (502, "auth_unavailable")


def test_malformed_supabase_url_is_rejected(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://not-secure.example")
    with pytest.raises(HTTPException) as exc:
        auth_supabase.verify_supabase_access_token("access-token")
    assert (exc.value.status_code, exc.value.detail["code"]) == (503, "cloud_configuration_invalid")


def test_missing_supabase_config_still_allows_legacy_google_compatibility(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    with patch("auth_google.verify_google", return_value={"sub": "google-sub", "email": "person@example.com", "name": "Person"}):
        ident = auth_supabase.verify_access_token("google-id-token")
    assert ident["provider"] == "google_legacy"
    assert ident["sub"] == "google-sub"

def test_invalid_supabase_token_falls_back_to_verified_legacy_google(monkeypatch):
    with patch.object(auth_supabase.requests, "get", return_value=Response(status=401, body={})):
        with patch("auth_google.verify_google", return_value={"sub": "legacy-google-sub", "email": "person@example.com", "name": "Person"}):
            ident = auth_supabase.verify_access_token("legacy-google-id-token")
    assert ident["provider"] == "google_legacy"
    assert ident["sub"] == "legacy-google-sub"


def test_library_owner_key_comes_from_verified_identity():
    import library
    with patch("auth_supabase.verify_access_token", return_value={"id": "verified-user-id", "provider": "supabase"}):
        with patch.object(library, "_resolve_library_owner", return_value="stable-owner-key"):
            assert library.current_user("Bearer valid-session") == "stable-owner-key"


def test_library_rejects_missing_or_oversized_bearer():
    import library
    for header in (None, "Basic token", "Bearer " + "x" * 9000):
        with pytest.raises(HTTPException) as exc:
            library.current_user(header)
        assert exc.value.status_code == 401

def test_admin_authorization_uses_verified_supabase_identity_and_database_role(monkeypatch):
    import admin
    verified = {"id": "a1e9a1c2-7d6f-4e3d-9b7a-2a3f4c5d6e7f", "sub": "google-sub", "email": "admin@example.com", "name": "Admin", "provider": "supabase"}
    with patch("auth_supabase.verify_access_token", return_value=verified) as verify:
        with patch.object(admin, "_rest", return_value=[{"email": "admin@example.com", "role": "admin"}]) as rest:
            result = admin.current_admin("Bearer supabase-session")
    assert result == {"email": "admin@example.com", "name": "Admin", "role": "admin"}
    verify.assert_called_once_with("supabase-session")
    assert rest.call_args.args[1] == "mf_admins"
    assert rest.call_args.args[2]["email"] == "eq.admin@example.com"


def test_admin_denies_verified_supabase_user_without_live_role(monkeypatch):
    import admin
    verified = {"id": "a1e9a1c2-7d6f-4e3d-9b7a-2a3f4c5d6e7f", "sub": "supabase-id", "email": "student@example.com", "name": "Student", "provider": "supabase"}
    with patch("auth_supabase.verify_access_token", return_value=verified):
        with patch.object(admin, "_rest", return_value=[]):
            with pytest.raises(HTTPException) as exc:
                admin.current_admin("Bearer supabase-session")
    assert (exc.value.status_code, exc.value.detail["code"]) == (403, "not_authorized")


def test_email_first_account_keeps_uuid_owner_after_google_identity_link(monkeypatch):
    import library
    user_id = "a1e9a1c2-7d6f-4e3d-9b7a-2a3f4c5d6e7f"
    account = {"user_id": user_id, "owner_key": user_id, "legacy_google_sub": None}
    calls = []
    def fake_db(method, table, params=None, json=None, prefer="return=representation"):
        calls.append((method, table, params, json, prefer))
        if table == "mf_auth_accounts" and method == "GET": return [account.copy()]
        if table == "mf_favorites" and method == "GET": return [{"song_id":"song-1","song":{"id":"song-1"},"added_at":"2026-01-01T00:00:00Z"}]
        if table == "mf_favorites" and method == "POST": return []
        if table == "mf_playlists" and method == "PATCH": return []
        if table == "mf_auth_accounts" and method == "PATCH":
            account.update(json)
            return []
        raise AssertionError((method, table, params, json))
    with patch.object(library, "_db", side_effect=fake_db):
        owner = library._resolve_library_owner({"id": user_id, "sub": user_id, "legacy_google_sub": "google-sub-123", "provider": "supabase"})
    assert owner == user_id
    assert account["legacy_google_sub"] == "google-sub-123"
    assert any(c[0] == "POST" and c[1] == "mf_favorites" for c in calls)
    assert not any(c[0] == "DELETE" and c[1] == "mf_favorites" for c in calls)
    assert any(c[0] == "PATCH" and c[1] == "mf_playlists" for c in calls)


def test_google_first_account_keeps_legacy_owner_key(monkeypatch):
    import library
    user_id = "a1e9a1c2-7d6f-4e3d-9b7a-2a3f4c5d6e7f"
    row = {"user_id": user_id, "owner_key": "google-sub-123", "legacy_google_sub": "google-sub-123"}
    calls = []
    def fake_db(method, table, params=None, json=None, prefer="return=representation"):
        calls.append((method, table, json))
        if table == "mf_auth_accounts" and method == "GET":
            return [] if sum(1 for c in calls if c[0] == "GET") == 1 else [row]
        if table == "mf_auth_accounts" and method == "POST": return []
        raise AssertionError((method, table))
    with patch.object(library, "_db", side_effect=fake_db):
        owner = library._resolve_library_owner({"id": user_id, "sub": user_id, "legacy_google_sub": "google-sub-123", "primary_provider": "google", "provider": "supabase"})
    assert owner == "google-sub-123"
    assert calls[1][2]["owner_key"] == "google-sub-123"


def test_legacy_google_token_keeps_existing_owner_without_mapping_table():
    import library
    with patch.object(library, "_db", side_effect=AssertionError("legacy flow must not query mapping table")):
        assert library._resolve_library_owner({"sub": "old-google-sub", "provider": "google_legacy"}) == "old-google-sub"


def test_email_first_account_initially_uses_supabase_uuid_owner(monkeypatch):
    import library
    user_id = "a1e9a1c2-7d6f-4e3d-9b7a-2a3f4c5d6e7f"
    row = {"user_id": user_id, "owner_key": user_id, "legacy_google_sub": None}
    calls = []
    def fake_db(method, table, params=None, json=None, prefer="return=representation"):
        calls.append((method, table, json))
        if table == "mf_auth_accounts" and method == "GET":
            return [] if sum(1 for c in calls if c[0] == "GET") == 1 else [row]
        if table == "mf_auth_accounts" and method == "POST": return []
        raise AssertionError((method, table))
    with patch.object(library, "_db", side_effect=fake_db):
        owner = library._resolve_library_owner({"id": user_id, "sub": user_id, "legacy_google_sub": None, "provider": "supabase"})
    assert owner == user_id
    assert calls[1][2]["owner_key"] == user_id


def test_legacy_favorites_are_not_deleted_if_copy_fails(monkeypatch):
    import library
    calls = []
    def fake_db(method, table, params=None, json=None, prefer="return=representation"):
        calls.append((method, table))
        if method == "GET" and table == "mf_favorites":
            return [{"song_id":"song-1","song":{"id":"song-1"},"added_at":"2026-01-01T00:00:00Z"}]
        if method == "POST" and table == "mf_favorites":
            raise HTTPException(status_code=502, detail={"code":"storage_failed"})
        raise AssertionError((method, table))
    with patch.object(library, "_db", side_effect=fake_db):
        with pytest.raises(HTTPException):
            library._merge_legacy_google_owner("legacy-google-sub", "stable-owner")
    assert ("DELETE", "mf_favorites") not in calls


def test_email_primary_with_google_already_linked_keeps_uuid_and_merges(monkeypatch):
    import library
    user_id = "a1e9a1c2-7d6f-4e3d-9b7a-2a3f4c5d6e7f"
    account = {"user_id": user_id, "owner_key": user_id, "legacy_google_sub": None}
    calls = []
    def fake_db(method, table, params=None, json=None, prefer="return=representation"):
        calls.append((method, table, params, json, prefer))
        if table == "mf_auth_accounts" and method == "GET": return [] if sum(1 for c in calls if c[0] == "GET") == 1 else [account.copy()]
        if table == "mf_auth_accounts" and method == "POST": account.update(json); return []
        if table == "mf_auth_accounts" and method == "PATCH": account.update(json); return []
        if table == "mf_favorites" and method == "GET": return [{"song_id":"song-1","song":{"id":"song-1"},"added_at":"2026-01-01T00:00:00Z"}]
        if table == "mf_favorites" and method == "POST": return []
        if table == "mf_playlists" and method == "PATCH": return []
        raise AssertionError((method, table, params, json))
    with patch.object(library, "_db", side_effect=fake_db):
        owner = library._resolve_library_owner({"id": user_id, "sub": user_id, "legacy_google_sub": "google-sub-123", "primary_provider": "email", "provider": "supabase"})
    assert owner == user_id
    assert account["legacy_google_sub"] == "google-sub-123"
    assert any(c[0] == "POST" and c[1] == "mf_favorites" for c in calls)
    assert not any(c[0] == "DELETE" and c[1] == "mf_favorites" for c in calls)


def test_legacy_favorites_are_copied_in_pages_without_deleting_source():
    import library
    calls = []
    page_one = [{"song_id": f"song-{i:03}", "song": {"id": f"song-{i:03}"}, "added_at": "2026-01-01T00:00:00Z"} for i in range(500)]
    page_two = [{"song_id": "song-500", "song": {"id": "song-500"}, "added_at": "2026-01-01T00:00:00Z"}]
    def fake_db(method, table, params=None, json=None, prefer="return=representation"):
        calls.append((method, table, params, json))
        if method == "GET" and table == "mf_favorites":
            return page_one if params["offset"] == 0 else page_two
        if method == "POST" and table == "mf_favorites": return []
        if method == "PATCH" and table == "mf_playlists": return []
        raise AssertionError((method, table, params))
    with patch.object(library, "_db", side_effect=fake_db):
        library._merge_legacy_google_owner("legacy-google-sub", "stable-owner")
    reads = [c for c in calls if c[0] == "GET" and c[1] == "mf_favorites"]
    writes = [c for c in calls if c[0] == "POST" and c[1] == "mf_favorites"]
    assert [c[2]["offset"] for c in reads] == [0, 500]
    assert [len(c[3]) for c in writes] == [500, 1]
    assert not any(c[0] == "DELETE" and c[1] == "mf_favorites" for c in calls)
