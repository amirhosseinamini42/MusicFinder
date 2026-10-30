from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from urllib.parse import quote
import os
import requests
import base64
import re
import time
import unicodedata
from collections import deque
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

from library import router as library_router

from admin import admin_router, public_router

app = FastAPI(title="MusicFinder API")


# =========================
# CORS
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
app.include_router(public_router)
app.include_router(library_router)

# =========================
# SPOTIFY CONFIG
# =========================

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")


def get_access_token():

    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Spotify credentials are missing."
        )

    auth_string = f"{CLIENT_ID}:{CLIENT_SECRET}"

    auth_bytes = auth_string.encode("utf-8")

    auth_base64 = base64.b64encode(
        auth_bytes
    ).decode("utf-8")

    try:

        response = requests.post(
            "https://accounts.spotify.com/api/token",
            headers={
                "Authorization": f"Basic {auth_base64}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials"
            },
            timeout=20,
        )

        response.raise_for_status()

        return response.json()["access_token"]

    except requests.RequestException as error:

        print("Spotify authentication error:", error)

        raise HTTPException(
            status_code=502,
            detail="Could not authenticate with Spotify."
        )


# =========================
# ROOT
# =========================

@app.get("/")
def root():

    return {
        "message": "MusicFinder API is running.",
        "status": "online"
    }


# =========================
# TEST
# =========================

@app.get("/test")
def test():

    return {
        "message": "MusicFinder backend is working!"
    }


@app.get("/config/supabase")
def supabase_config():
    url = os.getenv("SUPABASE_URL")
    publishable_key = os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

    if not url or not publishable_key:
        raise HTTPException(status_code=503, detail="Supabase is not configured.")

    return {"url": url, "publishableKey": publishable_key}

# =========================
# JAMENDO TEST / SEARCH
# =========================

JAMENDO_CLIENT_ID = os.getenv(
    "JAMENDO_CLIENT_ID",
    "709fa152"
)


@app.get("/jamendo/search")
def jamendo_search(q: str):

    query = q.strip()

    if not query:
        return {
            "results": []
        }

    response = requests.get(
        "https://api.jamendo.com/v3.0/tracks/",
        params={
            "client_id": JAMENDO_CLIENT_ID,
            "format": "json",
            "limit": 5,
            "namesearch": query,
            "audioformat": "mp32"
        },
        timeout=15
    )

    response.raise_for_status()

    return response.json()

# =========================
# SEARCH
# =========================

@app.get("/search")
def search_music(q: str):

    if not q.strip():

        raise HTTPException(
            status_code=400,
            detail="Search query cannot be empty."
        )

    token = get_access_token()

    try:

        response = requests.get(
            "https://api.spotify.com/v1/search",
            headers={
                "Authorization": f"Bearer {token}"
            },
            params={
                "q": q,
                "type": "track,artist,album",
                "limit": 10,
            },
            timeout=20,
        )

        response.raise_for_status()

        return response.json()

    except requests.RequestException as error:

        print("Spotify search error:", error)

        raise HTTPException(
            status_code=502,
            detail="Spotify search failed."
        )


# =========================
# LYRICS SEARCH
# =========================
#
# Finds songs from a fragment of their lyrics. Spotify cannot search lyric text, so
# the lyric lookup uses the Musixmatch API (free developer plan, API key required).
# Only song metadata (title / artist) is read from Musixmatch - no lyric text is
# requested, stored or returned. Each match is then resolved to a real Spotify track
# so results work with the existing cards and player.
#
# Env (server side only, never sent to the browser). Use ONE of them:
#   AUDD_API_TOKEN      - AudD findLyrics (used first when set)
#   MUSIXMATCH_API_KEY  - Musixmatch track.search

MUSIXMATCH_BASE = "https://api.musixmatch.com/ws/1.1"
LYRICS_MIN_CHARS = 3
LYRICS_MAX_CHARS = 200
LYRICS_MAX_MATCHES = 10
LYRICS_CACHE_SECONDS = 600
LYRICS_RATE_LIMIT = 15          # requests per IP per minute (best effort, per server instance)

_lyrics_cache = {}
_lyrics_hits = {}


def _api_error(status, code):

    return HTTPException(
        status_code=status,
        detail={"code": code}
    )


def _normalize(text):

    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\(.*?\)|\[.*?\]", " ", text)
    text = re.sub(r"\s-\s.*$", " ", text)
    text = re.sub(r"[^\w\s]", " ", text.lower())

    return re.sub(r"\s+", " ", text).strip()


def _lyrics_rate_ok(client_ip):

    now = time.time()

    if len(_lyrics_hits) > 2000:
        _lyrics_hits.clear()

    hits = _lyrics_hits.setdefault(client_ip, deque())

    while hits and hits[0] < now - 60:
        hits.popleft()

    if len(hits) >= LYRICS_RATE_LIMIT:
        return False

    hits.append(now)

    return True


