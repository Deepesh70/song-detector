"""Background thread worker for audio capture and provider querying."""

import numpy as np
from typing import Any, Dict
from PyQt6.QtCore import QThread, pyqtSignal

from client.capture import WasapiLoopbackCapture
from client.preprocessor import preprocess_audio_buffer
from client.fingerprinter import fingerprint_buffer
from client.direct_recognizer import (
    pcm_to_wav_bytes,
    recognize_audd_direct,
    recognize_acrcloud_direct,
    recognize_local_backend,
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

            # Progressive Chunk Recognition for Local Backend
            if provider == "local" and duration > 3.0:
                self.status_changed.emit("Streaming audio probe (Phase 1: 3.0s)...")
                probe_audio = self.capture.capture_raw_buffer(duration_seconds=3.0)
                passed_gate, probe_mono = preprocess_audio_buffer(probe_audio, orig_sr=sr)

                if passed_gate:
                    probe_hashes = fingerprint_buffer(probe_mono)
                    probe_wav = pcm_to_wav_bytes(probe_mono)
                    backend_url = self.config.get("backend_url", "http://127.0.0.1:8000")
                    probe_result = recognize_local_backend(probe_hashes, probe_wav, backend_url=backend_url)

                    if probe_result.get("matched"):
                        self.status_changed.emit(f"Fast probe matched: {probe_result.get('title')}")
                        show_windows_toast(
                            f"🎵 {probe_result.get('title')}",
                            f"Artist: {probe_result.get('artist')}\nAlbum: {probe_result.get('album', '')}",
                        )
                        self.recognition_finished.emit(probe_result)
                        return

                # If probe didn't match, continue streaming the remaining audio chunk
                remaining_time = duration - 3.0
                self.status_changed.emit(f"Extending audio capture (+{remaining_time:.1f}s)...")
                rem_audio = self.capture.capture_raw_buffer(duration_seconds=remaining_time)
                raw_audio = np.concatenate([probe_audio, rem_audio], axis=0)
            else:
                # Direct capture for Cloud APIs or short durations
                raw_audio = self.capture.capture_raw_buffer(duration_seconds=duration)

            self.status_changed.emit("Analyzing audio signal...")
            passed_gate, processed_mono = preprocess_audio_buffer(raw_audio, orig_sr=sr)

            if not passed_gate:
                self.status_changed.emit("Silence detected (below -50 dBFS).")
                self.recognition_failed.emit("Silence detected. Audio was below -50 dBFS.")
                return

            wav_bytes = pcm_to_wav_bytes(processed_mono)
            self.status_changed.emit(f"Querying {provider.upper()}...")

            if provider == "audd":
                token = self.config.get("audd_token", "")
                result = recognize_audd_direct(wav_bytes, api_token=token)

            elif provider == "acrcloud":
                host = self.config.get("acrcloud_host", "")
                key = self.config.get("acrcloud_access_key", "")
                secret = self.config.get("acrcloud_access_secret", "")
                result = recognize_acrcloud_direct(
                    wav_bytes, host=host, access_key=key, access_secret=secret
                )

            else:  # local (full buffer fall-through)
                hashes = fingerprint_buffer(processed_mono)
                backend_url = self.config.get("backend_url", "http://127.0.0.1:8000")
                result = recognize_local_backend(hashes, wav_bytes, backend_url=backend_url)

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
