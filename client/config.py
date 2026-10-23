import json
import os
from pathlib import Path
from typing import Any, Dict


def get_app_data_dir() -> Path:
    """Return platform-specific app data directory for Song Detector."""
    app_data = os.getenv("APPDATA")
    if app_data:
        base = Path(app_data)
    else:
        base = Path.home() / ".config"
    target = base / "SongDetector"
    target.mkdir(parents=True, exist_ok=True)
    return target


CONFIG_FILE_PATH: Path = get_app_data_dir() / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "provider": "audd",
    "audd_token": "",
    "acrcloud_host": "",
    "acrcloud_access_key": "",
    "acrcloud_access_secret": "",
    "backend_url": "http://127.0.0.1:8000",
    "capture_seconds": 5,
    "hotkey": "Ctrl+Shift+S",
    "minimize_to_tray": True,
}


def load_config() -> Dict[str, Any]:
    """Load configuration from disk with fallback to defaults."""
    if not CONFIG_FILE_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            merged = DEFAULT_CONFIG.copy()
            merged.update(data)
            return merged
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(config_data: Dict[str, Any]) -> None:
    """Persist configuration dictionary to disk."""
    get_app_data_dir()
    with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)