def _musixmatch_search(query):

    api_key = os.getenv("MUSIXMATCH_API_KEY")

    if not api_key:
        raise _api_error(503, "lyrics_not_configured")

    try:

        response = requests.get(
            f"{MUSIXMATCH_BASE}/track.search",
            params={
                "q_lyrics": query,
                "f_has_lyrics": 1,
                "s_track_rating": "desc",
                "page": 1,
                "page_size": LYRICS_MAX_MATCHES,
                "apikey": api_key,
            },
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

    except (requests.RequestException, ValueError) as error:

        # Never log the exception text: requests includes the full URL (and API key).
        print("Musixmatch request failed:", type(error).__name__)

        raise _api_error(502, "lyrics_unavailable")

    message = data.get("message") or {}

    status = (message.get("header") or {}).get("status_code")

    if status == 402:
        raise _api_error(429, "lyrics_limit_reached")

    if status == 404:
        return []

    if status != 200:

        print("Musixmatch returned status:", status)

        raise _api_error(502, "lyrics_unavailable")

    body = message.get("body")

    track_list = body.get("track_list", []) if isinstance(body, dict) else []

    matches = []
    seen = set()

    for item in track_list:

        track = (item or {}).get("track") or {}

        name = (track.get("track_name") or "").strip()
        artist = (track.get("artist_name") or "").strip()

        key = (_normalize(name), _normalize(artist))

        if not name or not artist or key in seen:
            continue

        seen.add(key)

        matches.append({"name": name, "artist": artist})

    return matches


def _audd_search(query):
    """AudD findLyrics. Only artist/title are read - the lyric text AudD returns is discarded."""

    token = os.getenv("AUDD_API_TOKEN")

    try:

        # Token travels in the POST body, never in the URL (so it cannot appear in error text).
        response = requests.post(
            "https://api.audd.io/findLyrics/",
            data={
                "api_token": token,
                "q": query,
            },
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

    except (requests.RequestException, ValueError) as error:

        print("AudD request failed:", type(error).__name__)

        raise _api_error(502, "lyrics_unavailable")

    if data.get("status") != "success":

        error_info = data.get("error") or {}

        code = error_info.get("error_code")

        print("AudD returned error code:", code)

        if code == 901:
            raise _api_error(429, "lyrics_limit_reached")

        raise _api_error(502, "lyrics_unavailable")

    result = data.get("result")

    matches = []
    seen = set()

    for item in (result if isinstance(result, list) else []):

        name = ((item or {}).get("title") or "").strip()
        artist = ((item or {}).get("artist") or "").strip()

        key = (_normalize(name), _normalize(artist))

        if not name or not artist or key in seen:
            continue

        seen.add(key)

        matches.append({"name": name, "artist": artist})

        if len(matches) >= LYRICS_MAX_MATCHES:
            break

    return matches


def _find_lyrics_matches(query):

    if os.getenv("AUDD_API_TOKEN"):
        return _audd_search(query), "audd"

    return _musixmatch_search(query), "musixmatch"


def _spotify_lookup(token, name, artist):
    """Returns (track_or_None, lookup_failed)."""

    try:

        response = requests.get(
            "https://api.spotify.com/v1/search",
            headers={
                "Authorization": f"Bearer {token}"
            },
            params={
                "q": f'track:"{name.replace(chr(34), " ")}" artist:"{artist.replace(chr(34), " ")}"',
                "type": "track",
                "limit": 5,
            },
            timeout=10,
        )

        response.raise_for_status()

        items = response.json().get("tracks", {}).get("items", [])

    except (requests.RequestException, ValueError):

        return None, True

    wanted_title = _normalize(name)
    wanted_artist = _normalize(artist)

    for item in items:

        title = _normalize(item.get("name"))

        artists = [
            _normalize(a.get("name"))
            for a in item.get("artists", [])
        ]

        title_ok = bool(title and wanted_title) and (
            title == wanted_title
            or title in wanted_title
            or wanted_title in title
        )

        artist_ok = any(
            a and wanted_artist and (
                a == wanted_artist
                or a in wanted_artist
                or wanted_artist in a
            )
            for a in artists
        )

        if title_ok and artist_ok:
            return item, False

    return None, False


@app.get("/lyrics/search")
def search_by_lyrics(q: str, request: Request):

    query = re.sub(r"\s+", " ", q or "").strip()

    if len(query) < LYRICS_MIN_CHARS:
        raise _api_error(400, "query_too_short")

    if len(query) > LYRICS_MAX_CHARS:
        raise _api_error(400, "query_too_long")

    cache_key = query.lower()

    cached = _lyrics_cache.get(cache_key)

    if cached and cached[0] > time.time():
        return cached[1]

    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()

    client_ip = forwarded or (request.client.host if request.client else "unknown")

    if not _lyrics_rate_ok(client_ip):
        raise _api_error(429, "rate_limited")

    matches, source = _find_lyrics_matches(query)

    results = []
    unresolved = []
    lookup_errors = 0

    if matches:

        token = get_access_token()

        with ThreadPoolExecutor(max_workers=5) as pool:

            outcomes = list(
                pool.map(
                    lambda m: _spotify_lookup(token, m["name"], m["artist"]),
                    matches
                )
            )

        seen_ids = set()

        for match, (track, failed) in zip(matches, outcomes):

            if failed:
                lookup_errors += 1
                continue

            if track is None:
                unresolved.append(match)
                continue

            if track.get("id") in seen_ids:
                continue

            seen_ids.add(track.get("id"))

            results.append(track)

    payload = {
        "query": query,
        "results": results,
        "unresolved": unresolved,
        "lookup_errors": lookup_errors,
        "source": source,
    }

    if lookup_errors == 0:

        if len(_lyrics_cache) > 200:
            _lyrics_cache.clear()

        _lyrics_cache[cache_key] = (time.time() + LYRICS_CACHE_SECONDS, payload)

    return payload


# =========================
# ARTIST
# =========================

@app.get("/artist/{artist_id}")
def get_artist(artist_id: str):

    token = get_access_token()

    try:

        response = requests.get(
            f"https://api.spotify.com/v1/artists/{artist_id}",
            headers={
                "Authorization": f"Bearer {token}"
            },
            timeout=20,
        )

        response.raise_for_status()

        data = response.json()

        images = data.get("images", [])

        return {
            "id": data.get("id"),
            "name": data.get("name"),
            "genres": data.get("genres", []),
            "image": (
                images[0].get("url")
                if images
                else None
            ),
            "spotify_url": (
                data.get(
                    "external_urls",
                    {}
                ).get("spotify")
            ),
        }

    except requests.RequestException as error:

        print("Spotify artist error:", error)

        raise HTTPException(
            status_code=502,
            detail="Could not load artist."
        )


# =========================
# ARTIST ALBUMS
# =========================

@app.get("/artist/{artist_id}/albums")
def get_artist_albums(artist_id: str):

    token = get_access_token()

    try:

        response = requests.get(
            f"https://api.spotify.com/v1/artists/{artist_id}/albums",
            headers={
                "Authorization": f"Bearer {token}"
            },
            params={
                "include_groups": "album,single,compilation",
                "limit": 20,
            },
            timeout=20,
        )

        response.raise_for_status()

        return response.json()

    except requests.RequestException as error:

        print("Spotify albums error:", error)

        raise HTTPException(
            status_code=502,
            detail="Could not load artist albums."
        )


# =========================
# ALBUM
# =========================

@app.get("/album/{album_id}")
def get_album(album_id: str):

    if not album_id.isalnum() or len(album_id) > 40:

        raise HTTPException(
            status_code=400,
            detail="Invalid album id."
        )

    token = get_access_token()

    try:

        response = requests.get(
            f"https://api.spotify.com/v1/albums/{album_id}",
            headers={
                "Authorization": f"Bearer {token}"
            },
            timeout=20,
        )

        if response.status_code == 404:

            raise HTTPException(
                status_code=404,
                detail="Album not found."
            )

        response.raise_for_status()

        data = response.json()

    except requests.RequestException as error:

        print("Spotify album error:", error)

        raise HTTPException(
            status_code=502,
            detail="Could not load album."
        )

    album_info = {
        "id": data.get("id"),
        "name": data.get("name"),
        "images": data.get("images", []),
        "external_urls": data.get("external_urls", {}),
        "release_date": data.get("release_date"),
    }

    # The frontend expects a flat array of tracks that carry album artwork,
    # so the player can show the cover for each album track.
    tracks = [
        {**track, "album": album_info}
        for track in (data.get("tracks") or {}).get("items", [])
    ]

    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "album_type": data.get("album_type"),
        "release_date": data.get("release_date"),
        "images": data.get("images", []),
        "artists": data.get("artists", []),
        "external_urls": data.get("external_urls", {}),
        "tracks": tracks,
    }


# =========================
# ARTIST BIO
# =========================

@app.get("/artist-bio")
def get_artist_bio(name: str):

    wikipedia_url = (
        "https://en.wikipedia.org/api/rest_v1/page/summary/"
        + quote(name.replace(" ", "_"))
    )

    try:

        response = requests.get(
            wikipedia_url,
            headers={
                "User-Agent": "MusicFinder/1.0"
            },
            timeout=10,
        )

        if response.status_code == 200:

            data = response.json()

            return {
                "title": data.get("title"),
                "description": data.get("description"),
                "extract": data.get("extract"),
                "thumbnail": (
                    data.get(
                        "thumbnail",
                        {}
                    ).get("source")
                ),
                "url": (
                    data.get(
                        "content_urls",
                        {}
                    )
                    .get(
                        "desktop",
                        {}
                    )
                    .get("page")
                ),
            }

    except requests.RequestException as error:

        print("Wikipedia error:", error)

    return {
        "title": name,
        "description": "",
        "extract": "",
        "thumbnail": None,
        "url": None,
    }