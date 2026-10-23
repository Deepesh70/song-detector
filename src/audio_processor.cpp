#include "hearthis/audio_processor.h"

#include <cmath>
#include <algorithm>
#include <cstring>

namespace hearthis {

bool is_silent(const std::vector<float>& samples, float threshold_db) {
    if (samples.empty()) {
        return true;
    }

    // 1. Calculate Root-Mean-Square (RMS) energy
    double sum_squares = 0.0;
    for (float sample : samples) {
        sum_squares += static_cast<double>(sample) * static_cast<double>(sample);
    }

    double mean_square = sum_squares / static_cast<double>(samples.size());
    double rms = std::sqrt(mean_square);

    // 2. Convert to decibels relative to full scale (dBFS)
    // Add 1e-9 to prevent log10(0) which would give -infinity
    double dbfs = 20.0 * std::log10(rms + 1e-9);

    return dbfs < threshold_db;
}

std::vector<float> stereo_to_mono(const std::vector<float>& stereo_samples) {
    size_t mono_count = stereo_samples.size() / 2;
    std::vector<float> mono(mono_count);

    // Interleaved stereo: [Left_0, Right_0, Left_1, Right_1, ...]
    for (size_t i = 0; i < mono_count; ++i) {
        mono[i] = (stereo_samples[2 * i] + stereo_samples[2 * i + 1]) * 0.5f;
    }

    return mono;
}

std::vector<uint8_t> pcm_to_wav_bytes(const std::vector<float>& mono_samples, uint32_t sample_rate) {
    uint16_t num_channels = 1;
    uint16_t bits_per_sample = 16;
    uint32_t byte_rate = sample_rate * num_channels * (bits_per_sample / 8);
    uint16_t block_align = num_channels * (bits_per_sample / 8);

    uint32_t data_bytes = static_cast<uint32_t>(mono_samples.size() * sizeof(int16_t));
    uint32_t total_file_size = 44 + data_bytes;

    std::vector<uint8_t> wav(total_file_size);
    uint8_t* ptr = wav.data();

    // Helper lambda to copy raw values into the byte buffer
    auto write_bytes = [&ptr](const void* src, size_t size) {
        std::memcpy(ptr, src, size);
        ptr += size;
    };

    uint32_t chunk_size = 36 + data_bytes;
    uint32_t subchunk1_size = 16;
    uint16_t audio_format = 1; // 1 = Linear PCM

    // Standard 44-byte RIFF WAV Header
    write_bytes("RIFF", 4);
    write_bytes(&chunk_size, 4);
    write_bytes("WAVE", 4);
    write_bytes("fmt ", 4);
    write_bytes(&subchunk1_size, 4);
    write_bytes(&audio_format, 2);
    write_bytes(&num_channels, 2);
    write_bytes(&sample_rate, 4);
    write_bytes(&byte_rate, 4);
    write_bytes(&block_align, 2);
    write_bytes(&bits_per_sample, 2);
    write_bytes("data", 4);
    write_bytes(&data_bytes, 4);

    // Convert float samples (-1.0 to 1.0) to 16-bit signed integers (-32768 to 32767)
    int16_t* pcm_data = reinterpret_cast<int16_t*>(ptr);
    for (size_t i = 0; i < mono_samples.size(); ++i) {
        float sample = mono_samples[i];
        // Clamp to prevent audio clipping distortion
        sample = std::max(-1.0f, std::min(1.0f, sample));
        pcm_data[i] = static_cast<int16_t>(sample * 32767.0f);
    }

    return wav;
}

} // namespace hearthis
