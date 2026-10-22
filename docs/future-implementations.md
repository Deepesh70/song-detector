# Implementation Status & Future Roadmap

This document tracks completed architectural milestones and outlines planned future extensions for production scaling.

---

## 1. Current Implementation Status

| Component | Status | Description | Reference File |
| :--- | :--- | :--- | :--- |
| **Silence Gate** | **Done** | Evaluates RMS energy against $-50\text{ dBFS}$ floor to reject ambient noise before processing. | [`client/preprocessor.py`](file:///c:/Users/aadit/Desktop/song-detector/client/preprocessor.py) |
| **Mono Downmixing** | **Done** | Downmixes stereo channels to single mono channel. | [`client/preprocessor.py`](file:///c:/Users/aadit/Desktop/song-detector/client/preprocessor.py) |
| **Polyphase Resampler** | **Done** | Anti-aliased sinc resampler from $48\text{ kHz}$ to canonical $11,025\text{ Hz}$ mono ($>52\text{ dB}$ stopband attenuation). | [`client/preprocessor.py`](file:///c:/Users/aadit/Desktop/song-detector/client/preprocessor.py) |
| **Log-Band Peak Extraction** | **Done** | 5 logarithmic frequency bands with 2D local maxima ($\pm 5$ bins, $\pm 5$ frames) and dynamic magnitude floor ($-45\text{ dB}$). | [`client/fingerprinter.py`](file:///c:/Users/aadit/Desktop/song-detector/client/fingerprinter.py) |
| **Combinatorial Pairing** | **Done** | Forward target pairing in time $\Delta t \in [3, 258]$ and frequency $|\Delta f| \le 250$ with top-$5$ amplitude ranking. | [`client/fingerprinter.py`](file:///c:/Users/aadit/Desktop/song-detector/client/fingerprinter.py) |
| **Signed 32-Bit Bit Packing** | **Done** | 10-bit $f_1$, 10-bit $f_2$, 8-bit $\Delta t$ with two's complement conversion for PostgreSQL `INT` compatibility. | [`client/fingerprinter.py`](file:///c:/Users/aadit/Desktop/song-detector/client/fingerprinter.py) |
| **Sliding Window Histogram** | **Done** | Unquantized $\delta t$ integer histogram evaluated with 3-frame sliding window sum. | [`backend/matcher.py`](file:///c:/Users/aadit/Desktop/song-detector/backend/matcher.py) |
| **In-Track Prominence Scoring** | **Done** | Evaluates $V_1 \ge 15$ and peak-to-noise ratio $V_1 / V_{\text{noise}} \ge 3.0$ with duplicate track overlap detection. | [`backend/matcher.py`](file:///c:/Users/aadit/Desktop/song-detector/backend/matcher.py) |
| **Fallback Token Security** | **Done** | Single-use JWT with nonce (`jti`) validated and atomically consumed via Redis `GETDEL`. | [`backend/fallback.py`](file:///c:/Users/aadit/Desktop/song-detector/backend/fallback.py) |
| **Unit & End-to-End Test Coverage** | **Done** | 18 automated tests covering bit packing, DSP filtering, resampler attenuation, matcher, fallback security, and end-to-end crop recognition. | [`tests/`](file:///c:/Users/aadit/Desktop/song-detector/tests/) |

---

## 2. Future Implementations & Optimizations

### 1. High-Throughput DSP Acceleration (C / Rust Extension)
- **Objective**: If Python STFT and 2D peak extraction become a throughput bottleneck during batch catalog ingestion of hundreds of thousands of tracks, rewrite the core inner loops in Rust (using `pyo3` and `rustfft`) or C/C++.
- **Key Focus**:
  - Zero-copy audio buffer passing from Python NumPy arrays into SIMD-accelerated FFT routines.
  - Parallelizing 2D local maxima filtering using AVX2 / NEON vector intrinsics.
- **Trigger**: Ingestion throughput dropping below 50x realtime on multi-core servers.

### 2. Bulk Database Ingestion via PostgreSQL `COPY` with `FREEZE`
- **Objective**: Optimize batch loading of millions of fingerprint rows into the PostgreSQL covering index.
- **Key Focus**:
  - Stream parsed landmarks directly into PostgreSQL using binary or text format `COPY fingerprints FROM STDIN`.
  - Use `COPY ... WITH (FREEZE)` on initial catalog creation so tuples are committed directly as pre-frozen, bypassing transaction visibility overhead and updating the Visibility Map without requiring a separate immediate vacuum pass.
  - Drop covering index before initial multi-million row loading and rebuild concurrently post-load.

### 3. Background System Tray Daemon with Global Hotkey
- **Objective**: Provide a non-intrusive desktop application experience for Windows users.
- **Key Focus**:
  - System tray icon with status indicator (Idle, Listening, Matched).
  - Global Windows hotkey registration (e.g. `Ctrl + Alt + S` via Win32 `RegisterHotKey` or `pynput`).
  - Active audio capture running on a worker thread with silence detection.
  - Toast notification or compact pop-up overlay displaying track title, artist, album art, and recognition confidence.
