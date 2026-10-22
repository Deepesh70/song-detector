import argparse
import os
import sys
from pathlib import Path
from collections import defaultdict
from typing import List, Tuple

# Ensure project root is in sys.path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import soundfile as sf
import numpy as np

from client.preprocessor import preprocess_audio_buffer
from client.fingerprinter import fingerprint_buffer
from backend.db import DatabaseManager

MAX_IDENTICAL_HASHES_PER_SONG: int = 5


def prune_repetitive_song_hashes(
    hashes: List[Tuple[int, int]],
    max_occurrences: int = MAX_IDENTICAL_HASHES_PER_SONG,
) -> List[Tuple[int, int]]:
    """Cap occurrences of any single hash within the same track to eliminate stationary hums and drone noise."""
    counts = defaultdict(int)
    pruned: List[Tuple[int, int]] = []

    for signed_hash, offset in hashes:
        if counts[signed_hash] < max_occurrences:
            counts[signed_hash] += 1
            pruned.append((signed_hash, offset))

    return pruned


def ingest_file(
    file_path: str,
    db: DatabaseManager,
    title: str = None,
    artist: str = None,
) -> int:
    """Read an audio file, extract landmark fingerprints, and persist to database."""
    base_name = os.path.basename(file_path)
    if not title:
        title = os.path.splitext(base_name)[0]
    if not artist:
        artist = "Unknown Artist"

    data, sr = sf.read(file_path, dtype="float32")
    duration_sec = int(len(data) / sr)

    passed_gate, processed_mono = preprocess_audio_buffer(data, orig_sr=sr)
    if not passed_gate:
        raise ValueError(f"Audio file {file_path} is silent (below -50 dBFS)")

    raw_hashes = fingerprint_buffer(processed_mono)
    pruned_hashes = prune_repetitive_song_hashes(raw_hashes)

    song_id = db.insert_track(
        title=title,
        artist=artist,
        duration_seconds=duration_sec,
        fingerprints=pruned_hashes,
    )
    return song_id


def ingest_catalog(catalog_dir: str, db: DatabaseManager) -> None:
    """Scan a directory of audio files and batch ingest each track."""
    supported_exts = (".wav", ".flac", ".mp3", ".ogg")
    count = 0

    for root, _, files in os.walk(catalog_dir):
        for f in files:
            if f.lower().endswith(supported_exts):
                path = os.path.join(root, f)
                print(f"[Ingesting] Processing {f}...")
                try:
                    song_id = ingest_file(path, db)
                    print(f" -> Success: Song ID {song_id}")
                    count += 1
                except Exception as e:
                    print(f" -> Error ingesting {f}: {e}")

    print(f"\n[Ingestion Complete] Ingested {count} tracks. Running VACUUM ANALYZE to update Visibility Map...")
    db.vacuum_analyze()
    print("[Done] PostgreSQL Visibility Map updated for Index-Only Scans.")


def main():
    parser = argparse.ArgumentParser(description="Song Detector Offline Catalog Ingester")
    parser.add_argument("--catalog-dir", required=True, help="Directory containing audio tracks to ingest")
    parser.add_argument("--init-db", action="store_true", help="Initialize PostgreSQL schema before ingestion")
    args = parser.parse_args()

    db = DatabaseManager()
    if args.init_db:
        print("[Database] Initializing schema and covering index...")
        db.init_schema()

    ingest_catalog(args.catalog_dir, db)


if __name__ == "__main__":
    main()
