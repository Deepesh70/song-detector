import os
import io
import sys
from pathlib import Path
from typing import List, Tuple, Optional
from fastapi import FastAPI, Header, HTTPException, status, Request
from pydantic import BaseModel, Field
import httpx
import redis

# Built-in lightweight .env loader
def load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()

# Ensure project root in sys.path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Sanitize invalid or unreadable SSL_CERT_FILE from Git Bash / terminal environments
if "SSL_CERT_FILE" in os.environ:
    cert_path = os.environ["SSL_CERT_FILE"]
    if not cert_path or not os.path.exists(cert_path):
        del os.environ["SSL_CERT_FILE"]

import certifi

# Set SSL_CERT_FILE to certifi's valid bundle to prevent Windows/Git Bash SSL errors
os.environ["SSL_CERT_FILE"] = certifi.where()

from backend.db import DatabaseManager
from backend.matcher import evaluate_matches, QueryLRUCache
from backend.fallback import FallbackManager

app = FastAPI(title="Song Detector API", version="1.0.0")

# Database & Cache clients
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
AUDD_API_TOKEN = os.getenv("AUDD_API_TOKEN")
ACRCLOUD_HOST = os.getenv("ACRCLOUD_HOST")
ACRCLOUD_ACCESS_KEY = os.getenv("ACRCLOUD_ACCESS_KEY")
ACRCLOUD_ACCESS_SECRET = os.getenv("ACRCLOUD_ACCESS_SECRET")

def _init_redis():
    try:
        client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=1)
        client.ping()
        return client
    except Exception:
        import fakeredis
        return fakeredis.FakeStrictRedis(decode_responses=True)

redis_client = _init_redis()
fallback_manager = FallbackManager(redis_client=redis_client)
db_manager = DatabaseManager()
query_lru_cache = QueryLRUCache(capacity=1024)

MAX_QUERY_HASHES: int = 800


class QueryPayload(BaseModel):
    hashes: List[Tuple[int, int]] = Field(..., max_length=MAX_QUERY_HASHES)


class IngestPayload(BaseModel):
    title: str
    artist: str
    duration_seconds: int
    fingerprints: List[Tuple[int, int]]


@app.post("/v1/recognize", status_code=status.HTTP_200_OK)
def recognize(payload: QueryPayload):
    """Identify a track using client landmark hashes against PostgreSQL covering index."""
    if not payload.hashes:
        token = fallback_manager.create_fallback_token()
        return {"matched": False, "fallback_token": token}

    cache_key = tuple(sorted(h for h, _ in payload.hashes[:128]))
    cached_match = query_lru_cache.get(cache_key)
    if cached_match is not None:
        return cached_match

    unique_hashes = list({h for h, _ in payload.hashes})

    try:
        db_matches = db_manager.query_fingerprints(unique_hashes)
    except Exception:
        token = fallback_manager.create_fallback_token()
        return {"matched": False, "fallback_token": token}

    result = evaluate_matches(payload.hashes, db_matches)

    if not result.matched or not result.candidate:
        token = fallback_manager.create_fallback_token()
        return {"matched": False, "fallback_token": token}

    song_id = result.candidate.song_id
    track_meta = db_manager.get_track_metadata(song_id)
    offset_sec = (result.candidate.peak_offset_frame * 256) / 11025.0

    response_data = {
        "matched": True,
        "track": {
            "id": song_id,
            "title": track_meta["title"] if track_meta else "Unknown",
            "artist": track_meta["artist"] if track_meta else "Unknown",
            "duration_seconds": track_meta["duration_seconds"] if track_meta else 0,
            "offset_seconds": round(offset_sec, 2),
        },
        "confidence": {
            "peak_votes": result.candidate.peak_votes,
            "prominence_ratio": round(result.candidate.prominence_ratio, 2),
        },
        "duplicates": result.duplicate_song_ids,
    }
    query_lru_cache.put(cache_key, response_data)
    return response_data


