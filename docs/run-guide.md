# Operator & Execution Guide

This document provides step-by-step instructions for running, testing, and operating Song Detector on Windows.

---

## 1. Prerequisites & Environment

The project runs within the `song-detector` Conda environment on Python 3.11+.

### Activate the Environment
Always activate the environment in your terminal before running any scripts:

```powershell
conda activate song-detector
```

If you are using Git Bash / MINGW64 on Windows:
```bash
source $(conda info --base)/etc/profile.d/conda.sh
conda activate song-detector
```

---

## 2. Running Automated Tests

Run the full automated test suite (DSP attenuation, bit packing, PostgreSQL signed int32 conversions, sliding window histogram matching, fallback token security, and end-to-end recognition):

```powershell
pytest -v
```

All 18 unit and integration tests should pass with zero errors.

---

## 3. Hardware Diagnostic Check

Before starting the full system, run the standalone diagnostic tool to verify that Windows WASAPI loopback audio capture and the silence gate are working with your speakers or headphones:

```powershell
python client/test_capture.py
```

### Steps:
1. Start playing any music or video on Spotify, YouTube, etc.
2. Press `Enter` in the terminal when prompted.
3. The script records 5 seconds of audio, reports the measured RMS dBFS level, verifies resampling to $11,025\text{ Hz}$ mono, displays the 5-band peak distribution, and writes [`client/captured_test.wav`](file:///c:/Users/aadit/Desktop/song-detector/client/captured_test.wav).

---

## 4. End-to-End Song Identification

Identifying songs playing on your PC requires two components running concurrently: the **Backend API Service** and the **Desktop Agent**.

### Step 1: Start the Backend Service (Terminal 1)
Open your first terminal in the project directory:

```powershell
conda activate song-detector
uvicorn backend.app:app --host 127.0.0.1 --port 8000
# OR
# python -m backend.app
```

The service will boot on `http://127.0.0.1:8000`:
- Auto-detects PostgreSQL on port 5432 (or falls back to local zero-config `song_detector.sqlite3`).
- Loads `AUDD_API_TOKEN` from `.env` for universal commercial song recognition.

---

### Step 2: Run the Desktop Loopback Agent (Terminal 2)
Open a second terminal:

```powershell
conda activate song-detector
```

#### Option A: Single 5-Second Identification (`--once`)
Identifies whatever song is currently playing and exits immediately:

```powershell
python client/agent.py --once
```

**Example Output:**
```text
[Listening] Capturing 5 seconds of system playback via WASAPI...
[Fingerprinted] Extracted 800 landmark pairs. Checking local catalog...
[Local Miss] Not in local library. Forwarding 5s audio to global provider (AudD)...
==================================================
>>> SONG IDENTIFIED (AudD Global Catalog) <<<
Title:        Starboy
Artist:       The Weeknd ft. Daft Punk
Album:        Starboy
Release Date: 2016-09-22
Listen:       https://lis.tn/Starboy
==================================================
```

#### Option B: Continuous Background Listener (`--listen`)
Keeps listening continuously in the background and identifies songs automatically whenever music plays:

```powershell
python client/agent.py --listen
```
- If your computer is quiet, the RMS silence gate drops the buffer at zero CPU/network cost:
  `[Silence] Audio energy below -50 dBFS silence gate. Skipping recognition.`
- When music plays, it captures, fingerprints, and identifies the track automatically.
- Press `Ctrl + C` to stop.

---

## 5. Ingesting Your Own Music Library (Local Catalog)

If you have your own MP3, WAV, FLAC, or OGG files that you want recognized locally with zero external API calls:

1. Place your audio files inside the `music_catalog/` directory:
   ```powershell
   mkdir music_catalog
   # Copy your songs into music_catalog/
   ```
2. Run the offline ingestion worker:
   ```powershell
   python worker/ingest.py --catalog-dir music_catalog
   ```
3. When any of those ingested songs play on your machine, the engine identifies them locally in under $50\text{ms}$ with zero network traffic:
   ```text
   ==================================================
   >>> SONG IDENTIFIED (Local Catalog Hit) <<<
   Title:      Demo_Acoustic_Song
   Artist:     Unknown Artist
   Offset:     12.0s
   Prominence: 73.0 (Votes: 73)
   ==================================================
   ```

---

## 6. Environment Configuration (`.env`)

Secrets and database endpoints are configured in `.env` (excluded from git via `.gitignore`):

| Variable | Purpose | Default / Example |
| :--- | :--- | :--- |
| `AUDD_API_TOKEN` | Commercial recognition token for 100M+ songs | `<your_token_here>` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:postgres@127.0.0.1:5432/song_detector` |
| `REDIS_URL` | Redis cache for fallback token nonces | `redis://127.0.0.1:6379/0` |

*Note: If PostgreSQL or Redis are not running, the system automatically uses the local SQLite engine (`song_detector.sqlite3`) and an in-memory cache.*

---

## 7. Troubleshooting

- **"No WASAPI loopback audio device detected"**: Ensure that your speakers or headphones are connected and set as the default playback device in Windows Sound Settings.
- **"Audio energy below -50 dBFS"**: The system was playing near-silence. Increase your media volume or unmute the application.
- **"Connection Error: Could not connect to API server"**: Ensure Terminal 1 is running `uvicorn backend.app:app --host 127.0.0.1 --port 8000`.
