# Operator & Execution Guide

This document provides step-by-step instructions for building, testing, and running HearThis on Windows.

---

## 1. Prerequisites

- **Operating System**: Windows 10 or Windows 11 (64-bit)
- **Compiler**: Microsoft Visual Studio 2022 (with C++ Desktop development workload) or Build Tools for Visual Studio
- **Optional**: CMake 3.20+ (included with Visual Studio)

---

## 2. Building the Project

### Method A: Quick Build (`build.bat`)
Open any terminal and run:
```cmd
build.bat
```
This script initializes the MSVC x64 developer environment, compiles and executes all 3 unit test suites, and produces `HearThis.exe` in under 5 seconds.

### Method B: CMake Build
```cmd
cmake -B build
cmake --build build --config Release
```
The compiled executable will be placed in `build\Release\HearThis.exe`.

---

## 3. Running Unit Tests

Run all unit tests using CMake's test runner:
```cmd
ctest --test-dir build -C Release --output-on-failure
```

The test suite covers:
1. **Audio Processor**: RMS silence detection (-50 dBFS gate), stereo-to-mono downmixing, and 44-byte standard RIFF WAV packing.
2. **WASAPI Loopback Capture**: Hardware endpoint activation, IEEE float format verification, and real-time packet extraction.
3. **API Client & Cryptography**: Native Windows BCrypt HMAC-SHA1 signature computation and JSON response parsing.

---

## 4. Running the Desktop Application

Launch `HearThis.exe`:
```cmd
HearThis.exe
```

### First-Time Configuration:
1. Select your preferred provider (**ACRCloud** is selected by default).
2. Enter your credentials:
   - For **ACRCloud**: Host URL (e.g., `identify-eu-west-1.acrcloud.com`), Access Key, and Access Secret.
   - For **AudD**: API Token.
3. Your credentials and preferred scan duration are automatically saved to `%APPDATA%\SongDetector\native_config.txt`.
4. Play any song in Spotify, YouTube, or a game, and click **Identify Music Now**.