def generate_acrcloud_signature(
    access_key: str,
    access_secret: str,
    timestamp: str,
    http_method: str = "POST",
    http_uri: str = "/v1/identify",
    data_type: str = "audio",
    signature_version: str = "1",
) -> str:
    """Generate HMAC-SHA1 signature for ACRCloud identification API."""
    import base64
    import hashlib
    import hmac

    string_to_sign = "\n".join([http_method, http_uri, access_key, data_type, signature_version, timestamp])
    digest = hmac.new(
        access_secret.encode("ascii"),
        string_to_sign.encode("ascii"),
        digestmod=hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


@app.post("/v1/recognize/fallback")
async def recognize_fallback(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Proxy audio buffer to commercial fallback provider (ACRCloud or AudD) with single-use token validation."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    token = authorization.split("Bearer ")[1].strip()
    is_valid = fallback_manager.verify_and_consume_token(token)

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or already consumed fallback token",
        )

    audio_bytes = await request.body()
    if len(audio_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty audio payload",
        )

    # 1. Check ACRCloud provider
    if ACRCLOUD_HOST and ACRCLOUD_ACCESS_KEY and ACRCLOUD_ACCESS_SECRET:
        try:
            import time
            timestamp = str(int(time.time()))
            sig = generate_acrcloud_signature(
                access_key=ACRCLOUD_ACCESS_KEY,
                access_secret=ACRCLOUD_ACCESS_SECRET,
                timestamp=timestamp,
            )
            data = {
                "access_key": ACRCLOUD_ACCESS_KEY,
                "sample_bytes": len(audio_bytes),
                "timestamp": timestamp,
                "signature": sig,
                "data_type": "audio",
                "signature_version": "1",
            }
            files = {
                "sample": ("query.wav", audio_bytes, "audio/wav"),
            }
            url = f"https://{ACRCLOUD_HOST}/v1/identify"
            async with httpx.AsyncClient(verify=certifi.where(), timeout=15.0) as client:
                resp = await client.post(url, data=data, files=files)
                res_data = resp.json()

                if res_data.get("status", {}).get("code") == 0:
                    music_list = res_data.get("metadata", {}).get("music", [])
                    if music_list:
                        m = music_list[0]
                        artists = ", ".join([a.get("name", "") for a in m.get("artists", [])])
                        album = m.get("album", {}).get("name")
                        spotify_id = m.get("external_metadata", {}).get("spotify", {}).get("track", {}).get("id")
                        song_link = f"https://open.spotify.com/track/{spotify_id}" if spotify_id else None
                        return {
                            "matched": True,
                            "provider": "acrcloud",
                            "track": {
                                "title": m.get("title"),
                                "artist": artists,
                                "album": album,
                                "release_date": m.get("release_date"),
                                "song_link": song_link,
                            },
                        }

                return {
                    "matched": False,
                    "provider": "acrcloud",
                    "detail": res_data.get("status", {}).get("msg", "No match in ACRCloud music database"),
                }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"ACRCloud provider request failed: {str(e)}",
            )

    # 2. Check AudD provider
    if AUDD_API_TOKEN:
        try:
            async with httpx.AsyncClient(verify=certifi.where(), timeout=15.0) as client:
                data = {
                    "api_token": AUDD_API_TOKEN,
                    "return": "apple_music,spotify",
                }
                files = {
                    "file": ("query.wav", audio_bytes, "audio/wav"),
                }
                resp = await client.post("https://api.audd.io/", data=data, files=files)
                res_data = resp.json()

                if res_data.get("status") == "success" and res_data.get("result"):
                    result = res_data["result"]
                    return {
                        "matched": True,
                        "provider": "audd",
                        "track": {
                            "title": result.get("title"),
                            "artist": result.get("artist"),
                            "album": result.get("album"),
                            "release_date": result.get("release_date"),
                            "song_link": result.get("song_link"),
                            "timecode": result.get("timecode"),
                        },
                    }
                else:
                    return {
                        "matched": False,
                        "provider": "audd",
                        "detail": res_data.get("error", {}).get("error_message", "No match in global music database"),
                    }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AudD recognition provider request failed: {str(e)}",
            )

    return {
        "matched": False,
        "provider": "none",
        "detail": "No commercial fallback provider credentials configured in .env",
    }


@app.post("/v1/catalog/ingest", status_code=status.HTTP_201_CREATED)
def ingest_song(payload: IngestPayload):
    """Ingest track metadata and landmark fingerprints into database."""
    try:
        song_id = db_manager.insert_track(
            title=payload.title,
            artist=payload.artist,
            duration_seconds=payload.duration_seconds,
            fingerprints=payload.fingerprints,
        )
        return {
            "song_id": song_id,
            "inserted_fingerprints": len(payload.fingerprints),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest track: {str(e)}",
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

