"""Identify tab for audio capture trigger and matched song display."""

import webbrowser
from typing import Any, Dict, List, Optional
from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFrame,
    QScrollArea,
)

from client.gui.visualizer import AudioVisualizerWidget


class IdentifyTab(QWidget):
    """Tab view for triggering recognition and inspecting matched track details."""

    identify_requested = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.current_spotify_url: str = ""
        self.current_youtube_url: str = ""
        self._init_ui()

    def _init_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(12)

        # Header
        header = QLabel("Audio Identification")
        header.setStyleSheet("font-size: 18px; font-weight: 700; color: #f3f4f6;")
        layout.addWidget(header)

        sub = QLabel("Capture desktop audio playback via WASAPI loopback and match against music databases.")
        sub.setStyleSheet("color: #9ca3af; font-size: 12px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        # Central Identify Button
        btn_container = QHBoxLayout()
        btn_container.addStretch()

        self.btn_identify = QPushButton("Identify Music Now")
        self.btn_identify.setObjectName("PrimaryButton")
        self.btn_identify.setFixedHeight(42)
        self.btn_identify.setMinimumWidth(200)
        self.btn_identify.setStyleSheet("font-size: 14px; font-weight: 600; padding: 0 20px;")
        self.btn_identify.clicked.connect(self.identify_requested.emit)
        btn_container.addWidget(self.btn_identify)

        btn_container.addStretch()
        layout.addLayout(btn_container)

        # Visualizer & Status
        self.visualizer = AudioVisualizerWidget()
        self.visualizer.setFixedHeight(28)
        layout.addWidget(self.visualizer)

        self.lbl_status = QLabel("Ready. Press hotkey (Ctrl+Shift+S / F9) or click Identify Music Now.")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #9ca3af; font-size: 12px;")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        # Result Card
        self.card_result = QFrame()
        self.card_result.setObjectName("CardResult")
        self.card_result.setStyleSheet(
            "QFrame#CardResult { background-color: #16161a; border: 1px solid #24242c; border-radius: 8px; }"
        )
        card_layout = QVBoxLayout(self.card_result)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(6)

        self.lbl_result_title = QLabel("No Song Identified Yet")
        self.lbl_result_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #f3f4f6; line-height: 1.3;")
        self.lbl_result_title.setWordWrap(True)
        card_layout.addWidget(self.lbl_result_title)

        self.lbl_result_artist = QLabel("Play audio in any app and click Identify Music Now to scan.")
        self.lbl_result_artist.setStyleSheet("color: #9ca3af; font-size: 12px; line-height: 1.3;")
        self.lbl_result_artist.setWordWrap(True)
        card_layout.addWidget(self.lbl_result_artist)

        self.lbl_result_meta = QLabel("")
        self.lbl_result_meta.setStyleSheet("color: #6b7280; font-size: 11px;")
        self.lbl_result_meta.setWordWrap(True)
        card_layout.addWidget(self.lbl_result_meta)

        # Action links
        self.action_links_layout = QHBoxLayout()
        self.action_links_layout.setSpacing(10)

        self.btn_spotify = QPushButton("Search on Spotify")
        self.btn_spotify.setFixedHeight(28)
        self.btn_spotify.setStyleSheet("font-size: 12px; padding: 0 12px;")
        self.btn_spotify.setVisible(False)
        self.btn_spotify.clicked.connect(self._open_spotify)
        self.action_links_layout.addWidget(self.btn_spotify)

        self.btn_youtube = QPushButton("Search on YouTube")
        self.btn_youtube.setFixedHeight(28)
        self.btn_youtube.setStyleSheet("font-size: 12px; padding: 0 12px;")
        self.btn_youtube.setVisible(False)
        self.btn_youtube.clicked.connect(self._open_youtube)
        self.action_links_layout.addWidget(self.btn_youtube)

        self.btn_open_settings = QPushButton("Open Settings")
        self.btn_open_settings.setObjectName("PrimaryButton")
        self.btn_open_settings.setFixedHeight(28)
        self.btn_open_settings.setStyleSheet("font-size: 12px; padding: 0 14px;")
        self.btn_open_settings.setVisible(False)
        self.btn_open_settings.clicked.connect(self.settings_requested.emit)
        self.action_links_layout.addWidget(self.btn_open_settings)

        self.action_links_layout.addStretch()
        card_layout.addLayout(self.action_links_layout)

        layout.addWidget(self.card_result)
        layout.addStretch()

        # Wrap in scroll area for small screens
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")
        scroll.setWidget(container)

        outer_layout.addWidget(scroll)

    def set_listening(self, is_listening: bool) -> None:
        if is_listening:
            self.btn_identify.setEnabled(False)
            self.btn_identify.setText("Listening...")
            self.visualizer.set_active(True)
            self.lbl_status.setText("Capturing system audio via WASAPI...")
        else:
            self.btn_identify.setEnabled(True)
            self.btn_identify.setText("Identify Music Now")
            self.visualizer.set_active(False)

    def set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def show_result(self, result: Dict[str, Any]) -> None:
        self.set_listening(False)
        self.btn_open_settings.setVisible(False)

        if result.get("matched"):
            title = result.get("title", "Unknown Title")
            artist = result.get("artist", "Unknown Artist")
            album = result.get("album", "")
            provider = result.get("provider", "Cloud API")
            spotify_url = result.get("spotify_url", "")
            youtube_url = result.get("youtube_url", "")

            self.lbl_result_title.setText(f"🎵 {title}")
            self.lbl_result_artist.setText(f"Artist: {artist}")
            self.lbl_result_meta.setText(f"Album: {album or 'Single'}  •  Provider: {provider}")

            self.current_spotify_url = spotify_url or f"https://open.spotify.com/search/{title} {artist}"
            self.current_youtube_url = youtube_url or f"https://www.youtube.com/results?search_query={title} {artist}"

            self.btn_spotify.setVisible(True)
            self.btn_youtube.setVisible(True)
        else:
            self.lbl_result_title.setText("No Match Found")
            self.lbl_result_artist.setText("Audio was not recognized in the selected music database.")
            self.lbl_result_meta.setText("Tip: Try identifying during a chorus or clean vocal/melody section.")
            self.btn_spotify.setVisible(False)
            self.btn_youtube.setVisible(False)

    def show_failure(self, error_msg: str) -> None:
        self.set_listening(False)
        self.btn_open_settings.setVisible(False)
        self.lbl_status.setText(f"Failed: {error_msg[:80]}")

    def show_missing_credentials(self, provider_name: str, missing_fields: List[str]) -> None:
        self.set_listening(False)
        self.lbl_status.setText(f"Configuration required for {provider_name}.")
        self.lbl_result_title.setText("Configuration Required")
        field_list = ", ".join(missing_fields)
        self.lbl_result_artist.setText(
            f"Missing {provider_name} parameters: {field_list}."
        )
        self.lbl_result_meta.setText(
            "Click Open Settings below to enter your credentials and try again."
        )
        self.btn_spotify.setVisible(False)
        self.btn_youtube.setVisible(False)
        self.btn_open_settings.setVisible(True)

    def _open_spotify(self) -> None:
        if self.current_spotify_url:
            webbrowser.open(self.current_spotify_url)

    def _open_youtube(self) -> None:
        if self.current_youtube_url:
            webbrowser.open(self.current_youtube_url)
