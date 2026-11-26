from datetime import datetime, timedelta, timezone

import library


def test_history_schema_and_future_time_are_bounded():
    listen = library.Listen(
        id="track-1",
        name="Example",
        artists=[{"id": "artist-1", "name": "Artist"}],
        image="https://example.test/cover.jpg",
        spotify="https://open.spotify.com/track/track-1",
        at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    row = library._listen_row("owner-key", listen)
    parsed = datetime.fromisoformat(row["listened_at"])
    assert row["user_sub"] == "owner-key"
    assert row["song_id"] == "track-1"
    assert parsed <= datetime.now(timezone.utc) + timedelta(seconds=2)
    assert row["song"]["artists"] == [{"id": "artist-1", "name": "Artist"}]


def test_list_history_clamps_limit_and_shapes_rows(monkeypatch):
    calls = []

    def fake_db(method, table, params=None, json=None, prefer="return=representation"):
        calls.append((method, table, params, json, prefer))
        return [{
            "song_id": "track-1",
            "song": {"name": "Example", "artists": [{"name": "Artist"}], "image": "cover", "spotify": "url"},
            "listened_at": "2026-01-01T00:00:00+00:00",
        }]

    monkeypatch.setattr(library, "_db", fake_db)
    result = library.list_history(limit=99999, user="owner-key")
    assert calls[0][2]["limit"] == library.MAX_HISTORY
    assert result["history"][0] == {
        "id": "track-1", "name": "Example", "artists": [{"name": "Artist"}],
        "image": "cover", "spotify": "url", "at": "2026-01-01T00:00:00+00:00",
    }


def test_add_listen_deduplicates_same_track_within_sixty_seconds(monkeypatch):
    now = datetime.now(timezone.utc)
    calls = []

    def fake_db(method, table, params=None, json=None, prefer="return=representation"):
        calls.append((method, table, params, json, prefer))
        return [{"song_id": "track-1", "listened_at": now.isoformat()}] if method == "GET" else []

    monkeypatch.setattr(library, "_db", fake_db)
    listen = library.Listen(id="track-1", at=(now + timedelta(seconds=20)).isoformat())
    assert library.add_listen(listen, user="owner-key") == {"ok": True, "duplicate": True}
    assert not any(call[0] == "POST" for call in calls)


def test_merge_history_is_additive_and_user_scoped(monkeypatch):
    calls = []

    def fake_db(method, table, params=None, json=None, prefer="return=representation"):
        calls.append((method, table, params, json, prefer))
        return []

    monkeypatch.setattr(library, "_db", fake_db)
    body = library.HistoryMerge(history=[library.Listen(id="track-1", name="Example")])
    result = library.merge_history(body, user="owner-key")
    post = next(call for call in calls if call[0] == "POST")
    assert result == {"ok": True, "received": 1}
    assert post[1] == "mf_listens"
    assert post[3][0]["user_sub"] == "owner-key"
    assert post[4] == "resolution=ignore-duplicates,return=minimal"


def test_clear_history_never_deletes_favorites_or_playlists(monkeypatch):
    calls = []

    def fake_db(method, table, params=None, json=None, prefer="return=representation"):
        calls.append((method, table, params, json, prefer))
        return []

    monkeypatch.setattr(library, "_db", fake_db)
    assert library.clear_history(user="owner-key") == {"ok": True}
    assert calls == [("DELETE", "mf_listens", {"user_sub": "eq.owner-key"}, None, "return=minimal")]


def test_taste_aggregates_tracks_and_artists(monkeypatch):
    rows = [
        {"song_id": "track-1", "song": {"name": "Song", "artists": [{"id": "artist-1", "name": "Artist"}], "image": "cover", "spotify": "url"}, "listened_at": "2026-01-02T00:00:00+00:00"},
        {"song_id": "track-1", "song": {"name": "Song", "artists": [{"id": "artist-1", "name": "Artist"}], "image": "cover", "spotify": "url"}, "listened_at": "2026-01-01T00:00:00+00:00"},
        {"song_id": "track-2", "song": {"name": "Other", "artists": [{"id": "artist-1", "name": "Artist"}], "image": "cover-2", "spotify": "url-2"}, "listened_at": "2025-12-31T00:00:00+00:00"},
    ]
    monkeypatch.setattr(library, "_db", lambda *args, **kwargs: rows)
    result = library.taste(limit=10, user="owner-key")
    assert result["total"] == 3
    assert result["last_played"] == rows[0]["listened_at"]
    assert result["tracks"][0]["id"] == "track-1"
    assert result["tracks"][0]["n"] == 2
    assert result["artists"][0]["n"] == 3
