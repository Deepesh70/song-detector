import base64
import hashlib
import hmac
import io
import threading
import time
from typing import Any, Dict, Optional, Tuple
import httpx
import soundfile as sf
import numpy as np

from client.preprocessor import SAMPLE_RATE_CANONICAL

_client_lock = threading.Lock()
_shared_client: Optional[httpx.Client] = None


def get_shared_client() -> httpx.Client:
    """Return a thread-safe persistent HTTP client with connection pooling and keep-alive."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        with _client_lock:
            if _shared_client is None or _shared_client.is_closed:
                _shared_client = httpx.Client(
                    timeout=httpx.Timeout(12.0, connect=5.0),
                    limits=httpx.Limits(
                        max_keepalive_connections=5,
                        max_connections=10,
                        keepalive_expiry=30.0,
                    ),
                )
    return _shared_client


def pcm_to_wav_bytes(pcm_buffer: np.ndarray, sample_rate: int = SAMPLE_RATE_CANONICAL) -> bytes:
    """Convert float32 mono PCM numpy array to in-memory WAV byte stream."""
    wav_bio = io.BytesIO()
    sf.write(wav_bio, pcm_buffer, sample_rate, format="WAV", subtype="PCM_16")
    return wav_bio.getvalue()


def recognize_audd_direct(
    audio_wav_bytes: bytes,
    api_token: str,
    timeout: float = 12.0,
) -> Dict[str, Any]:
    """Query AudD API directly using user-provided API token."""
    if not api_token.strip():
        raise ValueError("AudD API token is missing. Please enter your API token in Settings.")

    url = "https://api.audd.io/"
    data = {
        "api_token": api_token.strip(),
        "return": "apple_music,spotify",
    }
    files = {
        "file": ("sample.wav", audio_wav_bytes, "audio/wav"),
    }

    client = get_shared_client()
    resp = client.post(url, data=data, files=files, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"AudD returned HTTP {resp.status_code}: {resp.text}")

    result = resp.json()
    status = result.get("status")
    if status == "error":
        err_msg = result.get("error", {}).get("error_message", "Unknown AudD error")
        raise RuntimeError(f"AudD Error: {err_msg}")

    result_data = result.get("result")
    if not result_data:
        return {"matched": False, "provider": "AudD"}

    spotify_data = result_data.get("spotify", {}) or {}
    spotify_url = spotify_data.get("external_urls", {}).get("spotify", "")

    return {
        "matched": True,
        "provider": "AudD",
        "title": result_data.get("title", "Unknown Title"),
        "artist": result_data.get("artist", "Unknown Artist"),
        "album": result_data.get("album", ""),
        "release_date": result_data.get("release_date", ""),
        "spotify_url": spotify_url,
        "youtube_url": f"https://www.youtube.com/results?search_query={result_data.get('title', '')}+{result_data.get('artist', '')}",
        "confidence": 1.0,
    }


def recognize_acrcloud_direct(
    audio_wav_bytes: bytes,
    host: str,
    access_key: str,
    access_secret: str,
    timeout: float = 12.0,
) -> Dict[str, Any]:
    """Query ACRCloud audio recognition API directly using HMAC-SHA1 signature."""
    if not host.strip() or not access_key.strip() or not access_secret.strip():
        raise ValueError("ACRCloud host, access key, or secret is missing in Settings.")

    clean_host = host.strip().replace("https://", "").replace("http://", "").rstrip("/")
    url = f"https://{clean_host}/v1/identify"

    requrl = "/v1/identify"
    http_method = "POST"
    http_action = requrl
    data_type = "audio"
    signature_version = "1"
    timestamp = str(int(time.time()))

    string_to_sign = f"{http_method}\n{http_action}\n{access_key.strip()}\n{data_type}\n{signature_version}\n{timestamp}"
    sign = base64.b64encode(
        hmac.new(access_secret.strip().encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")

    data = {
        "access_key": access_key.strip(),
        "sample_bytes": str(len(audio_wav_bytes)),
        "timestamp": timestamp,
        "signature": sign,
        "data_type": data_type,
        "signature_version": signature_version,
    }
    files = {
        "sample": ("sample.wav", audio_wav_bytes, "audio/wav"),
    }

    client = get_shared_client()
    resp = client.post(url, data=data, files=files, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"ACRCloud returned HTTP {resp.status_code}: {resp.text}")

    result = resp.json()
    status_code = result.get("status", {}).get("code")
    if status_code != 0:
        msg = result.get("status", {}).get("msg", "Unknown ACRCloud status")
        if status_code == 1001:  # No result
            return {"matched": False, "provider": "ACRCloud"}
        raise RuntimeError(f"ACRCloud Error ({status_code}): {msg}")

    metadata = result.get("metadata", {})
    musics = metadata.get("music", [])
    if not musics:
        return {"matched": False, "provider": "ACRCloud"}

    best_match = musics[0]
    artists = ", ".join([a.get("name", "") for a in best_match.get("artists", [])])
    album = best_match.get("album", {}).get("name", "")
    title = best_match.get("title", "Unknown Title")

    return {
        "matched": True,
        "provider": "ACRCloud",
        "title": title,
        "artist": artists or "Unknown Artist",
        "album": album,
        "confidence": float(best_match.get("score", 100)) / 100.0,
        "spotify_url": "",
        "youtube_url": f"https://www.youtube.com/results?search_query={title}+{artists}",
    }


def recognize_local_backend(
    hashes: list,
    audio_wav_bytes: bytes,
    backend_url: str = "http://127.0.0.1:8000",
    timeout: float = 12.0,
) -> Dict[str, Any]:
    """Query local PostgreSQL / SQLite recognition backend with two-step fallback."""
    client = get_shared_client()
    clean_backend = backend_url.rstrip("/")

    # Step 1: Local catalog
    resp = client.post(f"{clean_backend}/v1/recognize", json={"hashes": hashes})
    if resp.status_code == 200:
        data = resp.json()
        if data.get("matched"):
            track = data["track"]
            return {
                "matched": True,
                "provider": "Local Catalog",
                "title": track.get("title", "Unknown Title"),
                "artist": track.get("artist", "Unknown Artist"),
                "album": track.get("album", "Local Database"),
                "confidence": float(data.get("confidence", 1.0)),
                "spotify_url": "",
                "youtube_url": f"https://www.youtube.com/results?search_query={track.get('title', '')}+{track.get('artist', '')}",
            }

        # Step 2: Fallback query
        fallback_token = data.get("fallback_token")
        if fallback_token:
            fb_resp = client.post(
                f"{clean_backend}/v1/recognize/fallback",
                content=audio_wav_bytes,
                headers={
                    "Authorization": f"Bearer {fallback_token}",
                    "Content-Type": "audio/wav",
                },
            )
            if fb_resp.status_code == 200:
                fb_data = fb_resp.json()
                if fb_data.get("matched"):
                    fb_track = fb_data["track"]
                    return {
                        "matched": True,
                        "provider": fb_data.get("provider", "Cloud Fallback"),
                        "title": fb_track.get("title", "Unknown Title"),
                        "artist": fb_track.get("artist", "Unknown Artist"),
                        "album": fb_track.get("album", ""),
                        "confidence": float(fb_data.get("confidence", 1.0)),
                        "spotify_url": "",
                        "youtube_url": f"https://www.youtube.com/results?search_query={fb_track.get('title', '')}+{fb_track.get('artist', '')}",
                    }

    return {"matched": False, "provider": "Local Backend"}
