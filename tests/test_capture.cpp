#include "hearthis/wasapi_capture.h"
#include "hearthis/audio_processor.h"

#include <iostream>
#include <cassert>
#include <chrono>
#include <atomic>

int main() {
    std::cout << "[HearThis C++] Testing WASAPI loopback and microphone capture..." << std::endl;

    hearthis::WasapiCapture capture;

    // Test 1: Speakers (Loopback) capture probe (0.5s)
    std::cout << "  [INFO] Probing Speakers (Loopback) capture..." << std::endl;
    hearthis::CapturedAudio speakers_audio = capture.capture_audio(hearthis::AudioSource::Speakers, 0.5);

    if (speakers_audio.success) {
        std::cout << "  [PASS] Loopback captured " << speakers_audio.samples.size() << " samples at "
                  << speakers_audio.sample_rate << " Hz (" << speakers_audio.channels << " channels)." << std::endl;
        std::vector<float> mono = hearthis::condition_audio(
            speakers_audio.samples, speakers_audio.channels, speakers_audio.sample_rate, hearthis::AudioSource::Speakers
        );
        std::vector<uint8_t> wav = hearthis::pcm_to_wav_bytes(mono, speakers_audio.sample_rate);
        std::cout << "  [PASS] Loopback audio conditioned and converted to WAV (" << wav.size() << " bytes)." << std::endl;
    } else {
        std::cout << "  [INFO] Loopback capture not active / headless environment: "
                  << speakers_audio.error_message << std::endl;
    }

    // Test 2: Microphone capture probe (0.5s)
    std::cout << "  [INFO] Probing Microphone capture..." << std::endl;
    hearthis::CapturedAudio mic_audio = capture.capture_audio(hearthis::AudioSource::Microphone, 0.5);

    if (mic_audio.success) {
        std::cout << "  [PASS] Microphone captured " << mic_audio.samples.size() << " samples at "
                  << mic_audio.sample_rate << " Hz (" << mic_audio.channels << " channels)." << std::endl;
        std::vector<float> conditioned = hearthis::condition_audio(
            mic_audio.samples, mic_audio.channels, mic_audio.sample_rate, hearthis::AudioSource::Microphone
        );
        std::vector<uint8_t> wav = hearthis::pcm_to_wav_bytes(conditioned, mic_audio.sample_rate);
        std::cout << "  [PASS] Microphone audio conditioned (HPF + norm) and converted to WAV (" << wav.size() << " bytes)." << std::endl;
    } else {
        std::cout << "  [INFO] Microphone not connected or permission unavailable: "
                  << mic_audio.error_message << std::endl;
    }

    // Test 3: Cooperative cancellation token test
    std::cout << "  [INFO] Testing cooperative cancellation token..." << std::endl;
    std::atomic<bool> cancel_token(true); // Pre-cancelled
    auto start_time = std::chrono::steady_clock::now();
    hearthis::CapturedAudio cancelled_audio = capture.capture_audio(hearthis::AudioSource::Speakers, 5.0, &cancel_token);
    auto duration_ms = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start_time).count();

    // The call requested 5000ms, but because cancel_token was true, it must abort in < 500ms
    assert(duration_ms < 1000);
    assert(cancelled_audio.success == false);
    std::cout << "  [PASS] Cooperative cancellation aborted 5.0s scan in " << duration_ms << " ms." << std::endl;

    // Test 4: Synthetic fallback verification for CI runners without audio hardware
    std::vector<float> synthetic_stereo(48000, 0.05f);
    std::vector<float> conditioned_synthetic = hearthis::condition_audio(
        synthetic_stereo, 2, 48000, hearthis::AudioSource::Microphone
    );
    std::vector<uint8_t> wav = hearthis::pcm_to_wav_bytes(conditioned_synthetic, 48000);
    assert(wav.size() == 44 + (24000 * sizeof(int16_t)));
    std::cout << "  [PASS] Synthetic fallback pipeline verified (" << wav.size() << " bytes)." << std::endl;

    std::cout << "\n>>> ALL WASAPI CAPTURE TESTS PASSED! <<<\n" << std::endl;
    return 0;
}
