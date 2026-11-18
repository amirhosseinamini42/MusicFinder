"""Lyrics search stays visible but is safely disabled until provider credentials are replaced."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(monkeypatch):
    main._lyrics_cache.clear()
    main._lyrics_hits.clear()
    return TestClient(main.app)


def code(response):
    return response.json()["detail"]["code"]


def test_lyrics_search_returns_temporary_503_without_any_provider_requests(client, monkeypatch):
    # Even stale credentials must not reactivate AudD or Musixmatch.
    monkeypatch.setenv("AUDD_API_TOKEN", "stale-test-token")
    monkeypatch.setenv("AUDD_API_KEY", "stale-alias-token")
    monkeypatch.setenv("MUSIXMATCH_API_KEY", "test-musixmatch-key")
    monkeypatch.setattr(main.requests, "get", lambda *a, **k: pytest.fail("No outbound GET is allowed"))
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: pytest.fail("No outbound POST is allowed"))

    response = client.get("/lyrics/search", params={"q": "example lyric line"})

    assert response.status_code == 503
    assert code(response) == "lyrics_temporarily_disabled"
    assert "temporarily" in response.text


def test_disabled_state_takes_precedence_over_stale_cache(client, monkeypatch):
    main._lyrics_cache["example lyric line"] = (float("inf"), {
        "query": "example lyric line", "results": [{"id": "stale"}],
        "unresolved": [], "lookup_errors": 0, "source": "audd",
    })
    monkeypatch.setattr(main.requests, "get", lambda *a, **k: pytest.fail("No outbound GET is allowed"))
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: pytest.fail("No outbound POST is allowed"))

    response = client.get("/lyrics/search", params={"q": "example lyric line"})

    assert response.status_code == 503
    assert code(response) == "lyrics_temporarily_disabled"


def test_short_query_validation_remains_active(client):
    response = client.get("/lyrics/search", params={"q": "hi"})
    assert response.status_code == 400
    assert code(response) == "query_too_short"


def test_frontend_keeps_lyrics_mode_and_displays_disabled_message():
    source = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'data-mode="lyrics"' in source
    assert "${API_BASE}/lyrics/search?q=${encodeURIComponent(query)}" in source
    assert "lyrics_temporarily_disabled" in source


def test_backend_no_longer_contains_audd_credential_or_request_code():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "AUDD_API_TOKEN" not in source
    assert "AUDD_API_KEY" not in source
    assert "api.audd.io" not in source
    assert "lyrics_temporarily_disabled" in source
