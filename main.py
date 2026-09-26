from fastapi import FastAPI
from fastapi.responses import FileResponse
from dotenv import load_dotenv
import os
import requests
import base64

load_dotenv()

app = FastAPI()

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")


def get_access_token():
    auth_string = f"{CLIENT_ID}:{CLIENT_SECRET}"
    auth_bytes = auth_string.encode("utf-8")
    auth_base64 = base64.b64encode(auth_bytes).decode("utf-8")

    response = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={
            "Authorization": f"Basic {auth_base64}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "client_credentials"
        },
    )

    response.raise_for_status()

    return response.json()["access_token"]


@app.get("/")
def home():
    return FileResponse("index.html")


@app.get("/test")
def test():
    return {"message": "MusicFinder backend is working!"}


@app.get("/search")
def search_music(q: str):
    token = get_access_token()

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
    )

    response.raise_for_status()

    return response.json()