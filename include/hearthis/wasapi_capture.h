#pragma once

#include <vector>
#include <string>
#include <cstdint>
#include <atomic>

namespace hearthis {

// Audio input source selection
enum class AudioSource {
    Speakers = 0,    // System audio loopback (internal playback without mic bleed)
    Microphone = 1   // Physical or external microphone (live room/ambient music)
};

// Result struct returned after capturing audio
struct CapturedAudio {
    std::vector<float> samples;     // Interleaved float samples
    uint32_t sample_rate = 48000;    // Hardware sample rate
    uint16_t channels = 2;          // Channels (1 for mono, 2 for stereo)
    bool success = false;           // True if recording succeeded
    std::string error_message;     // Error description if failed
};

class WasapiCapture {
public:
    WasapiCapture();
    ~WasapiCapture();

    // Unified audio capture entry point supporting Speakers (Loopback) and Microphone
    CapturedAudio capture_audio(
        AudioSource source = AudioSource::Speakers,
        double duration_seconds = 5.0,
        std::atomic<bool>* cancel_token = nullptr
    );

    // Inline backward-compatibility wrappers
    inline CapturedAudio capture_loopback(double duration_seconds = 5.0) {
        return capture_audio(AudioSource::Speakers, duration_seconds);
    }

    inline CapturedAudio capture_microphone(double duration_seconds = 5.0) {
        return capture_audio(AudioSource::Microphone, duration_seconds);
    }
};

} // namespace hearthis
