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

    // Test 4: Channel-aware downmixing (to_mono)
    // 1-channel mono passthrough
    std::vector<float> single_ch = {0.4f, 0.7f, -0.3f};
    std::vector<float> single_res = hearthis::to_mono(single_ch, 1);
    assert(single_res == single_ch);

    // 4-channel surround averaging
    std::vector<float> quad_ch = {0.2f, 0.4f, 0.6f, 0.8f};
    std::vector<float> quad_res = hearthis::to_mono(quad_ch, 4);
    assert(quad_res.size() == 1);
    assert(std::abs(quad_res[0] - 0.5f) < 1e-5f);
    std::cout << "  [PASS] Channel-aware downmixing verified (1ch passthrough and 4ch downmix)." << std::endl;

    // Test 5: 1st-order 80 Hz high-pass filter (strips DC offset)
    // Constant DC bias of +0.5 over 1000 samples at 48000 Hz
    std::vector<float> dc_signal(1000, 0.5f);
    std::vector<float> hp_filtered = hearthis::apply_high_pass_filter(dc_signal, 48000, 80.0f);
    assert(hp_filtered.size() == dc_signal.size());
    // After several hundred samples of steady DC, output should decay near 0
    assert(std::abs(hp_filtered.back()) < 0.01f);
    std::cout << "  [PASS] 80 Hz high-pass filter successfully attenuates DC offset." << std::endl;

    // Test 6: Bounded peak normalization
    // 6a: Signal with peak 0.20 (gain needed ~4.45x, below 10.0x cap) reaches target peak
    std::vector<float> moderate_signal = {0.1f, -0.2f, 0.15f, -0.05f};
    std::vector<float> norm_mod = hearthis::normalize_audio(moderate_signal, -1.0f, -48.0f);
    float target_linear = std::pow(10.0f, -1.0f / 20.0f); // ~0.891
    float peak_mod = 0.0f;
    for (float s : norm_mod) {
        if (std::abs(s) > peak_mod) peak_mod = std::abs(s);
    }
    assert(std::abs(peak_mod - target_linear) < 1e-3f);

    // 6b: Very quiet signal with peak 0.02 (gain clamped at 10.0x safety ceiling)
    std::vector<float> faint_signal = {0.005f, -0.02f, 0.01f, -0.015f};
    std::vector<float> norm_faint = hearthis::normalize_audio(faint_signal, -1.0f, -48.0f);
    float peak_faint = 0.0f;
    for (float s : norm_faint) {
        if (std::abs(s) > peak_faint) peak_faint = std::abs(s);
    }
    assert(std::abs(peak_faint - 0.20f) < 1e-3f); // 0.02 * 10.0 = 0.20

    // 6c: Thermal noise below -48 dBFS floor should NOT be amplified
    std::vector<float> noise_floor(100, 0.0001f);
    std::vector<float> noise_out = hearthis::normalize_audio(noise_floor, -1.0f, -48.0f);
    assert(noise_out == noise_floor);
    std::cout << "  [PASS] Bounded peak normalization boosts quiet audio and preserves noise gate floor." << std::endl;

    // Test 7: End-to-end signal conditioning (condition_audio)
    std::vector<float> raw_mic_stereo = {0.02f, 0.02f, -0.04f, -0.04f};
    std::vector<float> conditioned_mic = hearthis::condition_audio(
        raw_mic_stereo, 2, 48000, hearthis::AudioSource::Microphone
    );
    assert(conditioned_mic.size() == 2);

    std::vector<float> raw_speakers_stereo = {0.5f, 0.1f, -0.2f, 0.4f};
    std::vector<float> conditioned_speakers = hearthis::condition_audio(
        raw_speakers_stereo, 2, 48000, hearthis::AudioSource::Speakers
    );
    assert(conditioned_speakers.size() == 2);
    assert(std::abs(conditioned_speakers[0] - 0.3f) < 1e-5f);
    std::cout << "  [PASS] Source-aware condition_audio pipeline verified for both Speakers and Microphone." << std::endl;

    // Test 8: WAV file generation
    std::vector<float> mono_tone(48000, 0.25f);
    std::vector<uint8_t> wav = hearthis::pcm_to_wav_bytes(mono_tone, 48000);
    assert(wav.size() == 44 + (48000 * sizeof(int16_t)));
    assert(wav[0] == 'R' && wav[1] == 'I' && wav[2] == 'F' && wav[3] == 'F');
    assert(wav[8] == 'W' && wav[9] == 'A' && wav[10] == 'V' && wav[11] == 'E');
    std::cout << "  [PASS] 44-byte WAV header and PCM byte packing verified (" << wav.size() << " bytes)." << std::endl;

    std::cout << "\n>>> ALL AUDIO PROCESSOR TESTS PASSED! <<<\n" << std::endl;
    return 0;
}
