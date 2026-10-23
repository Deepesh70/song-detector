#include "hearthis/api_client.h"

#include <windows.h>
#include <winhttp.h>
#include <wincrypt.h>
#include <bcrypt.h>
#include <chrono>
#include <sstream>
#include <iostream>
#include <cstring>

#pragma comment(lib, "winhttp.lib")
#pragma comment(lib, "bcrypt.lib")
#pragma comment(lib, "crypt32.lib")

namespace hearthis {

ApiClient::ApiClient() {
    session_handle_ = WinHttpOpen(
        L"HearThis-Native/1.0",
        WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
        WINHTTP_NO_PROXY_NAME,
        WINHTTP_NO_PROXY_BYPASS,
        0
    );
}

ApiClient::~ApiClient() {
    if (session_handle_) {
        WinHttpCloseHandle(reinterpret_cast<HINTERNET>(session_handle_));
        session_handle_ = nullptr;
    }
}

std::string hmac_sha1_base64(const std::string& key, const std::string& message) {
    BCRYPT_ALG_HANDLE hAlg = nullptr;
    BCRYPT_HASH_HANDLE hHash = nullptr;

    NTSTATUS status = BCryptOpenAlgorithmProvider(
        &hAlg,
        BCRYPT_SHA1_ALGORITHM,
        nullptr,
        BCRYPT_ALG_HANDLE_HMAC_FLAG
    );

    if (status != 0) {
        return "";
    }

    DWORD hashObjectSize = 0, resultSize = 0;
    BCryptGetProperty(hAlg, BCRYPT_OBJECT_LENGTH, reinterpret_cast<PBYTE>(&hashObjectSize), sizeof(DWORD), &resultSize, 0);
    std::vector<UCHAR> hashObject(hashObjectSize);

    status = BCryptCreateHash(
        hAlg,
        &hHash,
        hashObject.data(),
        hashObjectSize,
        reinterpret_cast<PUCHAR>(const_cast<char*>(key.data())),
        static_cast<ULONG>(key.size()),
        0
    );

    if (status != 0) {
        BCryptCloseAlgorithmProvider(hAlg, 0);
        return "";
    }

    BCryptHashData(
        hHash,
        reinterpret_cast<PUCHAR>(const_cast<char*>(message.data())),
        static_cast<ULONG>(message.size()),
        0
    );

    UCHAR hashDigest[20] = {0}; // SHA-1 is 20 bytes
    BCryptFinishHash(hHash, hashDigest, sizeof(hashDigest), 0);

    BCryptDestroyHash(hHash);
    BCryptCloseAlgorithmProvider(hAlg, 0);

    // Convert 20-byte digest to Base64 using standard Windows Crypto API
    DWORD b64Len = 0;
    CryptBinaryToStringA(hashDigest, sizeof(hashDigest), CRYPT_STRING_BASE64 | CRYPT_STRING_NOCRLF, nullptr, &b64Len);
    std::string b64(b64Len, '\0');
    CryptBinaryToStringA(hashDigest, sizeof(hashDigest), CRYPT_STRING_BASE64 | CRYPT_STRING_NOCRLF, &b64[0], &b64Len);

    // Strip trailing null if present
    size_t actual_len = std::strlen(b64.c_str());
    b64.resize(actual_len);
    return b64;
}

std::string extract_json_field(const std::string& json, const std::string& key) {
    std::string pattern = "\"" + key + "\":";
    size_t pos = json.find(pattern);
    if (pos == std::string::npos) {
        return "";
    }

    pos += pattern.length();
    while (pos < json.length() && (json[pos] == ' ' || json[pos] == '\t' || json[pos] == '\r' || json[pos] == '\n')) {
        pos++;
    }

    if (pos >= json.length()) {
        return "";
    }

    if (json[pos] == '"') {
        pos++; // skip opening quote
        size_t end_quote = json.find('"', pos);
        if (end_quote != std::string::npos) {
            return json.substr(pos, end_quote - pos);
        }
    }

    return "";
}

std::string ApiClient::post_multipart(
    const std::wstring& host,
    const std::wstring& path,
    const std::vector<uint8_t>& body,
    const std::string& boundary
) {
    if (!session_handle_) {
        return "";
    }

    HINTERNET hConnect = WinHttpConnect(
        reinterpret_cast<HINTERNET>(session_handle_),
        host.c_str(),
        INTERNET_DEFAULT_HTTPS_PORT,
        0
    );

    if (!hConnect) {
        return "";
    }

    HINTERNET hRequest = WinHttpOpenRequest(
        hConnect,
        L"POST",
        path.c_str(),
        nullptr,
        WINHTTP_NO_REFERER,
        WINHTTP_DEFAULT_ACCEPT_TYPES,
        WINHTTP_FLAG_SECURE
    );

    if (!hRequest) {
        WinHttpCloseHandle(hConnect);
        return "";
    }

    std::wstring headers = L"Content-Type: multipart/form-data; boundary=" + 
                           std::wstring(boundary.begin(), boundary.end()) + L"\r\n";

    BOOL bResults = WinHttpSendRequest(
        hRequest,
        headers.c_str(),
        static_cast<DWORD>(headers.length()),
        const_cast<uint8_t*>(body.data()),
        static_cast<DWORD>(body.size()),
        static_cast<DWORD>(body.size()),
        0
    );

    std::string response_text;

    if (bResults) {
        bResults = WinHttpReceiveResponse(hRequest, nullptr);
    }

    if (bResults) {
        DWORD bytes_available = 0;
        do {
            bytes_available = 0;
            if (!WinHttpQueryDataAvailable(hRequest, &bytes_available)) {
                break;
            }

            if (bytes_available == 0) {
                break;
            }

            std::vector<char> buffer(bytes_available + 1, 0);
            DWORD bytes_read = 0;
            if (WinHttpReadData(hRequest, buffer.data(), bytes_available, &bytes_read)) {
                response_text.append(buffer.data(), bytes_read);
            }
        } while (bytes_available > 0);
    }

    WinHttpCloseHandle(hRequest);
    WinHttpCloseHandle(hConnect);

    return response_text;
}

// 1. Primary Default Provider: ACRCloud
RecognitionResult ApiClient::recognize_acrcloud(
    const std::vector<uint8_t>& wav_bytes,
    const AcrCredentials& creds
) {
    RecognitionResult result;
    result.provider = "ACRCloud";

    if (creds.host.empty() || creds.access_key.empty() || creds.access_secret.empty()) {
        result.error_message = "ACRCloud requires Host, Access Key, and Access Secret.";
        return result;
    }

    if (wav_bytes.empty()) {
        result.error_message = "Audio buffer is empty.";
        return result;
    }

    // Build HMAC-SHA1 signature
    auto now_sec = std::chrono::duration_cast<std::chrono::seconds>(
        std::chrono::system_clock::now().time_since_epoch()
    ).count();
    std::string timestamp = std::to_string(now_sec);

    std::string string_to_sign = "POST\n/v1/identify\n" + creds.access_key + "\naudio\n1\n" + timestamp;
    std::string signature = hmac_sha1_base64(creds.access_secret, string_to_sign);

    if (signature.empty()) {
        result.error_message = "Failed to calculate ACRCloud HMAC signature.";
        return result;
    }

    std::string boundary = "----HearThisAcrBoundary123456";
    std::string crlf = "\r\n";
    std::vector<uint8_t> payload;

    auto append_field = [&](const std::string& name, const std::string& value) {
        std::string part = "--" + boundary + crlf +
                           "Content-Disposition: form-data; name=\"" + name + "\"" + crlf + crlf +
                           value + crlf;
        payload.insert(payload.end(), part.begin(), part.end());
    };

    append_field("access_key", creds.access_key);
    append_field("sample_bytes", std::to_string(wav_bytes.size()));
    append_field("timestamp", timestamp);
    append_field("signature", signature);
    append_field("data_type", "audio");
    append_field("signature_version", "1");

    // Audio file attachment
    std::string file_header = "--" + boundary + crlf +
                              "Content-Disposition: form-data; name=\"sample\"; filename=\"sample.wav\"" + crlf +
                              "Content-Type: audio/wav" + crlf + crlf;
    payload.insert(payload.end(), file_header.begin(), file_header.end());
    payload.insert(payload.end(), wav_bytes.begin(), wav_bytes.end());

    std::string end_marker = crlf + "--" + boundary + "--" + crlf;
    payload.insert(payload.end(), end_marker.begin(), end_marker.end());

    // Clean host string (strip https:// if user pasted full url)
    std::string clean_host = creds.host;
    if (clean_host.find("https://") == 0) clean_host = clean_host.substr(8);
    if (clean_host.find("http://") == 0) clean_host = clean_host.substr(7);
    while (!clean_host.empty() && (clean_host.back() == '/' || clean_host.back() == ' ')) clean_host.pop_back();

    std::wstring w_host(clean_host.begin(), clean_host.end());
    std::string response = post_multipart(w_host, L"/v1/identify", payload, boundary);

    if (response.empty()) {
        result.error_message = "Network error: Failed to connect to ACRCloud host.";
        return result;
    }

    // Check status code: "code":0 means match found; "code":1001 means no match
    if (response.find("\"code\":0") == std::string::npos) {
        if (response.find("\"code\":1001") != std::string::npos) {
            result.matched = false;
            return result;
        }
        std::string msg = extract_json_field(response, "msg");
        result.error_message = msg.empty() ? "No match found in ACRCloud." : ("ACRCloud: " + msg);
        return result;
    }

    // Extract title, artist, album from metadata.music array
    result.title = extract_json_field(response, "title");
    result.artist = extract_json_field(response, "name"); // artist name
    result.album = extract_json_field(response, "name");  // fallback to album name or track

    if (!result.title.empty()) {
        result.matched = true;
        result.youtube_url = "https://www.youtube.com/results?search_query=" + result.title + "+" + result.artist;
    } else {
        result.matched = false;
    }

    return result;
}

// 2. Secondary Choice Provider: AudD
RecognitionResult ApiClient::recognize_audd(
    const std::vector<uint8_t>& wav_bytes,
    const std::string& api_token
) {
    RecognitionResult result;
    result.provider = "AudD";

    if (wav_bytes.empty()) {
        result.error_message = "Audio buffer is empty.";
        return result;
    }

    std::string boundary = "----HearThisAuddBoundary789456";
    std::string crlf = "\r\n";
    std::vector<uint8_t> payload;

    auto append_str = [&payload](const std::string& s) {
        payload.insert(payload.end(), s.begin(), s.end());
    };

    if (!api_token.empty()) {
        append_str("--" + boundary + crlf);
        append_str("Content-Disposition: form-data; name=\"api_token\"" + crlf + crlf);
        append_str(api_token + crlf);
    }

    append_str("--" + boundary + crlf);
    append_str("Content-Disposition: form-data; name=\"return\"" + crlf + crlf);
    append_str("spotify,youtube" + crlf);

    append_str("--" + boundary + crlf);
    append_str("Content-Disposition: form-data; name=\"file\"; filename=\"recording.wav\"" + crlf);
    append_str("Content-Type: audio/wav" + crlf + crlf);
    payload.insert(payload.end(), wav_bytes.begin(), wav_bytes.end());
    append_str(crlf);

    append_str("--" + boundary + "--" + crlf);

    std::string response = post_multipart(L"api.audd.io", L"/", payload, boundary);

    if (response.empty()) {
        result.error_message = "Network error: Failed to receive response from AudD API.";
        return result;
    }

    std::string status = extract_json_field(response, "status");
    if (status != "success") {
        result.error_message = "API error: " + response.substr(0, 100);
        return result;
    }

    if (response.find("\"result\":null") != std::string::npos) {
        result.matched = false;
        return result;
    }

    result.title = extract_json_field(response, "title");
    result.artist = extract_json_field(response, "artist");
    result.album = extract_json_field(response, "album");

    if (!result.title.empty()) {
        result.matched = true;
        result.youtube_url = "https://www.youtube.com/results?search_query=" + result.title + "+" + result.artist;
    } else {
        result.matched = false;
    }

    return result;
}

} // namespace hearthis
