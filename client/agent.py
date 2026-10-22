import argparse
import io
import os
import sys
import time
from pathlib import Path
from typing import Optional
import httpx
import numpy as np
import soundfile as sf
import certifi

# Ensure SSL_CERT_FILE points to certifi's valid bundle
os.environ["SSL_CERT_FILE"] = certifi.where()

# Ensure project root is in sys.path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Sanitize invalid or unreadable SSL_CERT_FILE from Git Bash / terminal environments
if "SSL_CERT_FILE" in os.environ:
    cert_path = os.environ["SSL_CERT_FILE"]
    if not cert_path or not os.path.exists(cert_path):
        del os.environ["SSL_CERT_FILE"]

from client.capture import WasapiLoopbackCapture
from client.preprocessor import SAMPLE_RATE_CANONICAL

API_BASE_URL: str = "http://127.0.0.1:8000"


def run_recognition_cycle(
    capture: WasapiLoopbackCapture,
    api_url: str = API_BASE_URL,
) -> bool:
    """Execute a single capture, fingerprint, and recognition handshake."""
    print("\n[Listening] Capturing 5 seconds of system playback via WASAPI...")
    passed_gate, hashes, pcm_buffer = capture.capture_and_fingerprint()

    if not passed_gate:
        print("[Silence] Audio energy below -50 dBFS silence gate. Skipping recognition.")
        return False

    print(f"[Fingerprinted] Extracted {len(hashes)} landmark pairs. Checking local catalog...")

    # Step 1: Send hashes to local catalog
    try:
        with httpx.Client(base_url=api_url, timeout=12.0, verify=False) as client:
            resp = client.post("/v1/recognize", json={"hashes": hashes})
            if resp.status_code != 200:
                print(f"[API Error] Server returned HTTP {resp.status_code}")
                return False

            data = resp.json()
            if data.get("matched"):
                track = data["track"]
                conf = data["confidence"]
                print("==================================================")
                print(">>> SONG IDENTIFIED (Local Catalog Hit) <<<")
                print(f"Title:      {track.get('title')}")
                print(f"Artist:     {track.get('artist')}")
                print(f"Offset:     {track.get('offset_seconds')}s")
                print(f"Prominence: {conf.get('prominence_ratio')} (Votes: {conf.get('peak_votes')})")
                print("==================================================")
                return True

            # Step 2: Local miss -> two-step fallback
            fallback_token = data.get("fallback_token")
            if not fallback_token:
                print("[No Match] Track not found and no fallback token received.")
                return False

            print("[Local Miss] Not in local library. Forwarding 5s audio to global provider (AudD)...")
            
            # Encode canonical mono PCM into clean in-memory WAV
            wav_bio = io.BytesIO()
            sf.write(wav_bio, pcm_buffer, SAMPLE_RATE_CANONICAL, format="WAV")
            wav_bytes = wav_bio.getvalue()

            fallback_resp = client.post(
                "/v1/recognize/fallback",
                content=wav_bytes,
                headers={
                    "Authorization": f"Bearer {fallback_token}",
                    "Content-Type": "audio/wav",
                },
            )

            if fallback_resp.status_code == 200:
                fb_data = fallback_resp.json()
                if fb_data.get("matched"):
                    track = fb_data["track"]
                    print("==================================================")
                    print(">>> SONG IDENTIFIED (AudD Global Catalog) <<<")
                    print(f"Title:        {track.get('title')}")
                    print(f"Artist:       {track.get('artist')}")
                    print(f"Album:        {track.get('album')}")
                    print(f"Release Date: {track.get('release_date')}")
                    if track.get("song_link"):
                        print(f"Listen:       {track.get('song_link')}")
                    print("==================================================")
                    return True
                else:
                    print(f"[No Match] Global recognition returned: {fb_data.get('detail')}")
                    return False
            else:
                print(f"[Fallback Error] HTTP {fallback_resp.status_code}: {fallback_resp.text}")
                return False

    except httpx.ConnectError:
        print(f"[Connection Error] Could not connect to API server at {api_url}.")
        print("  Make sure the backend is running: uvicorn backend.app:app --host 127.0.0.1 --port 8000")
        return False


def main():
    parser = argparse.ArgumentParser(description="Song Detector Desktop Loopback Agent")
    parser.add_argument("--listen", action="store_true", help="Start continuous loopback audio listener")
    parser.add_argument("--once", action="store_true", help="Run a single 5-second capture and exit")
    parser.add_argument("--api-url", default=API_BASE_URL, help="Backend API server URL")
    args = parser.parse_args()

    capture = WasapiLoopbackCapture()
    capture.start_keepalive()

    try:
        if args.once or not args.listen:
            run_recognition_cycle(capture, api_url=args.api_url)
        else:
            print("[Agent Active] Listening for playback. Press Ctrl+C to stop.")
            while True:
                run_recognition_cycle(capture, api_url=args.api_url)
                time.sleep(2.0)
    except KeyboardInterrupt:
        print("\n[Shutting down] Stopped loopback listener.")
    finally:
        capture.stop_keepalive()


if __name__ == "__main__":
    main()
