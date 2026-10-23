# AGENTS.md

## Project Overview
HearThis is a production-grade desktop audio identification system. It captures system audio on Windows using WASAPI loopback without microphone bleed, applies RMS silence gating and polyphase anti-aliasing resampling, and identifies tracks via direct cloud API providers (AudD and ACRCloud).

---

## Technology Stack

- **Client Runtime**: Python 3.11+
  - Windows Audio Capture: `soundcard` (WASAPI shared-mode loopback)
  - Resampling & DSP: `numpy`, `scipy` (polyphase anti-aliasing sinc resampler, silence gating)
  - GUI Framework: `PyQt6` (dark theme, WCAG AA, non-blocking QThread worker)
  - Audio Serialization: Python standard library `wave` (in-memory RIFF PCM)
  - Network Client: `httpx` (HTTP/1.1 keep-alive connection reuse)
  - Local Storage: SQLite (`HistoryStore` at `%APPDATA%/SongDetector/history.db`)

---

## Repository Structure

```
song-detector/
├── AGENTS.md                  # Project stack, commands, standards, and conventions
├── README.md                  # System overview and quickstart guide
├── requirements.txt           # Client application dependencies
├── HearThis.spec              # PyInstaller executable build specification
├── installer/                 # Windows Inno Setup installer script
│   └── HearThis.iss
├── assets/                    # Application icons (.ico mipmaps, .png)
├── client/                    # Desktop capture and client-side processing
│   ├── gui_app.py             # Desktop GUI launcher entrypoint
│   ├── gui/                   # Modular desktop GUI architecture
│   │   ├── styles.py          # WCAG AA dark theme QSS tokens
│   │   ├── visualizer.py      # Audio spectrum activity visualizer widget
│   │   ├── worker.py          # Non-blocking WASAPI recognition QThread worker
│   │   ├── tabs/              # Decomposed tab view components
│   │   │   ├── identify_tab.py# Hero trigger, visualizer, matched result card
│   │   │   ├── history_tab.py # SQLite table, live search, quick actions & Win32 copy
│   │   │   └── settings_tab.py# Provider selector & credential management
│   │   └── main_window.py     # Main window coordinator, tray icon, and global hotkeys
│   ├── config.py              # Local JSON configuration manager (%APPDATA%/SongDetector)
│   ├── history_store.py       # Local SQLite history database (recognition_history)
│   ├── direct_recognizer.py   # Direct client-side AudD & ACRCloud API recognition engine
│   ├── capture.py             # WASAPI loopback recording with silence keep-alive
│   ├── preprocessor.py        # RMS silence gate and polyphase resampler (48kHz -> 11,025Hz)
│   ├── notifier.py            # Windows 10/11 native toast notifications
│   └── agent.py               # CLI runner and hotkey dispatcher
└── tests/                     # Unit and integration test suites
    ├── test_client_gui.py     # GUI configuration, history store, and tab component tests
    └── test_resampler.py      # Polyphase anti-aliasing attenuation and RMS gate checks
```

---

## Development Commands

### Environment Setup
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Running Tests
```bash
# Run complete test suite
pytest -v
```

### Running the Desktop App
```bash
# Launch PyQt6 Desktop GUI
python client/gui_app.py

# Launch CLI loopback listener
python client/agent.py --listen
```

---

## Code Style & Engineering Standards

1. **Strict Type Annotations**: Every function and method must specify complete type annotations (`typing` module / standard modern Python typing). No bare `Any`.
2. **Deterministic DSP & Audio Processing**:
   - Signal processing functions must operate strictly on explicit `numpy.ndarray` buffers.
   - All sample rate and silence threshold parameters must reference shared configuration constants.
3. **Security & Secrets**:
   - User provider tokens/credentials reside strictly in local `%APPDATA%/SongDetector/config.json`.
   - Never print or commit credentials to logs or repository.
