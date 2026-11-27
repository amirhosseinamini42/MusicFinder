from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    return TestClient(main.app)


def audius_track(**overrides):
    track = {
        "id": "track123",
        "title": "Blinding Lights",
        "duration": 200,
        "is_streamable": True,
        "is_stream_gated": False,
        "play_count": 1200,
        "user": {"name": "The Weeknd"},
        "artwork": {"480x480": "https://images.example/cover.jpg"},
    }
    track.update(overrides)
    return track


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise main.requests.HTTPError("Audius request failed")


def test_audius_search_requires_server_side_api_key(client, monkeypatch):
    monkeypatch.delenv("AUDIUS_API_KEY", raising=False)
    monkeypatch.setattr(main.requests, "get", lambda *args, **kwargs: pytest.fail("No request without key"))

    response = client.get("/audius/search", params={
        "title": "Blinding Lights", "artist": "The Weeknd", "duration_ms": 200000
    })

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "audius_not_configured"}}


def test_audius_search_uses_api_key_header_and_returns_exact_stream_match(client, monkeypatch):
    monkeypatch.setenv("AUDIUS_API_KEY", "test-key-never-return-this")
    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append((url, headers, params, timeout))
        return FakeResponse({"data": [audius_track()]})

    monkeypatch.setattr(main.requests, "get", fake_get)
    response = client.get("/audius/search", params={
        "title": "Blinding Lights", "artist": "The Weeknd", "duration_ms": 200000
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "audius"
    assert payload["track"]["id"] == "track123"
    assert payload["track"]["stream_url"].endswith("/tracks/track123/stream")
    assert payload["track"]["artwork"] == "https://images.example/cover.jpg"
    assert calls[0][1] == {"x-api-key": "test-key-never-return-this"}
    assert calls[0][2]["query"] == "Blinding Lights The Weeknd"
    assert "test-key-never-return-this" not in response.text


@pytest.mark.parametrize("candidate", [
    audius_track(title="Blinding Lights (Live)"),
    audius_track(user={"name": "Another Artist"}),
    audius_track(duration=230),
    audius_track(is_streamable=False),
    audius_track(is_stream_gated=True),
])
def test_audius_search_rejects_ambiguous_or_unplayable_versions(client, monkeypatch, candidate):
    monkeypatch.setenv("AUDIUS_API_KEY", "test-key")
    monkeypatch.setattr(main.requests, "get", lambda *args, **kwargs: FakeResponse({"data": [candidate]}))

    response = client.get("/audius/search", params={
        "title": "Blinding Lights", "artist": "The Weeknd", "duration_ms": 200000
    })

    assert response.status_code == 200
    assert response.json()["track"] is None


def test_audius_search_returns_safe_error_when_provider_is_unavailable(client, monkeypatch):
    monkeypatch.setenv("AUDIUS_API_KEY", "test-key")

    def fail_request(*args, **kwargs):
        raise main.requests.Timeout("private request details")

    monkeypatch.setattr(main.requests, "get", fail_request)
    response = client.get("/audius/search", params={
        "title": "Blinding Lights", "artist": "The Weeknd"
    })

    assert response.status_code == 502
    assert response.json() == {"detail": {"code": "audius_unavailable"}}
    assert "private request details" not in response.text


def test_audius_search_validates_track_metadata(client):
    response = client.get("/audius/search", params={"title": "", "artist": "The Weeknd"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_track_metadata"


def test_frontend_uses_audius_first_and_keeps_spotify_queue_fallback():
    source = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "findAudiusTrack(song)" in source
    assert 'currentPlaybackProvider = "audius"' in source
    assert "showSpotifyFallback(song)" in source
    assert 'musicPlayer.classList.remove("mode-full")' in source
    assert "playQueueRelative(-1)" in source
    assert "playQueueRelative(1)" in source
    assert "AUDIUS_API_KEY" not in source
    assert '"x-api-key"' not in source
