"""Settings tab for provider configuration, credentials, and capture parameters."""

import webbrowser
from typing import Any, Dict, Optional
from PyQt6.QtCore import pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QComboBox,
    QFrame,
)

from client.config import save_config


class SettingsTab(QWidget):
    """Tab view for editing client recognition mode and cloud API credentials."""

    settings_saved = pyqtSignal(dict)

    def __init__(self, config: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        header = QLabel("Recognition Settings")
        header.setStyleSheet("font-size: 20px; font-weight: 700; color: #f3f4f6;")
        layout.addWidget(header)

        # Provider Selection
        layout.addWidget(QLabel("Recognition Provider:"))
        self.combo_provider = QComboBox()
        self.combo_provider.setFixedHeight(36)
        self.combo_provider.addItems(
            ["AudD (Direct Cloud)", "ACRCloud (Direct Cloud)"]
        )
        current_p = self.config.get("provider", "audd").lower()
        if current_p == "acrcloud":
            self.combo_provider.setCurrentIndex(1)
        else:
            self.combo_provider.setCurrentIndex(0)
        self.combo_provider.currentIndexChanged.connect(self._on_provider_changed)
        layout.addWidget(self.combo_provider)

        # AudD Form Frame
        self.frame_audd = QFrame()
        audd_layout = QVBoxLayout(self.frame_audd)
        audd_layout.setContentsMargins(0, 4, 0, 4)
        audd_layout.setSpacing(6)
        audd_layout.addWidget(QLabel("AudD API Token:"))
        self.input_audd_token = QLineEdit(self.config.get("audd_token", ""))
        self.input_audd_token.setFixedHeight(36)
        self.input_audd_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_audd_token.setPlaceholderText("Enter your AudD personal API token")
        audd_layout.addWidget(self.input_audd_token)

        audd_help_row = QHBoxLayout()
        lbl_audd_help = QLabel("Don't have a token? Register for free on AudD:")
        lbl_audd_help.setStyleSheet("color: #9ca3af; font-size: 12px;")
        btn_get_audd = QPushButton("Get Free AudD Token")
        btn_get_audd.setFixedHeight(28)
        btn_get_audd.setStyleSheet("font-size: 11px; padding: 0 12px;")
        btn_get_audd.clicked.connect(lambda: webbrowser.open("https://audd.io"))
        audd_help_row.addWidget(lbl_audd_help)
        audd_help_row.addWidget(btn_get_audd)
        audd_help_row.addStretch()
        audd_layout.addLayout(audd_help_row)

        layout.addWidget(self.frame_audd)

        # ACRCloud Form Frame
        self.frame_acr = QFrame()
        acr_layout = QVBoxLayout(self.frame_acr)
        acr_layout.setContentsMargins(0, 4, 0, 4)
        acr_layout.setSpacing(6)
        acr_layout.addWidget(QLabel("ACRCloud Host:"))
        self.input_acr_host = QLineEdit(self.config.get("acrcloud_host", ""))
        self.input_acr_host.setFixedHeight(36)
        self.input_acr_host.setPlaceholderText("identify-eu-west-1.acrcloud.com")
        acr_layout.addWidget(self.input_acr_host)

        acr_layout.addWidget(QLabel("ACRCloud Access Key:"))
        self.input_acr_key = QLineEdit(self.config.get("acrcloud_access_key", ""))
        self.input_acr_key.setFixedHeight(36)
        acr_layout.addWidget(self.input_acr_key)

        acr_layout.addWidget(QLabel("ACRCloud Access Secret:"))
        self.input_acr_secret = QLineEdit(self.config.get("acrcloud_access_secret", ""))
        self.input_acr_secret.setFixedHeight(36)
        self.input_acr_secret.setEchoMode(QLineEdit.EchoMode.Password)
        acr_layout.addWidget(self.input_acr_secret)

        acr_help_row = QHBoxLayout()
        lbl_acr_help = QLabel("Need project credentials? Open ACRCloud console:")
        lbl_acr_help.setStyleSheet("color: #9ca3af; font-size: 12px;")
        btn_get_acr = QPushButton("Get ACRCloud Credentials")
        btn_get_acr.setFixedHeight(28)
        btn_get_acr.setStyleSheet("font-size: 11px; padding: 0 12px;")
        btn_get_acr.clicked.connect(lambda: webbrowser.open("https://console.acrcloud.com"))
        acr_help_row.addWidget(lbl_acr_help)
        acr_help_row.addWidget(btn_get_acr)
        acr_help_row.addStretch()
        acr_layout.addLayout(acr_help_row)

        layout.addWidget(self.frame_acr)

        # Capture Duration
        layout.addWidget(QLabel("Recording Clip Duration (Seconds):"))
        self.combo_duration = QComboBox()
        self.combo_duration.setFixedHeight(36)
        self.combo_duration.addItems(["3 Seconds", "5 Seconds (Recommended)", "8 Seconds", "10 Seconds"])
        dur = self.config.get("capture_seconds", 5)
        dur_idx = 1
        if dur == 3:
            dur_idx = 0
        elif dur == 8:
            dur_idx = 2
        elif dur == 10:
            dur_idx = 3
        self.combo_duration.setCurrentIndex(dur_idx)
        layout.addWidget(self.combo_duration)

        # Save & Feedback
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Save Settings")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.clicked.connect(self._on_save_settings)
        btn_layout.addWidget(self.btn_save)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #10b981; font-weight: 500;")
        btn_layout.addWidget(self.lbl_status)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()
        self._update_provider_form_visibility()

    def _on_provider_changed(self) -> None:
        self._update_provider_form_visibility()

    def _update_provider_form_visibility(self) -> None:
        idx = self.combo_provider.currentIndex()
        self.frame_audd.setVisible(idx == 0)
        self.frame_acr.setVisible(idx == 1)

    def focus_provider(self, provider: str) -> None:
        """Select provider and focus its first empty configuration input."""
        p = provider.lower()
        if p == "acrcloud":
            self.combo_provider.setCurrentIndex(1)
            if not self.input_acr_host.text().strip():
                self.input_acr_host.setFocus()
            elif not self.input_acr_key.text().strip():
                self.input_acr_key.setFocus()
            else:
                self.input_acr_secret.setFocus()
        else:
            self.combo_provider.setCurrentIndex(0)
            self.input_audd_token.setFocus()

    def _on_save_settings(self) -> None:
        idx = self.combo_provider.currentIndex()
        providers = ["audd", "acrcloud"]
        durations = [3, 5, 8, 10]

        self.config["provider"] = providers[idx]
        self.config["audd_token"] = self.input_audd_token.text().strip()
        self.config["acrcloud_host"] = self.input_acr_host.text().strip()
        self.config["acrcloud_access_key"] = self.input_acr_key.text().strip()
        self.config["acrcloud_access_secret"] = self.input_acr_secret.text().strip()
        self.config["capture_seconds"] = durations[self.combo_duration.currentIndex()]

        save_config(self.config)
        self.settings_saved.emit(self.config)

        self.lbl_status.setText("Settings saved successfully.")
        QTimer.singleShot(3000, lambda: self.lbl_status.setText(""))
