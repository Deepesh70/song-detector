from typing import List, Tuple, Optional
import numpy as np

# Canonical DSP constants
SAMPLE_RATE: int = 11_025
FFT_WINDOW_SIZE: int = 2048
FFT_HOP_SIZE: int = 256
MIN_FREQUENCY_BIN: int = 5
MAX_FREQUENCY_BIN: int = 928
MAGNITUDE_FLOOR_DB: float = -45.0

# 5 Logarithmic Frequency Bands (bin indices)
FREQUENCY_BANDS: List[Tuple[int, int]] = [
    (5, 24),     # Band 0: Sub-bass (~27 - 129 Hz)
    (25, 59),    # Band 1: Bass (~135 - 318 Hz)
    (60, 139),   # Band 2: Midrange (~323 - 748 Hz)
    (140, 349),  # Band 3: High-mid (~754 - 1879 Hz)
    (350, 928),  # Band 4: Treble (~1884 - 4996 Hz)
]

# Pairing Constraints
TARGET_ZONE_T_MIN: int = 3
TARGET_ZONE_T_MAX: int = 258
TARGET_ZONE_MAX_DELTA_F: int = 250
MAX_TARGETS_PER_ANCHOR: int = 5
MAX_QUERY_HASHES: int = 800


def pack_hash(f1: int, f2: int, dt: int) -> int:
    """Pack landmark frequencies and time delta into an unsigned 32-bit integer.
    
    Bit layout:
      f1 (10 bits, 22..31)
      f2 (10 bits, 12..21)
      dt_packed (8 bits, 4..11)
      reserved (4 bits, 0..3)
    """
    dt_packed = dt - TARGET_ZONE_T_MIN
    if not (0 <= dt_packed <= 255):
        raise ValueError(f"dt_packed {dt_packed} out of range [0, 255] (dt={dt})")
    if not (0 <= f1 <= 1023) or not (0 <= f2 <= 1023):
        raise ValueError(f"Frequency bins f1={f1}, f2={f2} must be in [0, 1023]")

    return (
        ((f1 & 0x3FF) << 22)
        | ((f2 & 0x3FF) << 12)
        | ((dt_packed & 0xFF) << 4)
    )


def unpack_hash(u32_hash: int) -> Tuple[int, int, int]:
    """Unpack an unsigned 32-bit integer back to (f1, f2, dt)."""
    f1 = (u32_hash >> 22) & 0x3FF
    f2 = (u32_hash >> 12) & 0x3FF
    dt_packed = (u32_hash >> 4) & 0xFF
    dt = dt_packed + TARGET_ZONE_T_MIN
    return f1, f2, dt


def to_signed_int32(u32_hash: int) -> int:
    """Bit-cast an unsigned 32-bit integer to a signed two's complement 32-bit integer for PostgreSQL."""
    return u32_hash - 0x1_0000_0000 if u32_hash >= 0x8000_0000 else u32_hash


def from_signed_int32(i32_hash: int) -> int:
    """Bit-cast a signed two's complement 32-bit integer back to an unsigned 32-bit integer."""
    return i32_hash + 0x1_0000_0000 if i32_hash < 0 else i32_hash


def compute_spectrogram(audio_buffer: np.ndarray) -> np.ndarray:
    """Compute log-magnitude STFT spectrogram in dB.
    
    Returns array of shape [n_frequency_bins, n_time_frames].
    """
    from scipy import signal
    _, _, zxx = signal.stft(
        audio_buffer,
        fs=SAMPLE_RATE,
        window="hann",
        nperseg=FFT_WINDOW_SIZE,
        noverlap=FFT_WINDOW_SIZE - FFT_HOP_SIZE,
        boundary=None,
        padded=False,
    )
    # Log power magnitude in dB
    magnitudes = np.abs(zxx)
    return 20.0 * np.log10(magnitudes + 1e-10)


