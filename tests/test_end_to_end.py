import numpy as np
import pytest
from client.fingerprinter import fingerprint_buffer, SAMPLE_RATE
from backend.matcher import evaluate_matches, MIN_PROMINENCE_RATIO
from worker.ingest import prune_repetitive_song_hashes


def generate_synthetic_song(duration_sec: float = 30.0, seed: int = 42) -> np.ndarray:
    """Generate a realistic non-stationary multi-voice track with bass, chords, and melody."""
    rng = np.random.RandomState(seed)
    total_samples = int(SAMPLE_RATE * duration_sec)
    audio = np.zeros(total_samples, dtype=np.float32)

    current_sample = 0
    while current_sample < total_samples:
        note_dur = rng.uniform(0.18, 0.40)
        note_samples = min(int(note_dur * SAMPLE_RATE), total_samples - current_sample)
        if note_samples <= 0:
            break

        t = np.linspace(0, note_dur, note_samples, endpoint=False)
        # Polyphonic multi-band content:
        f_bass = rng.uniform(60.0, 250.0)
        f_mid1 = rng.uniform(300.0, 700.0)
        f_mid2 = f_mid1 * 1.25  # Major third
        f_treble = rng.uniform(900.0, 3500.0)

        env = np.exp(-2.5 * t / note_dur)
        voice_signal = (
            0.40 * np.sin(2 * np.pi * f_bass * t)
            + 0.25 * np.sin(2 * np.pi * f_mid1 * t)
            + 0.25 * np.sin(2 * np.pi * f_mid2 * t)
            + 0.15 * np.sin(2 * np.pi * f_treble * t)
        ) * env

        audio[current_sample:current_sample + note_samples] += voice_signal
        current_sample += note_samples

    return audio


def test_end_to_end_recognition_crop():
    """Verify that a random 5-second crop from a 30-second ingested track achieves top-1 match."""
    # 1. Generate synthetic track
    song_audio = generate_synthetic_song(duration_sec=30.0, seed=101)

    # 2. Ingest track into catalog (without query cap)
    track_hashes = fingerprint_buffer(song_audio)
    pruned_track_hashes = prune_repetitive_song_hashes(track_hashes)
    assert len(pruned_track_hashes) > 30, "Expected sufficient hashes for synthetic song"

    # Mock database index: list of (hash, song_id, offset_frames)
    song_id = 42
    db_index = [(h, song_id, offset) for h, offset in pruned_track_hashes]

    # 3. Take a random 5-second crop from the middle (seconds 10.0 to 15.0)
    start_sample = int(10.0 * SAMPLE_RATE)
    end_sample = int(15.0 * SAMPLE_RATE)
    crop_audio = song_audio[start_sample:end_sample]

    # 4. Fingerprint query clip (capped at 800)
    query_hashes = fingerprint_buffer(crop_audio, cap_hashes=800)
    assert len(query_hashes) > 0, "Query clip must produce hashes"

    # 5. Execute matcher
    result = evaluate_matches(query_hashes, db_index)

    # 6. Assertions
    assert result.matched is True
    assert result.candidate is not None
    assert result.candidate.song_id == song_id
    assert result.candidate.prominence_ratio >= MIN_PROMINENCE_RATIO

    # Expected offset frame = start_sample // hop_size = (10.0 * 11025) // 256 = 430
    expected_offset_frame = (10 * SAMPLE_RATE) // 256
    assert abs(result.candidate.peak_offset_frame - expected_offset_frame) <= 2, (
        f"Detected offset {result.candidate.peak_offset_frame} deviates from expected {expected_offset_frame}"
    )


def test_end_to_end_unmatched_audio_rejection():
    """Verify that an unmatched audio signal returns no match."""
    # Ingest Track A
    song_a = generate_synthetic_song(duration_sec=20.0, seed=1)
    hashes_a = prune_repetitive_song_hashes(fingerprint_buffer(song_a))
    db_index = [(h, 1, offset) for h, offset in hashes_a]

    # Query with completely different Track B
    song_b = generate_synthetic_song(duration_sec=5.0, seed=999)
    # Add random noise
    song_b += np.random.normal(0, 0.05, size=song_b.shape).astype(np.float32)
    query_hashes = fingerprint_buffer(song_b, cap_hashes=800)

    result = evaluate_matches(query_hashes, db_index)
    assert result.matched is False
