"""Background thread worker for audio capture and cloud provider querying."""

from typing import Any, Dict
from PyQt6.QtCore import QThread, pyqtSignal

from client.capture import WasapiLoopbackCapture
from client.preprocessor import preprocess_audio_buffer
from client.direct_recognizer import (
    pcm_to_wav_bytes,
    recognize_audd_direct,
    recognize_acrcloud_direct,
)
from client.notifier import show_windows_toast


class RecognitionWorker(QThread):
    """Background worker for non-blocking WASAPI loopback capture and recognition."""

    status_changed = pyqtSignal(str)
    level_updated = pyqtSignal(int)
    recognition_finished = pyqtSignal(dict)
    recognition_failed = pyqtSignal(str)

    def __init__(self, capture: WasapiLoopbackCapture, config: Dict[str, Any]):
        super().__init__()
        self.capture = capture
        self.config = config

    def run(self) -> None:
        try:
            self.status_changed.emit("Listening to system audio...")
            show_windows_toast("HearThis", "Listening to system audio...")

            duration = float(self.config.get("capture_seconds", 5))
            provider = self.config.get("provider", "audd").lower()
            sr = self.capture.sample_rate

            raw_audio = self.capture.capture_raw_buffer(duration_seconds=duration)

            self.status_changed.emit("Analyzing audio signal...")
            passed_gate, processed_mono = preprocess_audio_buffer(raw_audio, orig_sr=sr)

            if not passed_gate:
                self.status_changed.emit("Silence detected (below -50 dBFS).")
                self.recognition_failed.emit("Silence detected. Audio was below -50 dBFS.")
                return

            wav_bytes = pcm_to_wav_bytes(processed_mono)
            self.status_changed.emit(f"Querying {provider.upper()}...")

            if provider == "acrcloud":
                host = self.config.get("acrcloud_host", "")
                key = self.config.get("acrcloud_access_key", "")
                secret = self.config.get("acrcloud_access_secret", "")
                result = recognize_acrcloud_direct(
                    wav_bytes, host=host, access_key=key, access_secret=secret
                )
            else:  # default to audd
                token = self.config.get("audd_token", "")
                result = recognize_audd_direct(wav_bytes, api_token=token)

            if result.get("matched"):
                self.status_changed.emit(f"Matched: {result.get('title')}")
                show_windows_toast(
                    f"🎵 {result.get('title')}",
                    f"Artist: {result.get('artist')}\nAlbum: {result.get('album', '')}",
                )
            else:
                self.status_changed.emit("No match found.")
                show_windows_toast("HearThis", "No match found in database.")

            self.recognition_finished.emit(result)

        except Exception as e:
            err_msg = str(e)
            self.status_changed.emit(f"Error: {err_msg[:60]}")
            self.recognition_failed.emit(err_msg)
