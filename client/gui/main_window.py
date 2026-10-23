"""Main window and application entrypoint for Song Detector."""

import ctypes
from ctypes import wintypes
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import certifi
os.environ["SSL_CERT_FILE"] = certifi.where()

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QStackedWidget,
    QFrame,
    QSystemTrayIcon,
    QMenu,
)

from client.config import load_config
from client.history_store import HistoryStore
from client.capture import WasapiLoopbackCapture
from client.gui.styles import DARK_THEME_QSS
from client.gui.worker import RecognitionWorker
from client.gui.tabs.identify_tab import IdentifyTab
from client.gui.tabs.history_tab import HistoryTab
from client.gui.tabs.settings_tab import SettingsTab


def check_missing_credentials(config: Dict[str, Any]) -> tuple[str, List[str]]:
    """Determine whether the configured provider lacks required API credentials."""
    provider = config.get("provider", "audd").lower()
    missing: List[str] = []

    if provider == "audd":
        if not config.get("audd_token", "").strip():
            missing.append("API Token")
        return "AudD", missing

    elif provider == "acrcloud":
        if not config.get("acrcloud_host", "").strip():
            missing.append("Host URL")
        if not config.get("acrcloud_access_key", "").strip():
            missing.append("Access Key")
        if not config.get("acrcloud_access_secret", "").strip():
            missing.append("Access Secret")
        return "ACRCloud", missing

    elif provider == "local":
        if not config.get("backend_url", "").strip():
            missing.append("Backend URL")
        return "Local Backend", missing

    return provider.upper(), missing


