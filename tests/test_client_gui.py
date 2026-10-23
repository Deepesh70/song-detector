import tempfile
from pathlib import Path
from client.config import load_config, save_config
from client.history_store import HistoryStore
from client.direct_recognizer import pcm_to_wav_bytes
import numpy as np


def test_config_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_path = Path(tmpdir) / "config.json"
        from client import config
        original_path = config.CONFIG_FILE_PATH
        config.CONFIG_FILE_PATH = test_path
        try:
            cfg = load_config()
            assert "provider" in cfg
            cfg["audd_token"] = "test_token_123"
            save_config(cfg)

            loaded = load_config()
            assert loaded["audd_token"] == "test_token_123"
        finally:
            config.CONFIG_FILE_PATH = original_path


def test_history_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_history.db"
        store = HistoryStore(db_path=db_path)

        store.add_entry(
            title="Bohemian Rhapsody",
            artist="Queen",
            album="A Night at the Opera",
            provider="AudD",
        )
        store.add_entry(
            title="Blinding Lights",
            artist="The Weeknd",
            album="After Hours",
            provider="ACRCloud",
        )

        entries = store.list_entries()
        assert len(entries) == 2
        assert entries[0]["title"] == "Blinding Lights"

        filtered = store.list_entries(search="Queen")
        assert len(filtered) == 1
        assert filtered[0]["artist"] == "Queen"

        store.clear_all()
        assert len(store.list_entries()) == 0


def test_pcm_to_wav_bytes():
    silence = np.zeros(11025 * 2, dtype=np.float32)
    wav_bytes = pcm_to_wav_bytes(silence, sample_rate=11025)
    assert len(wav_bytes) > 44
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"


def test_gui_package_imports():
    from client.gui.styles import DARK_THEME_QSS
    assert "QMainWindow" in DARK_THEME_QSS
    assert "#10b981" in DARK_THEME_QSS

    from client.gui.tabs import IdentifyTab, HistoryTab, SettingsTab
    assert IdentifyTab is not None
    assert HistoryTab is not None
    assert SettingsTab is not None

    from client.gui.worker import RecognitionWorker
    assert RecognitionWorker is not None

    from client.gui import SongDetectorMainWindow
    assert SongDetectorMainWindow is not None


def test_missing_credentials_detection():
    from client.gui.main_window import check_missing_credentials

    # AudD without token
    cfg_audd_empty = {"provider": "audd", "audd_token": ""}
    provider, missing = check_missing_credentials(cfg_audd_empty)
    assert provider == "AudD"
    assert "API Token" in missing

    # AudD with token
    cfg_audd_ok = {"provider": "audd", "audd_token": "valid_token"}
    provider, missing = check_missing_credentials(cfg_audd_ok)
    assert missing == []

    # ACRCloud missing partial
    cfg_acr = {
        "provider": "acrcloud",
        "acrcloud_host": "host.com",
        "acrcloud_access_key": "",
        "acrcloud_access_secret": "",
    }
    provider, missing = check_missing_credentials(cfg_acr)
    assert provider == "ACRCloud"
    assert "Access Key" in missing
    assert "Access Secret" in missing
    assert "Host URL" not in missing


def test_provider_links_and_ui_elements():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    from client.gui.tabs.settings_tab import SettingsTab
    from client.gui.tabs.identify_tab import IdentifyTab

    # Instantiation check for tabs
    settings = SettingsTab({"provider": "audd", "audd_token": ""})
    assert hasattr(settings, "frame_audd")
    assert hasattr(settings, "frame_acr")

    identify = IdentifyTab()
    assert hasattr(identify, "btn_get_api_key")
    identify.show_missing_credentials("AudD", ["API Token"])
    assert not identify.btn_get_api_key.isHidden()
    assert identify.current_provider_url == "https://audd.io"

    identify.show_missing_credentials("ACRCloud", ["Host URL", "Access Key"])
    assert not identify.btn_get_api_key.isHidden()
    assert identify.current_provider_url == "https://console.acrcloud.com"




