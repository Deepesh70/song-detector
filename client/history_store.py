import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from client.config import get_app_data_dir

HISTORY_DB_PATH: Path = get_app_data_dir() / "history.db"


class HistoryStore:
    """Thread-safe SQLite store for song identification history."""

    def __init__(self, db_path: Path = HISTORY_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS recognition_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        title TEXT NOT NULL,
                        artist TEXT NOT NULL,
                        album TEXT,
                        provider TEXT NOT NULL,
                        confidence REAL DEFAULT 1.0,
                        spotify_url TEXT,
                        youtube_url TEXT
                    )
                    """
                )
        finally:
            conn.close()

    def add_entry(
        self,
        title: str,
        artist: str,
        album: str = "",
        provider: str = "local",
        confidence: float = 1.0,
        spotify_url: str = "",
        youtube_url: str = "",
    ) -> int:
        """Insert a recognized track into the history log."""
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO recognition_history 
                    (timestamp, title, artist, album, provider, confidence, spotify_url, youtube_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (timestamp_str, title, artist, album, provider, confidence, spotify_url, youtube_url),
                )
                return cursor.lastrowid
        finally:
            conn.close()

    def list_entries(self, limit: int = 100, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve recent recognition history entries, optionally filtered by keyword."""
        conn = self._get_connection()
        try:
            with conn:
                if search:
                    term = f"%{search}%"
                    cursor = conn.execute(
                        """
                        SELECT * FROM recognition_history
                        WHERE title LIKE ? OR artist LIKE ? OR album LIKE ?
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (term, term, term, limit),
                    )
                else:
                    cursor = conn.execute(
                        """
                        SELECT * FROM recognition_history
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (limit,),
                    )

                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        finally:
            conn.close()

    def clear_all(self) -> None:
        """Clear all historical entries."""
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM recognition_history")
        finally:
            conn.close()
