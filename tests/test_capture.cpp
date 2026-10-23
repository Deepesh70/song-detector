#include "hearthis/wasapi_capture.h"
#include "hearthis/audio_processor.h"

#include <iostream>

int main() {
    std::cout << "[HearThis C++] Testing WASAPI loopback capture..." << std::endl;

    hearthis::WasapiCapture capture;
    hearthis::CapturedAudio audio = capture.capture_loopback(0.5); // Fast 0.5s probe

    if (!audio.success) {
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
