cmake_minimum_required(VERSION 3.20)
project(HearThisNative VERSION 1.0.3 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include_directories(include)

# Common static library containing DSP, WASAPI capture, and WinHTTP/BCrypt client
add_library(hearthis_core STATIC
    src/audio_processor.cpp
    src/wasapi_capture.cpp
    src/api_client.cpp
)

target_link_libraries(hearthis_core PUBLIC
    ole32
    oleaut32
    winhttp
    bcrypt
    crypt32
)

# Main Standalone Desktop GUI Application (WIN32 Subsystem)
add_executable(HearThis WIN32 src/main.cpp)
target_link_libraries(HearThis PRIVATE
    hearthis_core
    dwmapi
    shell32
    comctl32
    user32
    gdi32
)

# Test executables
enable_testing()

add_executable(test_processor tests/test_processor.cpp)
target_link_libraries(test_processor PRIVATE hearthis_core)
add_test(NAME AudioProcessorTest COMMAND test_processor)

add_executable(test_capture tests/test_capture.cpp)
target_link_libraries(test_capture PRIVATE hearthis_core)
add_test(NAME WasapiCaptureTest COMMAND test_capture)

add_executable(test_api_client tests/test_api_client.cpp)
target_link_libraries(test_api_client PRIVATE hearthis_core)
add_test(NAME ApiClientTest COMMAND test_api_client)
