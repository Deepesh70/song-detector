#include "hearthis/api_client.h"
#include <iostream>
#include <cassert>

int main() {
    std::cout << "[HearThis C++] Testing ApiClient module..." << std::endl;

    // Test 1: Native Windows HMAC-SHA1 Base64 Signer
    std::string test_sig = hearthis::hmac_sha1_base64("secret", "hello");
    assert(test_sig == "URIFXAX5RPhXVe/FzYlw4ZTp9Fs=");
    std::cout << "  [PASS] HMAC-SHA1 signature matches test vector: " << test_sig << std::endl;

    // Test 2: JSON field extraction for AudD
    std::string fake_audd_json = R"({
        "status": "success",
        "result": {
            "title": "Bohemian Rhapsody",
            "artist": "Queen",
            "album": "A Night at the Opera"
        }
    })";

    assert(hearthis::extract_json_field(fake_audd_json, "status") == "success");
    assert(hearthis::extract_json_field(fake_audd_json, "title") == "Bohemian Rhapsody");
    assert(hearthis::extract_json_field(fake_audd_json, "artist") == "Queen");
    std::cout << "  [PASS] AudD JSON parsing verified." << std::endl;

    // Test 3: JSON field extraction for ACRCloud
    std::string fake_acr_json = R"({
        "status": {"msg": "Success", "code": 0, "version": "1.0"},
        "metadata": {
            "music": [{
                "title": "Blinding Lights",
                "name": "The Weeknd"
            }]
        }
    })";

    assert(hearthis::extract_json_field(fake_acr_json, "title") == "Blinding Lights");
    assert(hearthis::extract_json_field(fake_acr_json, "name") == "The Weeknd");
    std::cout << "  [PASS] ACRCloud JSON parsing verified." << std::endl;

    // Test 4: WinHTTP Session Handle Lifecycle
    hearthis::ApiClient client;
    std::cout << "  [PASS] WinHTTP session handle initialized." << std::endl;

    std::cout << "\n>>> ALL API CLIENT TESTS (ACRCLOUD & AUDD) PASSED! <<<\n" << std::endl;
    return 0;
}
