@echo off
setlocal

echo ===================================================
echo   Building HearThis Native C++ Production Suite
echo ===================================================

call "E:\Visual Studio\Product\VC\Auxiliary\Build\vcvarsall.bat" x64
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to initialize MSVC Developer Environment.
    exit /b 1
)

cd /d "%~dp0"

echo [1/4] Running Audio Processor Unit Tests...
cl /nologo /EHsc /std:c++17 /I include src\audio_processor.cpp tests\test_processor.cpp /Fe:test_processor_bin.exe
if %ERRORLEVEL% NEQ 0 exit /b 1
test_processor_bin.exe
if %ERRORLEVEL% NEQ 0 exit /b 1

echo [2/4] Running WASAPI Capture Unit Tests...
cl /nologo /EHsc /std:c++17 /I include src\audio_processor.cpp src\wasapi_capture.cpp tests\test_capture.cpp ole32.lib oleaut32.lib /Fe:test_capture_bin.exe
if %ERRORLEVEL% NEQ 0 exit /b 1
test_capture_bin.exe
if %ERRORLEVEL% NEQ 0 exit /b 1

echo [3/4] Running API Client Unit Tests (ACRCloud and AudD)...
cl /nologo /EHsc /std:c++17 /I include src\api_client.cpp tests\test_api_client.cpp winhttp.lib bcrypt.lib crypt32.lib /Fe:test_api_bin.exe
if %ERRORLEVEL% NEQ 0 exit /b 1
test_api_bin.exe
if %ERRORLEVEL% NEQ 0 exit /b 1

echo [4/4] Building Standalone Production Desktop Executable (HearThis.exe)...
cl /nologo /O2 /EHsc /std:c++17 /I include src\audio_processor.cpp src\wasapi_capture.cpp src\api_client.cpp src\main.cpp user32.lib gdi32.lib dwmapi.lib comctl32.lib shell32.lib ole32.lib oleaut32.lib winhttp.lib bcrypt.lib crypt32.lib /Fe:HearThis.exe /link /SUBSYSTEM:WINDOWS
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to compile HearThis.exe
    exit /b 1
)

if not exist dist mkdir dist
copy /y HearThis.exe dist\HearThis.exe >nul

del /q *.obj test_*_bin.exe 2>nul

echo.
echo ===================================================
echo   SUCCESS! Standalone Desktop Executable Built:
echo   HearThis.exe and dist\HearThis.exe
echo ===================================================
dir HearThis.exe