def extract_peaks(spectrogram: np.ndarray) -> List[Tuple[int, int, float]]:
    """Extract 2D local maxima within 5 logarithmic frequency bands subject to a relative magnitude floor.
    
    Returns list of (bin_index, frame_index, magnitude_db).
    """
    from scipy.ndimage import maximum_filter
    num_bins, num_frames = spectrogram.shape
    if num_frames == 0 or num_bins == 0:
        return []

    # Dynamic magnitude floor across valid frequency bins
    valid_spectrogram = spectrogram[MIN_FREQUENCY_BIN:MAX_FREQUENCY_BIN + 1, :]
    if valid_spectrogram.size == 0:
        return []

    max_mag = float(np.max(valid_spectrogram))
    floor_threshold = max_mag + MAGNITUDE_FLOOR_DB

    # 2D local maximum filter: +/- 5 bins, +/- 5 frames (11x11 footprint)
    footprint = np.ones((11, 11), dtype=bool)
    local_max = maximum_filter(spectrogram, footprint=footprint, mode="constant", cval=-np.inf)
    is_peak = (spectrogram == local_max) & (spectrogram >= floor_threshold)

    peaks: List[Tuple[int, int, float]] = []

    # Quota: top 1 peak per band per time frame
    for frame_idx in range(num_frames):
        for band_min, band_max in FREQUENCY_BANDS:
            # Find candidate peaks within this band at this frame
            band_peaks = []
            for bin_idx in range(band_min, band_max + 1):
                if is_peak[bin_idx, frame_idx]:
                    mag = float(spectrogram[bin_idx, frame_idx])
                    band_peaks.append((bin_idx, frame_idx, mag))

            if band_peaks:
                # Select the highest-magnitude peak in this band for this frame
                band_peaks.sort(key=lambda p: p[2], reverse=True)
                peaks.append(band_peaks[0])

    # Sort all peaks chronologically
    peaks.sort(key=lambda p: (p[1], p[0]))
    return peaks


def generate_landmark_hashes(
    peaks: List[Tuple[int, int, float]],
    cap_hashes: Optional[int] = None,
) -> List[Tuple[int, int]]:
    """Form combinatorial pairs from peaks and return list of (signed_int32_hash, t_query_frame)."""
    hashes: List[Tuple[int, int]] = []
    num_peaks = len(peaks)

    for i in range(num_peaks):
        f1, t1, _ = peaks[i]

        # Collect candidate targets satisfying time and frequency locality
        candidates: List[Tuple[int, int, float]] = []
        for j in range(i + 1, num_peaks):
            f2, t2, mag2 = peaks[j]
            dt = t2 - t1

            if dt < TARGET_ZONE_T_MIN:
                continue
            if dt > TARGET_ZONE_T_MAX:
                break  # Chronologically sorted, no further points can be within window

            if abs(f2 - f1) <= TARGET_ZONE_MAX_DELTA_F:
                candidates.append((f2, t2, mag2))

        # Rank candidates by magnitude A2 descending and take top N
        candidates.sort(key=lambda c: c[2], reverse=True)
        selected_targets = candidates[:MAX_TARGETS_PER_ANCHOR]

        for f2, t2, _ in selected_targets:
            dt = t2 - t1
            u32_hash = pack_hash(f1, f2, dt)
            signed_hash = to_signed_int32(u32_hash)
            hashes.append((signed_hash, t1))

    if cap_hashes is not None and len(hashes) > cap_hashes:
        # Uniform subsample if over budget
        indices = np.linspace(0, len(hashes) - 1, cap_hashes, dtype=int)
        hashes = [hashes[idx] for idx in indices]

    return hashes


def fingerprint_buffer(
    audio_buffer: np.ndarray,
    cap_hashes: Optional[int] = None,
) -> List[Tuple[int, int]]:
    """Complete fingerprint pipeline: STFT, peak extraction, pairing, and bit packing."""
    spec = compute_spectrogram(audio_buffer)
    peaks = extract_peaks(spec)
    return generate_landmark_hashes(peaks, cap_hashes=cap_hashes)
