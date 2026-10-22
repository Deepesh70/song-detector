from typing import Tuple
import numpy as np
from scipy import signal

# Canonical DSP constants
SAMPLE_RATE_INPUT: int = 48_000
SAMPLE_RATE_CANONICAL: int = 11_025
SILENCE_THRESHOLD_DBFS: float = -50.0
LOWPASS_CUTOFF_HZ: float = 5_000.0


def calculate_rms_dbfs(buffer: np.ndarray) -> float:
    """Calculate the Root Mean Square (RMS) energy in decibels relative to full scale (dBFS).
    
    Accepts 1D mono or 2D stereo buffers. Returns dBFS where 0 dBFS is a full-scale square wave.
    """
    if buffer.size == 0:
        return -120.0
    rms = np.sqrt(np.mean(np.square(buffer, dtype=np.float64)))
    # Avoid log(0) with a -120 dBFS noise floor clamp
    return float(20.0 * np.log10(rms + 1e-6))


def is_silent(buffer: np.ndarray, threshold_dbfs: float = SILENCE_THRESHOLD_DBFS) -> bool:
    """Evaluate whether an audio buffer falls below the silence threshold."""
    return calculate_rms_dbfs(buffer) < threshold_dbfs


def downmix_to_mono(buffer: np.ndarray) -> np.ndarray:
    """Downmix multi-channel audio to a single mono channel."""
    if buffer.ndim == 1:
        return buffer.astype(np.float32)
    # Average across channels (assuming shape [samples, channels])
    return np.mean(buffer, axis=-1, dtype=np.float32)


def resample_to_canonical(
    buffer: np.ndarray,
    orig_sr: int = SAMPLE_RATE_INPUT,
    target_sr: int = SAMPLE_RATE_CANONICAL,
    cutoff_hz: float = LOWPASS_CUTOFF_HZ,
) -> np.ndarray:
    """Resample audio buffer to target sample rate with an anti-aliasing low-pass filter.
    
    Uses polyphase sinc filtering via scipy.signal.resample_poly with a sharp Kaiser filter.
    """
    if orig_sr == target_sr:
        return buffer.astype(np.float32)

    # Calculate greatest common divisor for rational resampling factor
    gcd = int(np.gcd(orig_sr, target_sr))
    up = target_sr // gcd
    down = orig_sr // gcd

    # Polyphase anti-aliasing sinc resampling with a 60 dB Kaiser window
    resampled = signal.resample_poly(buffer, up=up, down=down, window=("kaiser", 5.653))
    return resampled.astype(np.float32)


def preprocess_audio_buffer(
    raw_buffer: np.ndarray,
    orig_sr: int = SAMPLE_RATE_INPUT,
) -> Tuple[bool, np.ndarray]:
    """Execute complete preprocessing pipeline: silence gating, mono downmix, and anti-aliased resampling.
    
    Returns:
        (passed_gate, processed_buffer)
    """
    mono = downmix_to_mono(raw_buffer)
    if is_silent(mono):
        return False, np.empty(0, dtype=np.float32)
    
    resampled = resample_to_canonical(mono, orig_sr=orig_sr, target_sr=SAMPLE_RATE_CANONICAL)
    return True, resampled
