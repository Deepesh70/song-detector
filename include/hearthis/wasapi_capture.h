#pragma once

#include <vector>
#include <string>
#include <cstdint>

namespace hearthis {

// Result struct returned after capturing loopback audio
struct CapturedAudio {
    std::vector<float> samples;     // Interleaved float samples (Left, Right, Left, Right...)
    uint32_t sample_rate = 48000;    // Hardware sample rate (typically 48,000 Hz)
    uint16_t channels = 2;          // Channels (typically 2 for stereo)
    bool success = false;           // True if recording succeeded
    std::string error_message;     // Error description if failed
};

class WasapiCapture {
public:
    WasapiCapture();
    ~WasapiCapture();

    // Captures loopback audio from Windows default playback device (speakers/headphones)
    CapturedAudio capture_loopback(double duration_seconds = 5.0);
};

} // namespace hearthis
