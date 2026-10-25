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

std::vector<float> to_mono(const std::vector<float>& samples, uint16_t channels) {
    if (samples.empty() || channels <= 1) {
        return samples;
    }

    size_t frame_count = samples.size() / channels;
    std::vector<float> mono(frame_count, 0.0f);
    float inv_channels = 1.0f / static_cast<float>(channels);

    for (size_t i = 0; i < frame_count; ++i) {
        float sum = 0.0f;
        for (uint16_t c = 0; c < channels; ++c) {
            sum += samples[i * channels + c];
        }
        mono[i] = sum * inv_channels;
    }

    return mono;
}

std::vector<float> apply_high_pass_filter(const std::vector<float>& samples, uint32_t sample_rate, float cutoff_hz) {
    if (samples.empty()) {
        return samples;
    }

    // 1st-order IIR RC high-pass filter: y[n] = alpha * (y[n-1] + x[n] - x[n-1])
    float dt = 1.0f / static_cast<float>(sample_rate);
    float rc = 1.0f / (2.0f * 3.14159265358979323846f * cutoff_hz);
    float alpha = rc / (rc + dt);

    std::vector<float> filtered(samples.size());
    filtered[0] = samples[0];

    for (size_t i = 1; i < samples.size(); ++i) {
        filtered[i] = alpha * (filtered[i - 1] + samples[i] - samples[i - 1]);
    }

    return filtered;
}

std::vector<float> normalize_audio(const std::vector<float>& samples, float target_peak_dbfs, float min_rms_dbfs) {
    if (samples.empty()) {
        return samples;
    }

    double sum_squares = 0.0;
    float max_abs = 0.0f;

    for (float s : samples) {
        sum_squares += static_cast<double>(s) * static_cast<double>(s);
        float a = std::fabs(s);
        if (a > max_abs) {
            max_abs = a;
        }
    }

    double rms = std::sqrt(sum_squares / static_cast<double>(samples.size()));
    double rms_dbfs = 20.0 * std::log10(rms + 1e-9);

    // If signal is below minimum noise floor or peak is negligible, don't boost thermal hiss
    if (rms_dbfs < static_cast<double>(min_rms_dbfs) || max_abs < 1e-4f) {
        return samples;
    }

    // Linear target peak (e.g. -1.0 dBFS ≈ 0.891)
    float target_linear = std::pow(10.0f, target_peak_dbfs / 20.0f);
    // Safety gain cap of 20 dB (10.0x) to prevent distortion
    float gain = std::min(target_linear / max_abs, 10.0f);

    std::vector<float> normalized(samples.size());
    for (size_t i = 0; i < samples.size(); ++i) {
        normalized[i] = std::clamp(samples[i] * gain, -1.0f, 1.0f);
    }

    return normalized;
}

std::vector<float> condition_audio(
    const std::vector<float>& raw_samples,
    uint16_t channels,
    uint32_t sample_rate,
    AudioSource source
) {
    // 1. Channel-aware downmixing
    std::vector<float> mono = to_mono(raw_samples, channels);

    if (source == AudioSource::Microphone) {
        // 2. 80 Hz high-pass filter: strip DC offset and 50/60 Hz mains hum/rumble
        mono = apply_high_pass_filter(mono, sample_rate, 80.0f);

        // 3. Peak normalization with noise-gate floor: scale to -1.0 dBFS if RMS >= -48 dBFS
        mono = normalize_audio(mono, -1.0f, -48.0f);
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
        sample = std::clamp(sample, -1.0f, 1.0f);
        pcm_data[i] = static_cast<int16_t>(sample * 32767.0f);
    }

    return wav;
}

} // namespace hearthis
