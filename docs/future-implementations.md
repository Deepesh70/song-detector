# Implementation Status & Future Roadmap

This document tracks completed engineering milestones in HearThis and outlines planned technical enhancements for future releases.

---

## 1. Current Implementation Status (v1.1.0)

| Subsystem / Feature | Status | Description | Implementation File |
| :--- | :--- | :--- | :--- |
| **WASAPI Loopback Capture** | **Complete** | Captures 48 kHz stereo system audio via COM `IAudioCaptureClient` without microphone bleed. | [`src/wasapi_capture.cpp`](file:///c:/Users/aadit/Desktop/song-detector/src/wasapi_capture.cpp) |
| **Audio Clock Keep-Alive** | **Complete** | Silent background render stream preventing WASAPI loopback starvation during digital silence. | [`src/wasapi_capture.cpp`](file:///c:/Users/aadit/Desktop/song-detector/src/wasapi_capture.cpp) |
| **Stereo Downmixing** | **Complete** | Single-pass floating point average downmix from stereo to mono. | [`src/audio_processor.cpp`](file:///c:/Users/aadit/Desktop/song-detector/src/audio_processor.cpp) |
| **RMS Silence Energy Gate** | **Complete** | Computes RMS energy against a $-50\text{ dBFS}$ floor to reject silence and avoid network waste. | [`src/audio_processor.cpp`](file:///c:/Users/aadit/Desktop/song-detector/src/audio_processor.cpp) |
| **RIFF WAV Serialization** | **Complete** | Converts floats to 16-bit linear PCM and serializes a 44-byte standard RIFF header in memory. | [`src/audio_processor.cpp`](file:///c:/Users/aadit/Desktop/song-detector/src/audio_processor.cpp) |
| **ACRCloud Client** | **Complete** | Computes HMAC-SHA1 signatures via Windows `bcrypt.dll` and Base64 via `crypt32.dll`. | [`src/api_client.cpp`](file:///c:/Users/aadit/Desktop/song-detector/src/api_client.cpp) |
| **AudD Client** | **Complete** | Multipart form-data HTTP client over Windows `winhttp.dll`. | [`src/api_client.cpp`](file:///c:/Users/aadit/Desktop/song-detector/src/api_client.cpp) |
| **Config Persistence** | **Complete** | Automatic persistence of credentials, active provider, and duration to `%APPDATA%/SongDetector/native_config.txt`. | [`src/main.cpp`](file:///c:/Users/aadit/Desktop/song-detector/src/main.cpp) |
| **Win32 Immersive UI** | **Complete** | Dark-mode native Win32 window (Segoe UI typography, DWM immersive dark mode, async worker). | [`src/main.cpp`](file:///c:/Users/aadit/Desktop/song-detector/src/main.cpp) |
| **Scan Duration Selector** | **Complete** | Runtime selector supporting 5-second quick scan and 10-second deep scan modes. | [`src/main.cpp`](file:///c:/Users/aadit/Desktop/song-detector/src/main.cpp) |
| **Automated CTest Suite** | **Complete** | Automated unit tests covering DSP gating, WASAPI packet extraction, and cryptographic verification. | [`tests/`](file:///c:/Users/aadit/Desktop/song-detector/tests/) |
| **Inno Setup Installer** | **Complete** | Automated setup packaging generating desktop shortcuts and Start Menu entries. | [`installer/HearThis.iss`](file:///c:/Users/aadit/Desktop/song-detector/installer/HearThis.iss) |

---

## 2. Planned Future Enhancements

### 2.1 Global System Hotkey Integration
- **Objective**: Trigger music identification instantly from anywhere in Windows without switching window focus.
- **Implementation Strategy**:
  - Register global hotkeys using the Win32 `RegisterHotKey(hwnd, HOTKEY_ID, MOD_CONTROL | MOD_SHIFT, 'S')` API during `WM_CREATE`.
  - Handle `WM_HOTKEY` messages in `WndProc` to trigger background scan workers asynchronously.
  - Provide fallback combinations (`F9` or `Ctrl+Alt+S`) configurable through the settings file.

### 2.2 System Tray Daemon & Background Minimization
- **Objective**: Allow HearThis to run unobtrusively in the background without occupying a taskbar slot.
- **Implementation Strategy**:
  - Add tray icon support using `Shell_NotifyIconW(NIM_ADD, &nid)` with custom `.ico` mipmaps from `assets/hearthis.ico`.
  - Intercept `WM_SYSCOMMAND` with `SC_MINIMIZE` or `SC_CLOSE` to hide the main window (`ShowWindow(hwnd, SW_HIDE)`).
  - Add a context menu with `Identify Now`, `Open Window`, and `Exit` items on right-click.

### 2.3 Windows Native Toast Notifications
- **Objective**: Display recognition results as native Windows 10/11 desktop notifications when running minimized.
- **Implementation Strategy**:
  - Leverage native balloon tips via `NIF_INFO` in `NOTIFYICONDATAW` for lightweight notification without external runtimes:
    ```cpp
    nid.uFlags |= NIF_INFO;
    wcscpy_s(nid.szInfoTitle, L"Song Identified");
    swprintf_s(nid.szInfo, L"%s - %s", songTitle, artistName);
    Shell_NotifyIconW(NIM_MODIFY, &nid);
    ```

### 2.4 Local History Store via Embedded SQLite
- **Objective**: Maintain a persistent history of recognized tracks with timestamps, album art links, and confidence scores.
- **Implementation Strategy**:
  - Integrate public domain `sqlite3.c` single-file amalgamation directly into the CMake build without external DLL dependencies.
  - Store history at `%APPDATA%/SongDetector/history.db`.
  - Add a "History" view or export option (CSV / JSON) in the desktop interface.

### 2.5 Offline Fingerprint Matching Engine
- **Objective**: Allow offline recognition against a user's local music collection when no internet connection is available.
- **Implementation Strategy**:
  - Implement a pure C++17 landmark extraction algorithm using a compact KissFFT or custom Cooley-Tukey FFT.
  - Store landmark hashes `(hash INT, song_id INT, offset INT)` in the local SQLite database.
  - Evaluate histogram time-offset alignment for matches before dispatching cloud fallback requests.
