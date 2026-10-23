"""History tab for viewing, filtering, copying, and launching past identifications."""

import ctypes
import webbrowser
from typing import Any, Dict, List, Optional
from PyQt6 import QtGui
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QApplication,
)

from client.history_store import HistoryStore


def copy_text_to_clipboard(text: str) -> bool:
    """Two-tier clipboard copy using Qt clipboard and Win32 API fallback."""
    # 1. Qt Clipboard
    try:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text, QtGui.QClipboard.Mode.Clipboard)
    except Exception:
        pass

    # 2. Native Windows Win32 Clipboard (guarantees OS-level persistence)
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        if user32.OpenClipboard(None):
            user32.EmptyClipboard()
            encoded = text.encode("utf-16le") + b"\x00\x00"
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
            if h_mem:
                p_mem = kernel32.GlobalLock(h_mem)
                ctypes.memmove(p_mem, encoded, len(encoded))
                kernel32.GlobalUnlock(h_mem)
                user32.SetClipboardData(CF_UNICODETEXT, h_mem)
            user32.CloseClipboard()
            return True
    except Exception:
        pass
    return True


class HistoryTab(QWidget):
    """Tab view for historical recognition results."""

    def __init__(self, history_store: HistoryStore, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.history_store = history_store
        self._history_entries: List[Dict[str, Any]] = []
        self._selected_spotify_url: str = ""
        self._selected_youtube_url: str = ""
        self._selected_track_text: str = ""
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        header_layout = QHBoxLayout()
        title = QLabel("Recognition History")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #f3f4f6;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.btn_clear_history = QPushButton("Clear History")
        self.btn_clear_history.clicked.connect(self._on_clear_history)
        header_layout.addWidget(self.btn_clear_history)
        layout.addLayout(header_layout)

        # Search Bar
        self.input_search = QLineEdit()
        self.input_search.setFixedHeight(36)
        self.input_search.setPlaceholderText("Filter by track title, artist, or album...")
        self.input_search.textChanged.connect(self.refresh)
        layout.addWidget(self.input_search)

        # History Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Date/Time", "Title", "Artist", "Album", "Provider"])

        h_header = self.table.horizontalHeader()
        h_header.setStretchLastSection(False)
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)

        self.table.setColumnWidth(0, 100)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 75)

        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(self._open_spotify)
        layout.addWidget(self.table)

        # Selected Track Detail Card (YouTube, Spotify, Copy)
        self.detail_card = QFrame()
        self.detail_card.setObjectName("HistoryDetailCard")
        self.detail_card.setStyleSheet(
            "QFrame#HistoryDetailCard { background-color: #16161a; border: 1px solid #24242c; border-radius: 8px; }"
        )
        self.detail_card.setVisible(False)
        card_layout = QVBoxLayout(self.detail_card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(6)

        self.lbl_detail_title = QLabel("")
        self.lbl_detail_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #f3f4f6; line-height: 1.3;")
        self.lbl_detail_title.setWordWrap(True)
        card_layout.addWidget(self.lbl_detail_title)

        self.lbl_detail_artist = QLabel("")
        self.lbl_detail_artist.setStyleSheet("color: #9ca3af; font-size: 12px; line-height: 1.3;")
        self.lbl_detail_artist.setWordWrap(True)
        card_layout.addWidget(self.lbl_detail_artist)

        # Quick action links
        links_box = QHBoxLayout()
        links_box.setSpacing(8)

        self.btn_spotify = QPushButton("Spotify")
        self.btn_spotify.setFixedHeight(30)
        self.btn_spotify.setStyleSheet(
            "background-color: #10b981; color: #ffffff; border: 1px solid #059669; font-weight: 600; font-size: 12px; padding: 0 14px;"
        )
        self.btn_spotify.clicked.connect(self._open_spotify)
        links_box.addWidget(self.btn_spotify)

        self.btn_youtube = QPushButton("YouTube")
        self.btn_youtube.setFixedHeight(30)
        self.btn_youtube.setStyleSheet(
            "background-color: #202028; color: #f3f4f6; border: 1px solid #2e2e38; font-size: 12px; padding: 0 14px;"
        )
        self.btn_youtube.clicked.connect(self._open_youtube)
        links_box.addWidget(self.btn_youtube)

        self.btn_copy = QPushButton("Copy")
        self.btn_copy.setFixedHeight(30)
        self.btn_copy.setStyleSheet(
            "background-color: #202028; color: #f3f4f6; border: 1px solid #2e2e38; font-size: 12px; padding: 0 14px;"
        )
        self.btn_copy.clicked.connect(self._copy_track_info)
        links_box.addWidget(self.btn_copy)

        links_box.addStretch()
        card_layout.addLayout(links_box)

        layout.addWidget(self.detail_card)

    def refresh(self) -> None:
        """Fetch records from SQLite history and update table."""
        search_query = self.input_search.text().strip()
        self._history_entries = self.history_store.list_entries(limit=100, search=search_query or None)

        self.table.setRowCount(len(self._history_entries))
        for row_idx, item in enumerate(self._history_entries):
            raw_ts = str(item.get("timestamp", ""))
            short_ts = raw_ts[5:16] if len(raw_ts) >= 16 else raw_ts

            col_data = [
                short_ts,
                str(item.get("title", "")),
                str(item.get("artist", "")),
                str(item.get("album", "")),
                str(item.get("provider", "")),
            ]
            for col_idx, text_val in enumerate(col_data):
                t_item = QTableWidgetItem(text_val)
                t_item.setToolTip(f"{item.get('title', '')} - {item.get('artist', '')} ({item.get('album', '')})")
                self.table.setItem(row_idx, col_idx, t_item)

        if self._history_entries:
            self.table.selectRow(0)
        else:
            self.detail_card.setVisible(False)

    def _on_selection_changed(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.detail_card.setVisible(False)
            return

        row_idx = selected_rows[0].row()
        if row_idx >= len(self._history_entries):
            return

        item = self._history_entries[row_idx]
        title = item.get("title", "Unknown Title")
        artist = item.get("artist", "Unknown Artist")
        album = item.get("album", "")
        provider = item.get("provider", "Cloud API")
        spotify_url = item.get("spotify_url", "")
        youtube_url = item.get("youtube_url", "")

        self.lbl_detail_title.setText(f"🎵 {title}")
        self.lbl_detail_artist.setText(f"Artist: {artist}   •   Album: {album or 'Single'}   •   Provider: {provider}")

        self._selected_spotify_url = spotify_url or f"https://open.spotify.com/search/{title} {artist}"
        self._selected_youtube_url = youtube_url or f"https://www.youtube.com/results?search_query={title} {artist}"
        self._selected_track_text = f"{title} - {artist}"

        self.detail_card.setVisible(True)

    def _open_spotify(self) -> None:
        if self._selected_spotify_url:
            webbrowser.open(self._selected_spotify_url)

    def _open_youtube(self) -> None:
        if self._selected_youtube_url:
            webbrowser.open(self._selected_youtube_url)

    def _copy_track_info(self) -> None:
        if not self._selected_track_text:
            return

        copy_text_to_clipboard(self._selected_track_text)

        self.btn_copy.setText("✓ Copied!")
        self.btn_copy.setStyleSheet(
            "background-color: #10b981; color: #ffffff; border: 1px solid #059669; font-size: 12px; font-weight: 600; padding: 0 14px;"
        )
        QTimer.singleShot(2000, self._reset_copy_button)

    def _reset_copy_button(self) -> None:
        self.btn_copy.setText("Copy")
        self.btn_copy.setStyleSheet(
            "background-color: #202028; color: #f3f4f6; border: 1px solid #2e2e38; font-size: 12px; padding: 0 14px;"
        )

    def _on_clear_history(self) -> None:
        self.history_store.clear_all()
        self.refresh()