class SongDetectorMainWindow(QMainWindow):
    """Main desktop application window coordinating navigation, capture, and tray."""

    hotkey_triggered_signal = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HearThis")
        self.resize(720, 540)
        self.setMinimumSize(640, 480)

        # Set Window Icon
        icon_path = Path(__file__).resolve().parent.parent.parent / "assets" / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(icon_path)))

        self.config = load_config()
        self.history_store = HistoryStore()
        self.capture = WasapiLoopbackCapture()
        self.capture.start_keepalive()

        self.worker: Optional[RecognitionWorker] = None
        self.hotkey_thread_running = True

        self._apply_dark_style()
        self._init_ui()
        self._init_tray()
        self._register_hotkeys()

        self.hotkey_triggered_signal.connect(self.on_identify_clicked)

    def _apply_dark_style(self) -> None:
        self.setStyleSheet(DARK_THEME_QSS)

    def _init_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Sidebar Navigation
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 24, 16, 24)
        sidebar_layout.setSpacing(8)

        # App Logo & Title
        title_box = QHBoxLayout()
        title_box.setSpacing(10)
        icon_path = Path(__file__).resolve().parent.parent.parent / "assets" / "icon.png"
        if icon_path.exists():
            logo_lbl = QLabel()
            pixmap = QtGui.QPixmap(str(icon_path)).scaled(
                24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            logo_lbl.setPixmap(pixmap)
            title_box.addWidget(logo_lbl)

        app_title = QLabel("HearThis")
        app_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f3f4f6;")
        title_box.addWidget(app_title)
        title_box.addStretch()

        sidebar_layout.addLayout(title_box)
        sidebar_layout.addSpacing(16)

        self.btn_nav_identify = QPushButton("Identify Music")
        self.btn_nav_identify.setObjectName("NavButton")
        self.btn_nav_identify.setCheckable(True)
        self.btn_nav_identify.setChecked(True)
        self.btn_nav_identify.clicked.connect(lambda: self._switch_tab(0))
        sidebar_layout.addWidget(self.btn_nav_identify)

        self.btn_nav_history = QPushButton("History")
        self.btn_nav_history.setObjectName("NavButton")
        self.btn_nav_history.setCheckable(True)
        self.btn_nav_history.clicked.connect(lambda: self._switch_tab(1))
        sidebar_layout.addWidget(self.btn_nav_history)

        self.btn_nav_settings = QPushButton("Settings")
        self.btn_nav_settings.setObjectName("NavButton")
        self.btn_nav_settings.setCheckable(True)
        self.btn_nav_settings.clicked.connect(lambda: self._switch_tab(2))
        sidebar_layout.addWidget(self.btn_nav_settings)

        sidebar_layout.addStretch()

        hotkey_label = QLabel("Global Hotkeys:\nCtrl+Shift+S\nF9 or F8")
        hotkey_label.setStyleSheet("color: #6b7280; font-size: 11px; line-height: 1.4;")
        sidebar_layout.addWidget(hotkey_label)

        main_layout.addWidget(sidebar)

        # 2. Content Stack with Dedicated Tab Views
        self.stack = QStackedWidget()
        self.tab_identify = IdentifyTab()
        self.tab_identify.identify_requested.connect(self.on_identify_clicked)
        self.tab_identify.settings_requested.connect(self._go_to_settings)

        self.tab_history = HistoryTab(self.history_store)

        self.tab_settings = SettingsTab(self.config)
        self.tab_settings.settings_saved.connect(self._on_settings_saved)

        self.stack.addWidget(self.tab_identify)
        self.stack.addWidget(self.tab_history)
        self.stack.addWidget(self.tab_settings)

        main_layout.addWidget(self.stack)

    def _switch_tab(self, index: int) -> None:
        self.btn_nav_identify.setChecked(index == 0)
        self.btn_nav_history.setChecked(index == 1)
        self.btn_nav_settings.setChecked(index == 2)
        self.stack.setCurrentIndex(index)
        if index == 1:
            self.tab_history.refresh()

    def _go_to_settings(self) -> None:
        self._switch_tab(2)
        provider = self.config.get("provider", "audd").lower()
        self.tab_settings.focus_provider(provider)

    def _on_settings_saved(self, updated_config: Dict[str, Any]) -> None:
        self.config = updated_config

    # --- Recognition Execution ---
    def on_identify_clicked(self) -> None:
        if self.worker and self.worker.isRunning():
            return

        provider_name, missing = check_missing_credentials(self.config)
        if missing:
            self.tab_identify.show_missing_credentials(provider_name, missing)
            from client.notifier import show_windows_toast
            show_windows_toast(
                "HearThis - Configuration Required",
                f"{provider_name} requires: {', '.join(missing)}.",
            )
            return

        self.tab_identify.set_listening(True)

        self.worker = RecognitionWorker(self.capture, self.config)
        self.worker.status_changed.connect(self.tab_identify.set_status)
        self.worker.recognition_finished.connect(self._on_recognition_finished)
        self.worker.recognition_failed.connect(self._on_recognition_failed)
        self.worker.start()

    def _on_recognition_finished(self, result: Dict[str, Any]) -> None:
        self.tab_identify.show_result(result)

        if result.get("matched"):
            title = result.get("title", "Unknown Title")
            artist = result.get("artist", "Unknown Artist")
            album = result.get("album", "")
            provider = result.get("provider", "Cloud API")
            spotify_url = result.get("spotify_url", "") or f"https://open.spotify.com/search/{title} {artist}"
            youtube_url = result.get("youtube_url", "") or f"https://www.youtube.com/results?search_query={title} {artist}"

            self.history_store.add_entry(
                title=title,
                artist=artist,
                album=album,
                provider=provider,
                spotify_url=spotify_url,
                youtube_url=youtube_url,
            )

    def _on_recognition_failed(self, error_msg: str) -> None:
        self.tab_identify.show_failure(error_msg)

    # --- System Tray & Background Hotkey ---
    def _init_tray(self) -> None:
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = Path(__file__).resolve().parent.parent.parent / "assets" / "icon.png"
        if icon_path.exists():
            self.tray_icon.setIcon(QtGui.QIcon(str(icon_path)))
        else:
            self.tray_icon.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPlay))

        tray_menu = QMenu()
        act_open = tray_menu.addAction("Open HearThis")
        act_open.triggered.connect(self.showNormal)

        act_identify = tray_menu.addAction("Identify Music Now")
        act_identify.triggered.connect(self.on_identify_clicked)

        tray_menu.addSeparator()
        act_exit = tray_menu.addAction("Exit")
        act_exit.triggered.connect(self._on_exit_app)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.showNormal()
                self.activateWindow()

    def _register_hotkeys(self) -> None:
        """Register event-driven system hotkeys via Windows RegisterHotKey API."""
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            MOD_CONTROL = 0x0002
            MOD_SHIFT = 0x0004
            MOD_NOREPEAT = 0x4000
            VK_S = 0x53
            VK_F9 = 0x78
            VK_F8 = 0x77

            # Ctrl+Shift+S
            user32.RegisterHotKey(hwnd, 101, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_S)
            # F9
            user32.RegisterHotKey(hwnd, 102, MOD_NOREPEAT, VK_F9)
            # F8
            user32.RegisterHotKey(hwnd, 103, MOD_NOREPEAT, VK_F8)
        except Exception:
            pass

    def _unregister_hotkeys(self) -> None:
        """Release hotkey registrations."""
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            user32.UnregisterHotKey(hwnd, 101)
            user32.UnregisterHotKey(hwnd, 102)
            user32.UnregisterHotKey(hwnd, 103)
        except Exception:
            pass

    def nativeEvent(self, event_type: Any, message: Any) -> Tuple[bool, int]:
        """Intercept native Windows message pump events for WM_HOTKEY."""
        try:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312:  # WM_HOTKEY
                self.hotkey_triggered_signal.emit()
                return True, 0
        except Exception:
            pass
        return False, 0

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.config.get("minimize_to_tray", True):
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "HearThis",
                "Running in system tray. Press Ctrl+Shift+S or F9 anytime.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
        else:
            self._on_exit_app()

    def _on_exit_app(self) -> None:
        self._unregister_hotkeys()
        self.capture.stop_keepalive()
        self.tray_icon.hide()
        QApplication.quit()


def main() -> None:
    # Reset any preemptive MTA COM apartment initialized by audio drivers during import
    # so Qt OleInitialize() can initialize Single-Threaded Apartment (STA) mode cleanly.
    try:
        ctypes.windll.ole32.CoUninitialize()
    except Exception:
        pass

    # Set Windows AppUserModelID so taskbar displays the custom icon
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "HearThis.AudioIdentifier.1.0"
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    icon_path = Path(__file__).resolve().parent.parent.parent / "assets" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QtGui.QIcon(str(icon_path)))

    window = SongDetectorMainWindow()
    window.show()
    sys.exit(app.exec())
