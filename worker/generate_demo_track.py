import os
import sys
from pathlib import Path
import numpy as np
import soundfile as sf

# Ensure project root in sys.path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from client.preprocessor import SAMPLE_RATE_INPUT


def create_demo_song(output_path: str = "music_catalog/Demo_Acoustic_Song.wav"):
    """Generate a clean polyphonic 45-second acoustic demo track."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    sr = SAMPLE_RATE_INPUT  # 48,000 Hz native audio
    duration_sec = 45.0
    total_samples = int(sr * duration_sec)
    t = np.linspace(0, duration_sec, total_samples, endpoint=False)
    audio = np.zeros(total_samples, dtype=np.float32)

    rng = np.random.RandomState(42)
    current_sample = 0

    while current_sample < total_samples:
        note_dur = rng.uniform(0.20, 0.50)
        note_samples = min(int(note_dur * sr), total_samples - current_sample)
        if note_samples <= 0:
            break

        t_note = np.linspace(0, note_dur, note_samples, endpoint=False)

        # Multi-band acoustic chords:
        f_bass = rng.uniform(65.0, 220.0)
        f_chord1 = rng.uniform(260.0, 600.0)
        f_chord2 = f_chord1 * 1.25  # Major third
        f_chord3 = f_chord1 * 1.50  # Perfect fifth
        f_treble = rng.uniform(1000.0, 4000.0)

        envelope = np.exp(-3.0 * t_note / note_dur)
        voice = (
            0.35 * np.sin(2 * np.pi * f_bass * t_note)
            + 0.20 * np.sin(2 * np.pi * f_chord1 * t_note)
            + 0.20 * np.sin(2 * np.pi * f_chord2 * t_note)
            + 0.15 * np.sin(2 * np.pi * f_chord3 * t_note)
            + 0.10 * np.sin(2 * np.pi * f_treble * t_note)
        ) * envelope

        audio[current_sample:current_sample + note_samples] += voice
        current_sample += note_samples

    # Normalize to -6 dBFS
    max_val = np.max(np.abs(audio))
    if max_val > 0:
        audio = (audio / max_val) * 0.5

    sf.write(output_path, audio, sr)
    print(f"[Created] Demo audio file: {os.path.abspath(output_path)}")
    print(f"  Duration: {duration_sec}s | Sample Rate: {sr} Hz")


if __name__ == "__main__":
    create_demo_song()
