import numpy as np
from client.preprocessor import (
    calculate_rms_dbfs,
    is_silent,
    downmix_to_mono,
    resample_to_canonical,
    SAMPLE_RATE_INPUT,
    SAMPLE_RATE_CANONICAL,
    SILENCE_THRESHOLD_DBFS,
)


def test_silence_gating():
    """Verify silence gate correctly classifies quiet background audio vs active playback."""
    # Quiet white noise at ~ -65 dBFS
    quiet_samples = np.random.normal(0, 5e-4, size=48_000).astype(np.float32)
    dbfs_quiet = calculate_rms_dbfs(quiet_samples)
    assert dbfs_quiet < SILENCE_THRESHOLD_DBFS
    assert is_silent(quiet_samples) is True

    # Active audio signal at ~ -10 dBFS
    active_samples = (0.3 * np.sin(2 * np.pi * 440 * np.linspace(0, 1, 48_000))).astype(np.float32)
    dbfs_active = calculate_rms_dbfs(active_samples)
    assert dbfs_active > SILENCE_THRESHOLD_DBFS
    assert is_silent(active_samples) is False


def test_stereo_to_mono_downmix():
    """Verify downmix to mono averages across channels accurately."""
    left = np.full((100,), 0.8, dtype=np.float32)
    right = np.full((100,), 0.2, dtype=np.float32)
    stereo = np.column_stack([left, right])

    mono = downmix_to_mono(stereo)
    assert mono.shape == (100,)
    assert np.allclose(mono, 0.5, atol=1e-5)


def test_anti_aliasing_attenuation():
    """Verify that frequencies above 5 kHz are sharply attenuated during 48kHz -> 11,025Hz resampling."""
    duration_s = 1.0
    t = np.linspace(0, duration_s, int(SAMPLE_RATE_INPUT * duration_s), endpoint=False)
    
    # 10 kHz tone (would alias to 1025 Hz at 11,025 Hz without anti-aliasing)
    high_freq_tone = (0.8 * np.sin(2 * np.pi * 10_000 * t)).astype(np.float32)
    
    resampled = resample_to_canonical(high_freq_tone, orig_sr=SAMPLE_RATE_INPUT, target_sr=SAMPLE_RATE_CANONICAL)
    
    rms_original = np.sqrt(np.mean(np.square(high_freq_tone)))
    rms_filtered = np.sqrt(np.mean(np.square(resampled)))
    
    attenuation_db = 20 * np.log10(rms_filtered / rms_original + 1e-10)
    # Filter should provide > 40 dB stopband attenuation
    assert attenuation_db < -40.0, f"Expected < -40 dB attenuation for 10 kHz tone, got {attenuation_db:.2f} dB"
