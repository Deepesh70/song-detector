#include "hearthis/audio_processor.h"
#include <iostream>
#include <vector>
#include <cassert>
#include <cmath>

int main() {
    std::cout << "[HearThis C++] Testing audio processor module..." << std::endl;

    // Test 1: Silence detection
    std::vector<float> silent_audio(48000, 0.0001f);
    bool silent = hearthis::is_silent(silent_audio, -50.0f);
    assert(silent == true);
    std::cout << "  [PASS] Silence detected correctly for quiet buffer." << std::endl;

    // Test 2: Active sound detection
    std::vector<float> loud_audio(48000, 0.5f);
    bool loud_silent = hearthis::is_silent(loud_audio, -50.0f);
    assert(loud_silent == false);
    std::cout << "  [PASS] Active audio passes silence gate correctly." << std::endl;

    // Test 3: Stereo to mono downmixing
    std::vector<float> stereo = {1.0f, 0.0f, 0.8f, 0.2f};
    std::vector<float> mono = hearthis::stereo_to_mono(stereo);
    assert(mono.size() == 2);
    assert(std::abs(mono[0] - 0.5f) < 1e-5f);
    assert(std::abs(mono[1] - 0.5f) < 1e-5f);
    std::cout << "  [PASS] Stereo downmix to mono verified." << std::endl;

    // Test 4: WAV file generation
    std::vector<float> mono_tone(48000, 0.25f);
    std::vector<uint8_t> wav = hearthis::pcm_to_wav_bytes(mono_tone, 48000);
    assert(wav.size() == 44 + (48000 * sizeof(int16_t)));
    assert(wav[0] == 'R' && wav[1] == 'I' && wav[2] == 'F' && wav[3] == 'F');
    assert(wav[8] == 'W' && wav[9] == 'A' && wav[10] == 'V' && wav[11] == 'E');
    std::cout << "  [PASS] 44-byte WAV header and PCM byte packing verified (" << wav.size() << " bytes)." << std::endl;

    std::cout << "\n>>> ALL AUDIO PROCESSOR TESTS PASSED! <<<\n" << std::endl;
    return 0;
}
