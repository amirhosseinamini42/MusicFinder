from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from dotenv import load_dotenv
from urllib.parse import quote
import os
import requests
import base64
import re
import time
import threading

load_dotenv()

from library import router as library_router

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


app.add_middleware(GZipMiddleware, minimum_size=800)   # JSON search/library payloads compress well

app.include_router(library_router)

# =========================
# SPOTIFY CONFIG
# =========================

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

_spotify_token = {"value": None, "expires": 0.0}      # reuse the token instead of fetching one per request
_SPOTIFY_ID = re.compile(r"^[A-Za-z0-9]{1,40}$")


# =========================
# PERFORMANCE HELPERS
# =========================
# One pooled HTTP session: reuses TCP/TLS connections to Spotify/Jamendo/Wikipedia
# instead of a fresh handshake per request.
_http = requests.Session()
_http.headers.update({"Accept-Encoding": "gzip, deflate"})

# Small in-memory TTL cache for PUBLIC provider data only (search, artist, albums, bio).
# Never used for user-specific data or anything containing secrets.
_cache = {}
_cache_lock = threading.Lock()
_CACHE_MAX = 500


def _cache_get(key):
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > time.time():
            return hit[1]
        if hit:
            _cache.pop(key, None)
    return None


def _cache_set(key, value, ttl):
    with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            now = time.time()
            for k in [k for k, v in _cache.items() if v[0] <= now]:
                _cache.pop(k, None)
            if len(_cache) >= _CACHE_MAX:
                _cache.clear()
        _cache[key] = (time.time() + ttl, value)
    return value


_token_lock = threading.Lock()


def _upstream_error(error, message):
    """Friendly, safe error for a failed upstream call (never leaks raw exceptions)."""
    status = getattr(getattr(error, "response", None), "status_code", None)
    if status == 429:
        return HTTPException(status_code=429, detail="Spotify is busy right now. Please try again in a moment.")
    return HTTPException(status_code=502, detail=message)


def get_access_token():

    if _spotify_token["value"] and _spotify_token["expires"] > time.time():
        return _spotify_token["value"]

    with _token_lock:
        # another request may have refreshed the token while we waited
        if _spotify_token["value"] and _spotify_token["expires"] > time.time():
            return _spotify_token["value"]
        return _fetch_access_token()


def _fetch_access_token():

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

        response = _http.post(
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

        data = response.json()

        _spotify_token["value"] = data["access_token"]
        _spotify_token["expires"] = time.time() + max(60, int(data.get("expires_in", 3600)) - 120)

        return _spotify_token["value"]

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

JAMENDO_CLIENT_ID = os.getenv("JAMENDO_CLIENT_ID")


@app.get("/jamendo/search")
def jamendo_search(q: str):

    query = q.strip()

    if not query:
        return {
            "results": []
        }

    if len(query) > 200:
        raise HTTPException(status_code=400, detail="Search query is too long.")

    if not JAMENDO_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Jamendo is not configured.")

    ckey = ("jamendo", query.lower())
    cached = _cache_get(ckey)
    if cached is not None:
        return cached

    try:

        response = _http.get(
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

        return _cache_set(ckey, response.json(), 300)

    except (requests.RequestException, ValueError) as error:

        print("Jamendo error:", error)

        raise _upstream_error(error, "Jamendo search failed.")

# =========================
# SEARCH
# =========================

@app.get("/search")
def search_music(q: str):

    if len(q) > 200:
        raise HTTPException(status_code=400, detail="Search query is too long.")

    if not q.strip():

        raise HTTPException(
            status_code=400,
            detail="Search query cannot be empty."
        )

    ckey = ("search", q.strip().lower())
    cached = _cache_get(ckey)
    if cached is not None:
        return cached

    token = get_access_token()

    try:

        response = _http.get(
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

        return _cache_set(ckey, response.json(), 300)

    except requests.RequestException as error:

        print("Spotify search error:", error)

        raise _upstream_error(error, "Spotify search failed.")


# =========================
# ARTIST
# =========================

@app.get("/artist/{artist_id}")
def get_artist(artist_id: str):

    if not _SPOTIFY_ID.match(artist_id):
        raise HTTPException(status_code=400, detail="Invalid artist id.")

    ckey = ("artist", artist_id)
    cached = _cache_get(ckey)
    if cached is not None:
        return cached

    token = get_access_token()

    try:

        response = _http.get(
            f"https://api.spotify.com/v1/artists/{artist_id}",
            headers={
                "Authorization": f"Bearer {token}"
            },
            timeout=20,
        )

        response.raise_for_status()

        data = response.json()

        images = data.get("images", [])

        return _cache_set(ckey, {
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
        }, 3600)

    except requests.RequestException as error:

        print("Spotify artist error:", error)

        raise _upstream_error(error, "Could not load artist.")


# =========================
# ARTIST ALBUMS
# =========================

@app.get("/artist/{artist_id}/albums")
def get_artist_albums(artist_id: str):

    if not _SPOTIFY_ID.match(artist_id):
        raise HTTPException(status_code=400, detail="Invalid artist id.")

    ckey = ("albums", artist_id)
    cached = _cache_get(ckey)
    if cached is not None:
        return cached

    token = get_access_token()

    try:

        response = _http.get(
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

        return _cache_set(ckey, response.json(), 1800)

    except requests.RequestException as error:

        print("Spotify albums error:", error)

        raise _upstream_error(error, "Could not load artist albums.")


# =========================
# ARTIST BIO
# =========================

@app.get("/artist-bio")
def get_artist_bio(name: str):

    ckey = ("bio", name.strip()[:200].lower())
    cached = _cache_get(ckey)
    if cached is not None:
        return cached

    wikipedia_url = (
        "https://en.wikipedia.org/api/rest_v1/page/summary/"
        + quote(name.strip()[:200].replace(" ", "_"))
    )

    try:

        response = _http.get(
            wikipedia_url,
            headers={
                "User-Agent": "MusicFinder/1.0"
            },
            timeout=10,
        )

        if response.status_code == 200:

            data = response.json()

            return _cache_set(ckey, {
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
            }, 21600)

    except requests.RequestException as error:

        print("Wikipedia error:", error)

    return {
        "title": name,
        "description": "",
        "extract": "",
        "thumbnail": None,
        "url": None,
    }