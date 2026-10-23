#pragma once

#include <string>
#include <vector>
#include <cstdint>

namespace hearthis {

// Song match result returned from cloud recognition
struct RecognitionResult {
    bool matched = false;
    std::string title;
    std::string artist;
    std::string album;
    std::string provider;
    std::string spotify_url;
    std::string youtube_url;
    std::string error_message;
};

// ACRCloud 3-key authentication credentials
struct AcrCredentials {
    std::string host;
    std::string access_key;
    std::string access_secret;
};

class ApiClient {
public:
    ApiClient();
    ~ApiClient();

    // Primary Default Provider: ACRCloud
    RecognitionResult recognize_acrcloud(
        const std::vector<uint8_t>& wav_bytes,
        const AcrCredentials& creds
    );

    // Secondary Choice Provider: AudD
    RecognitionResult recognize_audd(
        const std::vector<uint8_t>& wav_bytes,
        const std::string& api_token
    );

    // General HTTPS POST helper for multipart data using native WinHTTP
    std::string post_multipart(
        const std::wstring& host,
        const std::wstring& path,
        const std::vector<uint8_t>& body,
        const std::string& boundary
    );

private:
    void* session_handle_ = nullptr; // HINTERNET session
};

// Lightweight zero-dependency JSON string field extractor
std::string extract_json_field(const std::string& json, const std::string& key);

// Native Windows BCrypt HMAC-SHA1 Base64 signer for ACRCloud authentication
std::string hmac_sha1_base64(const std::string& key, const std::string& message);

} // namespace hearthis
