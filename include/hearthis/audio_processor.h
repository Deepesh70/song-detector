#pragma once

#include <vector>
#include <cstdint>

namespace hearthis {

// Structure holding basic audio format info
struct AudioConfig {
    uint32_t sample_rate = 48000;
    uint16_t channels = 2;
    float silence_threshold_db = -50.0f;
};

// Check if the audio buffer energy is below the silence threshold (-50 dBFS)
bool is_silent(const std::vector<float>& samples, float threshold_db = -50.0f);

// Convert interleaved stereo [L, R, L, R, ...] into mono [M, M, ...]
std::vector<float> stereo_to_mono(const std::vector<float>& stereo_samples);

// Convert float samples (-1.0 to +1.0) into a standard 44-byte RIFF WAV byte array
std::vector<uint8_t> pcm_to_wav_bytes(const std::vector<float>& mono_samples, uint32_t sample_rate = 48000);

} // namespace hearthis
