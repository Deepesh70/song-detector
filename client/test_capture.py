import os
import sys
import time
from pathlib import Path
import numpy as np

# Ensure project root is in sys.path regardless of current working directory
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import soundcard as sc
import soundfile as sf

from client.capture import WasapiLoopbackCapture
from client.preprocessor import (
    calculate_rms_dbfs,
    preprocess_audio_buffer,
    SAMPLE_RATE_INPUT,
    SAMPLE_RATE_CANONICAL,
    SILENCE_THRESHOLD_DBFS,
)
from client.fingerprinter import (
    compute_spectrogram,
    extract_peaks,
    generate_landmark_hashes,
    FREQUENCY_BANDS,
)


def run_live_diagnostic():
    print("==================================================")
    print("   Song Detector: Windows Live Capture Diagnostic")
    print("==================================================")

    # 1. Inspect audio loopback devices
    speaker = sc.default_speaker()
    print(f"\n[Hardware] Default Output Speaker: {speaker.name}")

    mics = sc.all_microphones(include_loopback=True)
    loopbacks = [m for m in mics if m.isloopback]
    print(f"[Hardware] Detected {len(loopbacks)} WASAPI Loopback Endpoints:")
    for lb in loopbacks:
        print(f"  - {lb.name}")

    capture = WasapiLoopbackCapture()
    capture.start_keepalive()

    print("\n--------------------------------------------------")
    print("Instruction:")
    print("  1. Play any song or video on YouTube, Spotify, etc.")
    print("  2. Ensure sound is coming through your speakers/headphones.")
    print("--------------------------------------------------")
    input("\nPress ENTER when your audio is playing to start 5-second capture...")

    print("\n[Recording] Capturing 5.0 seconds of system audio...")
    raw_buffer = capture.capture_raw_buffer()
    capture.stop_keepalive()

    # 2. Analyze RMS energy
    rms_dbfs = calculate_rms_dbfs(raw_buffer)
    print(f"\n[Analysis] Raw Buffer Shape: {raw_buffer.shape} (Native {SAMPLE_RATE_INPUT} Hz)")
    print(f"[Analysis] Measured Energy:  {rms_dbfs:.2f} dBFS (Gate Threshold: {SILENCE_THRESHOLD_DBFS:.2f} dBFS)")

    if rms_dbfs < SILENCE_THRESHOLD_DBFS:
        print("\n[Result] SILENCE DETECTED!")
        print("  The audio energy was below the -50 dBFS silence gate.")
        print("  Ensure that audio was playing at normal volume and try again.")
        return

    print("  -> Passed RMS silence gate!")

    # 3. Resample
    passed_gate, mono_resampled = preprocess_audio_buffer(raw_buffer, orig_sr=SAMPLE_RATE_INPUT)
    print(f"[Resampler] Resampled to Canonical Rate: {mono_resampled.shape[0]} samples ({SAMPLE_RATE_CANONICAL} Hz mono)")

    # 4. Save sample WAV file for user verification
    output_wav = "captured_test.wav"
    sf.write(output_wav, mono_resampled, SAMPLE_RATE_CANONICAL)
    print(f"[Audio Saved] Wrote clean canonical audio to: {os.path.abspath(output_wav)}")

    # 5. Extract STFT & Landmarks
    spec = compute_spectrogram(mono_resampled)
    peaks = extract_peaks(spec)
    hashes = generate_landmark_hashes(peaks, cap_hashes=800)

    print(f"\n[Landmarks] Extracted {len(peaks)} constellation peaks across 5 frequency bands:")
    for b_idx, (b_min, b_max) in enumerate(FREQUENCY_BANDS):
        band_peaks = [p for p in peaks if b_min <= p[0] <= b_max]
        print(f"  - Band {b_idx} (bins {b_min:3d}..{b_max:3d}): {len(band_peaks):3d} peaks")

    print(f"\n[Hashing] Generated {len(hashes)} 32-bit landmark pairs (capped at 800 for query budget)")
    print("\nFirst 5 generated query hashes:")
    for h, t_q in hashes[:5]:
        print(f"  Hash: {h:11d}  |  Query Frame Offset: {t_q:4d}")

    print("\n==================================================")
    print(">>> LIVE CAPTURE & FINGERPRINTING VERIFIED <<<")
    print("==================================================")


if __name__ == "__main__":
    run_live_diagnostic()
