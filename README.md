# Song Detector

A production-grade system audio recognition service modeled after Shazam's acoustic landmark fingerprinting algorithm (Wang, 2003). The system captures playback directly from Windows system audio (WASAPI loopback) without microphone bleed, extracts noise-resilient constellation landmarks, matches candidate tracks against an indexed PostgreSQL inverted index using in-track prominence histogram voting, and proxies unindexed queries to commercial providers via a two-step fallback token protocol.

---

## Key Features

- **Windows WASAPI Loopback Capture**: Captures internal application playback (Spotify, YouTube, VLC, browser) with silence detection and clock keep-alive.
- **Robust DSP Pipeline**:
  - RMS silence gate ($-50\text{ dBFS}$) rejecting quantization floor.
  - Polyphase anti-aliased sinc resampler from native $48\text{ kHz}$ to canonical $11,025\text{ Hz}$ mono.
  - 5-band logarithmic frequency division ($27\text{ Hz}\text{–}5000\text{ Hz}$).
  - Dynamic spectral magnitude floor ($-45\text{ dB}$ from clip peak).
  - 2D local maxima filtering with amplitude-ranked target pairing.
- **Invariance**: Amplitude-free hash encoding ensures resistance to EQ adjustments, bass boost, and lossy MP3 compression.
- **PostgreSQL Covering Index**: High-speed Index-Only Scans with per-hash `LATERAL` limits (1,000 matches/hash) and signed `int32` two's complement casting.
- **Within-Track Prominence Scoring**: Replaces raw counts with Signal-to-Noise Ratio (SNR) peak-to-noise scoring ($V_1 / V_{\text{noise}} \ge 3.0$), eliminating false positives and length bias.
- **Two-Step Fallback Protocol**: Hashes are sent first ($\approx 6\text{ KB}$); on a miss, an atomic Redis-backed single-use JWT authorises an Opus/MP3 snippet upload to query AudD/ACRCloud without exposing API keys to clients.

---

## Documentation

Detailed technical documentation is available in the `docs/` directory:

- [Operator & Execution Guide](docs/run-guide.md): Step-by-step instructions for running tests, backend server, desktop agent, and local catalog ingestion.
- [System Architecture](docs/architecture.md): Complete component interaction, data flow, and threat model.
- [DSP & Mathematical Specification](docs/dsp-specification.md): Exact mathematical formulations, bit allocation, STFT parameters, and scoring algorithms.
- [API Reference](docs/api-reference.md): Endpoints, request/response schemas, error handling, and authentication tokens.
- [Implementation Status & Future Roadmap](docs/future-implementations.md): Current completion status and planned future extensions (Rust DSP acceleration, `COPY FREEZE` bulk loader, system tray daemon).

---

## Quickstart

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Redis 7+

### Installation
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Verification
```bash
pytest -v
```
