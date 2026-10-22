import os
import sqlite3
from typing import List, Tuple, Optional
import psycopg
from psycopg.rows import tuple_row

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:5432/song_detector"
)

PG_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tracks (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    artist VARCHAR(255) NOT NULL,
    duration_seconds INT NOT NULL,
    hash_count INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fingerprints (
    hash INT NOT NULL,
    song_id INT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    offset_frames INT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fingerprints_hash_covering 
ON fingerprints (hash) 
INCLUDE (song_id, offset_frames);
"""

PG_QUERY_HASHES_SQL = """
SELECT q.h AS hash, f.song_id, f.offset_frames
FROM unnest(%(hashes)s::int4[]) AS q(h)
CROSS JOIN LATERAL (
    SELECT song_id, offset_frames
    FROM fingerprints
    WHERE hash = q.h
    LIMIT 1000
) f;
"""

SQLITE_DB_PATH: str = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "song_detector.sqlite3"
)

SQLITE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    hash_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fingerprints (
    hash INTEGER NOT NULL,
    song_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    offset_frames INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fingerprints_hash_sqlite 
ON fingerprints (hash, song_id, offset_frames);
"""


class DatabaseManager:
    """Manages database connection, auto-selecting PostgreSQL when available, or local SQLite for development."""

    def __init__(self, dsn: str = DATABASE_URL, sqlite_path: str = SQLITE_DB_PATH):
        self.dsn = dsn
        self.sqlite_path = sqlite_path
        self._is_postgres = self._probe_postgres()

    def _probe_postgres(self) -> bool:
        """Check if PostgreSQL server is reachable."""
        try:
            with psycopg.connect(self.dsn, connect_timeout=1) as conn:
                return True
        except Exception:
            return False

    def init_schema(self) -> None:
        """Create tables and indexes."""
        if self._is_postgres:
            with psycopg.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(PG_SCHEMA_SQL)
                conn.commit()
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                conn.executescript(SQLITE_SCHEMA_SQL)
                conn.commit()

    def vacuum_analyze(self) -> None:
        """Execute VACUUM to optimize query plan and Visibility Map."""
        if self._is_postgres:
            conn = psycopg.connect(self.dsn, autocommit=True)
            try:
                with conn.cursor() as cur:
                    cur.execute("VACUUM ANALYZE fingerprints;")
            finally:
                conn.close()
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                conn.execute("VACUUM;")
                conn.execute("ANALYZE;")

    def insert_track(
        self,
        title: str,
        artist: str,
        duration_seconds: int,
        fingerprints: List[Tuple[int, int]],
    ) -> int:
        """Insert track record and batch fingerprints."""
        if self._is_postgres:
            with psycopg.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO tracks (title, artist, duration_seconds, hash_count)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id;
                        """,
                        (title, artist, duration_seconds, len(fingerprints)),
                    )
                    song_id = cur.fetchone()[0]

                    if fingerprints:
                        with cur.copy("COPY fingerprints (hash, song_id, offset_frames) FROM STDIN") as copy:
                            for signed_hash, offset_frame in fingerprints:
                                copy.write_row((signed_hash, song_id, offset_frame))
                conn.commit()
            return song_id
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO tracks (title, artist, duration_seconds, hash_count)
                    VALUES (?, ?, ?, ?);
                    """,
                    (title, artist, duration_seconds, len(fingerprints)),
                )
                song_id = cur.lastrowid
                if fingerprints:
                    rows = [(signed_hash, song_id, offset_frame) for signed_hash, offset_frame in fingerprints]
                    cur.executemany(
                        "INSERT INTO fingerprints (hash, song_id, offset_frames) VALUES (?, ?, ?);",
                        rows,
                    )
                conn.commit()
            return song_id

    def query_fingerprints(
        self,
        unique_hashes: List[int],
    ) -> List[Tuple[int, int, int]]:
        """Query covering index with per-hash limit."""
        if not unique_hashes:
            return []

        if self._is_postgres:
            with psycopg.connect(self.dsn, row_factory=tuple_row) as conn:
                with conn.cursor() as cur:
                    cur.execute(PG_QUERY_HASHES_SQL, {"hashes": unique_hashes})
                    return cur.fetchall()
        else:
            # SQLite query execution with parameterized IN clause
            results: List[Tuple[int, int, int]] = []
            with sqlite3.connect(self.sqlite_path) as conn:
                cur = conn.cursor()
                # Batch in chunks of 500 parameters
                chunk_size = 500
                for i in range(0, len(unique_hashes), chunk_size):
                    chunk = unique_hashes[i : i + chunk_size]
                    placeholders = ",".join(["?"] * len(chunk))
                    cur.execute(
                        f"""
                        SELECT hash, song_id, offset_frames
                        FROM fingerprints
                        WHERE hash IN ({placeholders})
                        LIMIT 50000;
                        """,
                        chunk,
                    )
                    results.extend(cur.fetchall())
            return results

    def get_track_metadata(self, song_id: int) -> Optional[dict]:
        """Fetch track title, artist, duration by song_id."""
        if self._is_postgres:
            with psycopg.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, title, artist, duration_seconds FROM tracks WHERE id = %s;",
                        (song_id,)
                    )
                    row = cur.fetchone()
                    if row:
                        return {
                            "id": row[0],
                            "title": row[1],
                            "artist": row[2],
                            "duration_seconds": row[3],
                        }
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, title, artist, duration_seconds FROM tracks WHERE id = ?;",
                    (song_id,)
                )
                row = cur.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "title": row[1],
                        "artist": row[2],
                        "duration_seconds": row[3],
                    }
        return None
