#include "hearthis/wasapi_capture.h"

#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <wrl/client.h>
#include <chrono>
#include <thread>

using Microsoft::WRL::ComPtr;

namespace hearthis {

WasapiCapture::WasapiCapture() {
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
}

WasapiCapture::~WasapiCapture() {
    CoUninitialize();
}

CapturedAudio WasapiCapture::capture_audio(AudioSource source, double duration_seconds, std::atomic<bool>* cancel_token) {
    CapturedAudio result;
    HRESULT hr;

    // 1. Create a Device Enumerator to access system audio endpoints
    ComPtr<IMMDeviceEnumerator> enumerator;
    hr = CoCreateInstance(
        __uuidof(MMDeviceEnumerator),
        nullptr,
        CLSCTX_ALL,
        __uuidof(IMMDeviceEnumerator),
        reinterpret_cast<void**>(enumerator.GetAddressOf())
    );
    if (FAILED(hr)) {
        result.error_message = "Failed to create Windows audio device enumerator.";
        return result;
    }

    // 2. Select appropriate endpoint (eRender for loopback, eCapture for microphone)
    EDataFlow data_flow = (source == AudioSource::Microphone) ? eCapture : eRender;
    DWORD stream_flags = (source == AudioSource::Speakers) ? AUDCLNT_STREAMFLAGS_LOOPBACK : 0;

    ComPtr<IMMDevice> default_device;
    hr = enumerator->GetDefaultAudioEndpoint(data_flow, eConsole, default_device.GetAddressOf());

    // Fallback: If microphone on eConsole fails, check eCommunications (USB headsets/BT mics)
    if (FAILED(hr) && source == AudioSource::Microphone) {
        hr = enumerator->GetDefaultAudioEndpoint(eCapture, eCommunications, default_device.GetAddressOf());
    }

    if (FAILED(hr)) {
        result.error_message = (source == AudioSource::Microphone)
            ? "No default microphone found. Please check microphone connection and Windows privacy permissions."
            : "No default audio playback device found.";
        return result;
    }

    // 3. Activate IAudioClient interface on the selected device
    ComPtr<IAudioClient> audio_client;
    hr = default_device->Activate(
        __uuidof(IAudioClient),
        CLSCTX_ALL,
        nullptr,
        reinterpret_cast<void**>(audio_client.GetAddressOf())
    );
    if (FAILED(hr)) {
        result.error_message = "Failed to activate WASAPI Audio Client.";
        return result;
    }

    // 4. Query hardware mix format
    WAVEFORMATEX* wave_format = nullptr;
    hr = audio_client->GetMixFormat(&wave_format);
    if (FAILED(hr) || !wave_format) {
        result.error_message = "Failed to query system audio mix format.";
        return result;
    }

    result.sample_rate = wave_format->nSamplesPerSec;
    result.channels = wave_format->nChannels;

    bool is_float = false;
    if (wave_format->wFormatTag == WAVE_FORMAT_IEEE_FLOAT) {
        is_float = true;
    } else if (wave_format->wFormatTag == WAVE_FORMAT_EXTENSIBLE) {
        auto* pEx = reinterpret_cast<WAVEFORMATEXTENSIBLE*>(wave_format);
        if (pEx->SubFormat == KSDATAFORMAT_SUBTYPE_IEEE_FLOAT) {
            is_float = true;
        }
    }

    REFERENCE_TIME buffer_duration = 10000000; // 1-second circular buffer

    // 5. Initialize stream with OS auto-conversion flags enabled
    DWORD init_flags = stream_flags | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY;

    hr = audio_client->Initialize(
        AUDCLNT_SHAREMODE_SHARED,
        init_flags,
        buffer_duration,
        0,
        wave_format,
        nullptr
    );

    // Fallback: If driver rejects SRC/AUTOCONVERTPCM flags, retry with base stream flags
    if (FAILED(hr)) {
        hr = audio_client->Initialize(
            AUDCLNT_SHAREMODE_SHARED,
            stream_flags,
            buffer_duration,
            0,
            wave_format,
            nullptr
        );
    }

    if (FAILED(hr)) {
        CoTaskMemFree(wave_format);
        result.error_message = (source == AudioSource::Microphone)
            ? "Failed to initialize WASAPI microphone stream."
            : "Failed to initialize WASAPI loopback stream.";
        return result;
    }

    // 6. Acquire Capture Client service
    ComPtr<IAudioCaptureClient> capture_client;
    hr = audio_client->GetService(
        __uuidof(IAudioCaptureClient),
        reinterpret_cast<void**>(capture_client.GetAddressOf())
    );

    if (FAILED(hr)) {
        CoTaskMemFree(wave_format);
        result.error_message = "Failed to get IAudioCaptureClient service.";
        return result;
    }

    // 7. Start audio stream
    hr = audio_client->Start();
    if (FAILED(hr)) {
        CoTaskMemFree(wave_format);
        result.error_message = "Failed to start audio stream.";
        return result;
    }

    size_t target_total_frames = static_cast<size_t>(result.sample_rate * duration_seconds);
    size_t total_samples_needed = target_total_frames * result.channels;
    result.samples.reserve(total_samples_needed);

    auto start_time = std::chrono::steady_clock::now();
    double timeout_seconds = duration_seconds + 1.5;

    // 8. Capture Loop: Read audio packets with cooperative cancellation
    while (result.samples.size() < total_samples_needed) {
        if (cancel_token && cancel_token->load()) {
            audio_client->Stop();
            CoTaskMemFree(wave_format);
            result.error_message = "Capture cancelled by user.";
            result.success = false;
            return result;
        }

        auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start_time).count();
        if (elapsed > timeout_seconds) {
            break;
        }

        UINT32 next_packet_size = 0;
        hr = capture_client->GetNextPacketSize(&next_packet_size);
        if (FAILED(hr)) {
            break;
        }

        if (next_packet_size == 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            continue;
        }

        BYTE* pData = nullptr;
        UINT32 num_frames_read = 0;
        DWORD flags = 0;

        hr = capture_client->GetBuffer(&pData, &num_frames_read, &flags, nullptr, nullptr);
        if (FAILED(hr)) {
            break;
        }

        size_t samples_in_packet = num_frames_read * result.channels;

        if (flags & AUDCLNT_BUFFERFLAGS_SILENT) {
            for (size_t i = 0; i < samples_in_packet; ++i) {
                result.samples.push_back(0.0f);
            }
        } else if (is_float) {
            const float* float_data = reinterpret_cast<const float*>(pData);
            for (size_t i = 0; i < samples_in_packet; ++i) {
                result.samples.push_back(float_data[i]);
            }
        } else if (wave_format->wBitsPerSample == 16) {
            const int16_t* int_data = reinterpret_cast<const int16_t*>(pData);
            for (size_t i = 0; i < samples_in_packet; ++i) {
                result.samples.push_back(static_cast<float>(int_data[i]) / 32768.0f);
            }
        } else if (wave_format->wBitsPerSample == 32) {
            const int32_t* int_data = reinterpret_cast<const int32_t*>(pData);
            for (size_t i = 0; i < samples_in_packet; ++i) {
                result.samples.push_back(static_cast<float>(int_data[i]) / 2147483648.0f);
            }
        } else {
            // Generic 8-bit or fallback
            for (size_t i = 0; i < samples_in_packet; ++i) {
                result.samples.push_back(0.0f);
            }
        }

        capture_client->ReleaseBuffer(num_frames_read);
    }

    audio_client->Stop();
    CoTaskMemFree(wave_format);

    if (result.samples.size() < total_samples_needed) {
        result.samples.resize(total_samples_needed, 0.0f);
    }

    result.success = true;
    return result;
}

} // namespace hearthis
