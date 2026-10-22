import time
import threading
from typing import Optional, Tuple, List
import numpy as np
import soundcard as sc

from client.preprocessor import (
    preprocess_audio_buffer,
    SAMPLE_RATE_INPUT,
    SAMPLE_RATE_CANONICAL,
)
from client.fingerprinter import fingerprint_buffer, MAX_QUERY_HASHES

CAPTURE_DURATION_SECONDS: float = 5.0
DEFAULT_CHUNK_SIZE: int = 4096


class WasapiLoopbackCapture:
    """Windows WASAPI system audio loopback capture engine with silence keep-alive."""

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE_INPUT,
        capture_duration: float = CAPTURE_DURATION_SECONDS,
    ):
        self.sample_rate = sample_rate
        self.capture_duration = capture_duration
        self.total_frames = int(self.sample_rate * self.capture_duration)
        self._keepalive_running = False
        self._keepalive_thread: Optional[threading.Thread] = None

    def start_keepalive(self) -> None:
        """Start a silent render stream to keep the Windows WASAPI audio clock active during silence."""
        if self._keepalive_running:
            return

        self._keepalive_running = True

        def _silent_stream():
            try:
                speaker = sc.default_speaker()
                with speaker.player(samplerate=self.sample_rate) as player:
                    silent_chunk = np.zeros((1024, 2), dtype=np.float32)
                    while self._keepalive_running:
                        player.play(silent_chunk)
                        time.sleep(0.01)
            except Exception:
                # Keep-alive is best-effort and should never crash capture
                pass

        self._keepalive_thread = threading.Thread(target=_silent_stream, daemon=True)
        self._keepalive_thread.start()

    def stop_keepalive(self) -> None:
        """Stop the silent render keep-alive stream."""
        self._keepalive_running = False
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            self._keepalive_thread.join(timeout=0.2)

    def capture_raw_buffer(self) -> np.ndarray:
        """Record a 5-second buffer directly from the default speaker's loopback microphone.
        
        Returns float32 array of shape [frames, channels].
        """
        loopback_mic = sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)
        if loopback_mic is None:
            # Fallback to first available loopback device
            loopbacks = [m for m in sc.all_microphones(include_loopback=True) if m.isloopback]
            if not loopbacks:
                raise RuntimeError("No WASAPI loopback audio device detected on this system")
            loopback_mic = loopbacks[0]

        # Record exact number of frames
        with loopback_mic.recorder(samplerate=self.sample_rate) as recorder:
            raw_data = recorder.record(numframes=self.total_frames)

        return raw_data.astype(np.float32)

    def capture_and_fingerprint(self) -> Tuple[bool, List[Tuple[int, int]], np.ndarray]:
        """Capture loopback audio, evaluate silence gate, resample, and generate landmark hashes.
        
        Returns:
            (passed_silence_gate, hashes, canonical_pcm_buffer)
        """
        raw_buffer = self.capture_raw_buffer()
        passed_gate, processed_mono = preprocess_audio_buffer(raw_buffer, orig_sr=self.sample_rate)

        if not passed_gate:
            return False, [], np.empty(0, dtype=np.float32)

        hashes = fingerprint_buffer(processed_mono, cap_hashes=MAX_QUERY_HASHES)
        return True, hashes, processed_mono
