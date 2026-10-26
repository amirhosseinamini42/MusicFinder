from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from urllib.parse import quote
import os
import requests
import base64
import re
import time

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


app.include_router(library_router)

# =========================
# SPOTIFY CONFIG
# =========================

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

_spotify_token = {"value": None, "expires": 0.0}      # reuse the token instead of fetching one per request
_SPOTIFY_ID = re.compile(r"^[A-Za-z0-9]{1,40}$")


def _upstream_error(error, message):
    """Friendly, safe error for a failed upstream call (never leaks raw exceptions)."""
    status = getattr(getattr(error, "response", None), "status_code", None)
    if status == 429:
        return HTTPException(status_code=429, detail="Spotify is busy right now. Please try again in a moment.")
    return HTTPException(status_code=502, detail=message)


def get_access_token():

    if _spotify_token["value"] and _spotify_token["expires"] > time.time():
        return _spotify_token["value"]

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

    try:

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

        raise _upstream_error(error, "Spotify search failed.")


# =========================
# ARTIST
# =========================

@app.get("/artist/{artist_id}")
def get_artist(artist_id: str):

    if not _SPOTIFY_ID.match(artist_id):
        raise HTTPException(status_code=400, detail="Invalid artist id.")


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

        raise _upstream_error(error, "Could not load artist.")


# =========================
# ARTIST ALBUMS
# =========================

@app.get("/artist/{artist_id}/albums")
def get_artist_albums(artist_id: str):

    if not _SPOTIFY_ID.match(artist_id):
        raise HTTPException(status_code=400, detail="Invalid artist id.")


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

        raise _upstream_error(error, "Could not load artist albums.")


# =========================
# ARTIST BIO
# =========================

@app.get("/artist-bio")
def get_artist_bio(name: str):

    wikipedia_url = (
        "https://en.wikipedia.org/api/rest_v1/page/summary/"
        + quote(name.strip()[:200].replace(" ", "_"))
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