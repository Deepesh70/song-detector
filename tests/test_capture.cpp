#include "hearthis/wasapi_capture.h"
#include "hearthis/audio_processor.h"

#include <iostream>
#include <cassert>

int main() {
    std::cout << "[HearThis C++] Testing WASAPI loopback capture..." << std::endl;

    hearthis::WasapiCapture capture;
    hearthis::CapturedAudio audio = capture.capture_loopback(0.5); // Fast 0.5s probe

    if (!audio.success) {
        // Headless CI environments (e.g. GitHub Actions runners) do not have physical speakers attached.
        if (audio.error_message.find("No default audio playback device") != std::string::npos ||
            audio.error_message.find("audio device enumerator") != std::string::npos) {
            std::cout << "  [INFO] Headless/CI environment detected (" << audio.error_message << ")." << std::endl;
            std::cout << "  [PASS] Hardware absence handled gracefully with structured error." << std::endl;

            // Verify downstream audio conditioning on synthetic buffer
            std::vector<float> synthetic_stereo(48000, 0.1f);
            std::vector<float> mono = hearthis::stereo_to_mono(synthetic_stereo);
            std::vector<uint8_t> wav = hearthis::pcm_to_wav_bytes(mono, 48000);
            assert(wav.size() == 44 + (24000 * sizeof(int16_t)));
            std::cout << "  [PASS] Downstream stereo downmix & WAV packing verified on synthetic buffer." << std::endl;

            std::cout << "\n>>> WASAPI CAPTURE TEST PASSED (HEADLESS ENVIRONMENT) <<<\n" << std::endl;
            return 0;
        }

        std::cerr << "  [ERROR] Capture failed: " << audio.error_message << std::endl;
        return 1;
    }

    std::cout << "  [PASS] Captured " << audio.samples.size() << " samples at "
              << audio.sample_rate << " Hz (" << audio.channels << " channels)." << std::endl;

    std::vector<float> mono = hearthis::stereo_to_mono(audio.samples);
    std::vector<uint8_t> wav = hearthis::pcm_to_wav_bytes(mono, audio.sample_rate);

    std::cout << "  [PASS] Generated WAV stream: " << wav.size() << " bytes." << std::endl;
    std::cout << "\n>>> ALL WASAPI CAPTURE TESTS PASSED! <<<\n" << std::endl;
    return 0;
}
