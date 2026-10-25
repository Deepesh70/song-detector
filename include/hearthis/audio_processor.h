#pragma once

#include "hearthis/wasapi_capture.h"

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

// Channel-aware downmixing (1ch passthrough, 2ch average, multi-channel average)
std::vector<float> to_mono(const std::vector<float>& samples, uint16_t channels = 2);

// Backward-compatibility wrapper for stereo downmix
inline std::vector<float> stereo_to_mono(const std::vector<float>& stereo_samples) {
    return to_mono(stereo_samples, 2);
}

// 1st-order IIR high-pass filter (removes DC bias and 50/60 Hz mains hum/rumble)
std::vector<float> apply_high_pass_filter(
    const std::vector<float>& samples,
    uint32_t sample_rate = 48000,
    float cutoff_hz = 80.0f
);

// Bounded peak normalization with a noise-gate floor
std::vector<float> normalize_audio(
    const std::vector<float>& samples,
    float target_peak_dbfs = -1.0f,
    float min_rms_dbfs = -48.0f
);

// End-to-end signal conditioning tailored by input source
std::vector<float> condition_audio(
    const std::vector<float>& raw_samples,
    uint16_t channels,
    uint32_t sample_rate,
    AudioSource source
);

// Convert float samples (-1.0 to +1.0) into a standard 44-byte RIFF WAV byte array
std::vector<uint8_t> pcm_to_wav_bytes(const std::vector<float>& mono_samples, uint32_t sample_rate = 48000);

} // namespace hearthis
