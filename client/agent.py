import argparse
import os
import sys
import time
from pathlib import Path
import certifi

# Ensure SSL_CERT_FILE points to certifi's valid bundle
os.environ["SSL_CERT_FILE"] = certifi.where()

# Ensure project root is in sys.path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

if "SSL_CERT_FILE" in os.environ:
    cert_path = os.environ["SSL_CERT_FILE"]
    if not cert_path or not os.path.exists(cert_path):
        del os.environ["SSL_CERT_FILE"]

from client.capture import WasapiLoopbackCapture
from client.config import load_config
from client.preprocessor import preprocess_audio_buffer
from client.direct_recognizer import (
    pcm_to_wav_bytes,
    recognize_audd_direct,
    recognize_acrcloud_direct,
)


def run_recognition_cycle(capture: WasapiLoopbackCapture) -> bool:
    """Execute a single capture and cloud recognition handshake."""
    config = load_config()
    provider = config.get("provider", "audd").lower()
    duration = float(config.get("capture_seconds", 5))

    print(f"\n[Listening] Capturing {duration:.1f}s of system audio via WASAPI...")
    raw_audio = capture.capture_raw_buffer(duration_seconds=duration)
    passed_gate, mono = preprocess_audio_buffer(raw_audio, orig_sr=capture.sample_rate)

    if not passed_gate:
        print("[Silence] Audio energy below -50 dBFS silence gate. Skipping.")
        return False

    wav_bytes = pcm_to_wav_bytes(mono)
    print(f"[Querying] Sending audio to {provider.upper()}...")

    try:
        if provider == "acrcloud":
            res = recognize_acrcloud_direct(
                wav_bytes,
                host=config.get("acrcloud_host", ""),
                access_key=config.get("acrcloud_access_key", ""),
                access_secret=config.get("acrcloud_access_secret", ""),
            )
        else:
            res = recognize_audd_direct(
                wav_bytes,
                api_token=config.get("audd_token", ""),
            )

        if res.get("matched"):
            print("==================================================")
            print(f">>> SONG IDENTIFIED ({res.get('provider')}) <<<")
            print(f"Title:  {res.get('title')}")
            print(f"Artist: {res.get('artist')}")
            print(f"Album:  {res.get('album', '')}")
            if res.get("spotify_url"):
                print(f"URL:    {res.get('spotify_url')}")
            print("==================================================")
            return True
        else:
            print("[No Match] Track was not recognized.")
            return False

    except Exception as e:
        print(f"[Error] Recognition failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="HearThis Desktop Loopback Agent")
    parser.add_argument("--listen", action="store_true", help="Start continuous loopback audio listener")
    parser.add_argument("--once", action="store_true", help="Run a single capture and exit")
    args = parser.parse_args()

    capture = WasapiLoopbackCapture()
    capture.start_keepalive()

    try:
        if args.once or not args.listen:
            run_recognition_cycle(capture)
        else:
            print("[HearThis CLI Active] Listening for playback. Press Ctrl+C to stop.")
            while True:
                run_recognition_cycle(capture)
                time.sleep(2.0)
    except KeyboardInterrupt:
        print("\n[Shutting down] Stopped loopback listener.")
    finally:
        capture.stop_keepalive()


if __name__ == "__main__":
    main()
