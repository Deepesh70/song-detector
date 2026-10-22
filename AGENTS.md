# AGENTS.md

## Project Overview
Song Detector is a production-grade desktop audio identification system modeled after Shazam's acoustic landmark fingerprinting algorithm (Wang, 2003). It captures system audio on Windows using WASAPI loopback, extracts robust time-frequency constellation landmarks invariant to equalizers and MP3 compression, matches hashes against a PostgreSQL covering index using in-track prominence histogram scoring, and provides a two-step fallback proxy to commercial providers (AudD / ACRCloud).

---

## Technology Stack

- **Client Runtime**: Python 3.11+ / Rust
  - Windows Audio Capture: `soundcard` / `PyAudio` (WASAPI shared-mode loopback)
  - Resampling & DSP: `numpy`, `scipy` (polyphase anti-aliasing sinc resampler, STFT, peak extraction)
- **Backend Service**:
  - API Framework: `FastAPI` (Python) with `uvicorn`
  - Relational Database: `PostgreSQL` 14+ with B-Tree covering index (`INCLUDE (song_id, offset_frames)`)
  - Cache & State Store: `Redis` 7+ (stateful single-use JWT fallback token nonces via `GETDEL`)
  - Ingestion Worker: Background async processor (CLI bulk loader / worker queue)
- **Fallback Integration**:
  - AudD / ACRCloud API (proxied exclusively through backend)

---

## Repository Structure

```
song-detector/
├── AGENTS.md                  # Project stack, commands, standards, and conventions
├── README.md                  # System overview and quickstart guide
├── .gitignore                 # Python, environment, audio cache, and OS ignore rules
├── docs/                      # Architectural and technical documentation
│   ├── architecture.md        # Complete system architecture and data flow
│   ├── dsp-specification.md   # Mathematical and algorithmic DSP specification
│   ├── api-reference.md       # API schemas, endpoints, and error handling
│   ├── future-implementations.md # Current status and future optimization roadmap
│   └── run-guide.md           # Step-by-step operator and execution guide
├── client/                    # Desktop capture and client-side processing
│   ├── capture.py             # WASAPI loopback recording with silence keep-alive
│   ├── preprocessor.py        # RMS silence gate and polyphase resampler (48kHz -> 11,025Hz)
│   ├── fingerprinter.py       # STFT, 5-band peak picker, and full 32-bit hash encoder
│   └── agent.py               # Desktop daemon / hotkey dispatcher and fallback uploader
├── backend/                   # Recognition service and database integration
│   ├── app.py                 # FastAPI application and endpoint routing
│   ├── db.py                  # PostgreSQL pool and covering index lateral query executor
│   ├── matcher.py             # Sliding window histogram and in-track prominence evaluator
│   └── fallback.py            # Redis token generator/validator and provider proxy
├── worker/                    # Offline catalog ingestion pipeline
│   ├── ingest.py              # Audio directory scanner, landmark generator, batch copy
│   └── maintenance.py         # Vacuum runner and global stop-hash pruner
└── tests/                     # Unit and integration test suites
    ├── test_bit_packing.py    # Bit layout, signed int32 conversions, boundary checks
    ├── test_dsp.py            # Spectral magnitude floor, 5-band local max, pair generator
    ├── test_matcher.py        # Sliding window, duplicate track handling, prominence ratio
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

# Run targeted DSP tests
pytest -v tests/test_bit_packing.py tests/test_dsp.py tests/test_matcher.py
```

### Running the Services
```bash
# Start backend API (development)
uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload

# Run catalog ingestion
python worker/ingest.py --catalog-dir ./music_catalog

# Run desktop loopback listener
python client/agent.py --listen
```

---

## Code Style & Engineering Standards

1. **Strict Type Annotations**: Every function and method must specify complete type annotations (`typing` module / standard modern Python typing). No bare `Any`.
2. **Deterministic DSP**:
   - Signal processing functions must operate strictly on explicit `numpy.ndarray` buffers.
   - All sample rate, FFT size, and hop parameters must reference shared configuration constants.
   - Never use random seeds or non-deterministic operations in feature extraction.
3. **Database Integrity**:
   - Every raw 32-bit unsigned integer hash must be explicitly bit-cast to a signed two's complement `int32` before passing to PostgreSQL.
   - Ingestion batch loads must run `VACUUM ANALYZE fingerprints;` to maintain Visibility Map consistency for Index-Only Scans.
   - Use parameterized queries with `CROSS JOIN LATERAL` and `LIMIT 1000` per hash.
4. **Security & Secrets**:
   - No API keys in client-side code. AudD / ACRCloud credentials reside solely in backend `.env`.
   - Replay protection on `/v1/recognize/fallback` via atomic Redis `GETDEL`.
