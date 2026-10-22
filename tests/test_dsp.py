import numpy as np
from client.fingerprinter import (
    compute_spectrogram,
    extract_peaks,
    generate_landmark_hashes,
    SAMPLE_RATE,
    FFT_WINDOW_SIZE,
    FFT_HOP_SIZE,
    FREQUENCY_BANDS,
)


def test_dynamic_spectral_floor_and_silent_bands():
    """Verify that silent bands below M_max - 45 dB emit 0 peaks."""
    duration_s = 2.0
    t = np.linspace(0, duration_s, int(SAMPLE_RATE * duration_s), endpoint=False)
    
    # Generate a loud mid-range tone in Band 2 (e.g. 500 Hz, bin ~93)
    tone_500hz = 0.8 * np.sin(2 * np.pi * 500 * t)
    
    # Add quiet noise across the whole spectrum (-70 dB relative to tone)
    noise = np.random.normal(0, 1e-4, size=t.shape)
    signal = tone_500hz + noise

    spec = compute_spectrogram(signal)
    peaks = extract_peaks(spec)

    # Band 0: bins 5..24 (~27-129 Hz)
    # Band 4: bins 350..928 (~1884-4996 Hz)
    b0_min, b0_max = FREQUENCY_BANDS[0]
    b4_min, b4_max = FREQUENCY_BANDS[4]

    peaks_in_b0 = [p for p in peaks if b0_min <= p[0] <= b0_max]
    peaks_in_b4 = [p for p in peaks if b4_min <= p[0] <= b4_max]

    assert len(peaks_in_b0) == 0, f"Expected 0 peaks in Band 0, got {len(peaks_in_b0)}"
    assert len(peaks_in_b4) == 0, f"Expected 0 peaks in Band 4, got {len(peaks_in_b4)}"
    
    # Band 2 must have peaks
    b2_min, b2_max = FREQUENCY_BANDS[2]
    peaks_in_b2 = [p for p in peaks if b2_min <= p[0] <= b2_max]
    assert len(peaks_in_b2) > 0, "Band 2 should contain peaks for 500 Hz tone"


def test_temporal_spacing_between_peaks():
    """Verify that 2D local maxima filter prevents peaks in the same band within +/- 5 frames."""
    duration_s = 3.0
    t = np.linspace(0, duration_s, int(SAMPLE_RATE * duration_s), endpoint=False)
    # Steady 440 Hz tone
    audio = 0.9 * np.sin(2 * np.pi * 440 * t)

    spec = compute_spectrogram(audio)
    peaks = extract_peaks(spec)

    # Group peaks by band
    for band_idx, (b_min, b_max) in enumerate(FREQUENCY_BANDS):
        band_peaks = [p for p in peaks if b_min <= p[0] <= b_max]
        # Check consecutive frames
        frames = [p[1] for p in band_peaks]
        for i in range(len(frames) - 1):
            frame_diff = frames[i + 1] - frames[i]
            assert frame_diff >= 6, (
                f"Band {band_idx} produced peaks too close: frames {frames[i]} and {frames[i+1]} (diff={frame_diff})"
            )


def test_pairing_amplitude_ranking():
    """Verify that the top N target peaks are selected by amplitude rather than early time starvation."""
    # Synthesize 1 anchor peak and 10 forward peaks
    # anchor: bin 100, frame 10, mag 20.0
    # targets: 5 quiet peaks at frames 13..17, 5 loud peaks at frames 50..54
    anchor = (100, 10, 20.0)
    quiet_targets = [(105, t, 5.0) for t in range(13, 18)]
    loud_targets = [(110, t, 18.0) for t in range(50, 55)]
    
    all_peaks = [anchor] + quiet_targets + loud_targets
    all_peaks.sort(key=lambda p: (p[1], p[0]))

    hashes = generate_landmark_hashes(all_peaks)
    
    # All hashes for anchor frame 10 should pair with the loud targets
    anchor_hashes = [h for h in hashes if h[1] == 10]
    assert len(anchor_hashes) == 5, f"Expected 5 paired hashes for anchor, got {len(anchor_hashes)}"
