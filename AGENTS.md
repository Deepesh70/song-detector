# AGENTS.md

## Project Overview
HearThis is a production-grade native Windows desktop audio identification system written in modern C++17. It captures system audio playback on Windows using WASAPI loopback without microphone bleed, applies RMS silence gating, serializes in-memory RIFF PCM WAV, and identifies tracks via direct cloud API providers (ACRCloud with BCrypt HMAC-SHA1 and AudD).

---

## Technology Stack

- **Client Runtime**: Native C++17 (MSVC x64 / Windows SDK)
  - Audio Capture: Windows Audio Session API (`WASAPI` / `IAudioCaptureClient` COM in loopback mode)
  - DSP & Serialization: Standard library SIMD vector arithmetic and in-memory RIFF WAV generation
  - Network Client: Windows HTTP Services (`winhttp.dll` / TLS 1.2+ connection reuse)
  - Cryptography: Windows Cryptography Next Generation (`bcrypt.dll` for HMAC-SHA1, `crypt32.dll` for Base64)
  - GUI Framework: Native Win32 API with Immersive Dark Mode (`dwmapi.dll` / `user32.dll` / `gdi32.dll`)
  - Local Configuration: Flat-key persistence at `%APPDATA%/SongDetector/native_config.txt`

---

## Repository Structure

```
song-detector/
├── AGENTS.md                  # Project stack, commands, standards, and conventions
├── README.md                  # System overview and quickstart guide
├── CMakeLists.txt             # Multi-platform CMake build configuration
├── build.bat                  # One-click MSVC compile & test runner
├── include/                   # Public C++ header interfaces
│   └── hearthis/
│       ├── audio_processor.h  # Audio processing and WAV serialization
│       ├── wasapi_capture.h   # Loopback audio capture via WASAPI
│       └── api_client.h       # Cloud API transport & BCrypt HMAC-SHA1
├── src/                       # Source implementations
│   ├── audio_processor.cpp    # Audio math algorithms
│   ├── wasapi_capture.cpp     # COM audio interface integration
│   ├── api_client.cpp         # WinHTTP HTTPS multipart client
│   └── main.cpp               # Win32 desktop application entrypoint
├── tests/                     # Automated C++ unit tests
│   ├── test_processor.cpp     # RMS silence and WAV format tests
│   ├── test_capture.cpp       # Loopback hardware capture tests
│   └── test_api_client.cpp    # HMAC-SHA1 test vector & JSON parser tests
├── installer/                 # Windows Inno Setup installer script
│   └── HearThis.iss
└── assets/                    # Application icons (.ico mipmaps, .png)
```

---

## Development Commands

### Building and Testing with CMake
```cmd
cmake -B build
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
```

### Direct MSVC Compilation
```cmd
build.bat
```

---

## Code Style & Engineering Standards

1. **Modern C++17 & RAII**:
   - Never manage memory with raw `new`/`delete` outside constructor/destructor wrappers.
   - Use standard containers (`std::vector`, `std::string`) and COM smart pointers (`Microsoft::WRL::ComPtr`).
2. **Zero Third-Party Dependencies**:
   - All networking, cryptographic signing, and audio capture must link strictly against native Windows system DLLs (`winhttp.dll`, `bcrypt.dll`, `crypt32.dll`, `ole32.dll`).
3. **Security & Secrets**:
   - User credentials reside strictly in `%APPDATA%/SongDetector/native_config.txt`.
   - Never print or commit credentials to logs or repository.
