#include "hearthis/audio_processor.h"
#include "hearthis/wasapi_capture.h"
#include "hearthis/api_client.h"

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <commctrl.h>
#include <dwmapi.h>
#include <shellapi.h>
#include <string>
#include <vector>
#include <thread>
#include <fstream>
#include <sstream>
#include <atomic>
#include <chrono>
#include <algorithm>

#pragma comment(lib, "user32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "dwmapi.lib")
#pragma comment(lib, "comctl32.lib")
#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "oleaut32.lib")
#pragma comment(lib, "winhttp.lib")
#pragma comment(lib, "bcrypt.lib")
#pragma comment(lib, "crypt32.lib")

#ifndef DWMWA_USE_IMMERSIVE_DARK_MODE
#define DWMWA_USE_IMMERSIVE_DARK_MODE 20
#endif

// Control IDs
#define IDC_BTN_SETTINGS        100
#define IDC_COMBO_PROVIDER      101
#define IDC_BTN_IDENTIFY        102
#define IDC_BTN_BROWSER         103
#define IDC_BTN_GET_CREDS       104
#define IDC_BTN_YOUTUBE         105
#define IDC_BTN_COPY            106

// Segmented Toggle IDs
#define IDC_TOGGLE_SRC_SPEAKERS 110
#define IDC_TOGGLE_SRC_MIC      111
#define IDC_TOGGLE_DUR_5S       112
#define IDC_TOGGLE_DUR_10S      113

#define IDC_EDIT_ACR_HOST       201
#define IDC_EDIT_ACR_KEY        202
#define IDC_EDIT_ACR_SECRET     203
#define IDC_EDIT_AUDD_TOKEN     204

// Custom Windows Messages & Timers
#define WM_RECOGNITION_DONE     (WM_USER + 1)
#define TIMER_SCAN_PROGRESS     1

// Global UI State & Handles
HWND g_hwnd_main = nullptr;
HWND g_hwnd_btn_settings = nullptr;
HWND g_hwnd_provider = nullptr;
HWND g_hwnd_btn_get_creds = nullptr;

// Segmented Buttons
HWND g_hwnd_btn_src_speakers = nullptr;
HWND g_hwnd_btn_src_mic = nullptr;
HWND g_hwnd_btn_dur_5s = nullptr;
HWND g_hwnd_btn_dur_10s = nullptr;

HWND g_hwnd_btn_identify = nullptr;
HWND g_hwnd_status = nullptr;

// Card Action Buttons
HWND g_hwnd_btn_browser = nullptr;
HWND g_hwnd_btn_youtube = nullptr;
HWND g_hwnd_btn_copy = nullptr;

// Result Card Displays
HWND g_hwnd_song_title = nullptr;
HWND g_hwnd_song_artist = nullptr;
HWND g_hwnd_card_badge = nullptr;
HWND g_hwnd_subtitle = nullptr;

// Settings Header Labels & Edit Controls
HWND g_hwnd_lbl_provider = nullptr;
HWND g_hwnd_lbl_acr_host = nullptr;
HWND g_hwnd_edit_acr_host = nullptr;
HWND g_hwnd_lbl_acr_key = nullptr;
HWND g_hwnd_edit_acr_key = nullptr;
HWND g_hwnd_lbl_acr_secret = nullptr;
HWND g_hwnd_edit_acr_secret = nullptr;
HWND g_hwnd_lbl_audd_token = nullptr;
HWND g_hwnd_edit_audd_token = nullptr;

// Symmetrical Toggle Labels
HWND g_hwnd_lbl_src = nullptr;
HWND g_hwnd_lbl_dur = nullptr;

// Fonts
HFONT g_font_title = nullptr;
HFONT g_font_song_title = nullptr;
HFONT g_font_bold = nullptr;
HFONT g_font_regular = nullptr;
HFONT g_font_small = nullptr;

// GDI Brushes & Pens
HBRUSH g_bg_brush = nullptr;
HBRUSH g_input_brush = nullptr;
HBRUSH g_card_brush = nullptr;
HBRUSH g_accent_brush = nullptr;
HPEN g_border_pen = nullptr;
HPEN g_border_subtle_pen = nullptr;

COLORREF g_status_color = RGB(156, 163, 175);
std::string g_current_youtube_url = "";
std::string g_current_track_string = "";
std::atomic<bool> g_cancel_scan{false};

// Animation & Collapsible Settings State
bool g_settings_expanded = false;
bool g_is_scanning = false;
float g_scan_progress = 0.0f;
int g_scan_target_seconds = 10;
std::chrono::steady_clock::time_point g_scan_start_time;

// Configuration persistence paths
std::string get_load_config_file_path() {
    char* appdata = nullptr;
    size_t len = 0;
    if (_dupenv_s(&appdata, &len, "APPDATA") == 0 && appdata) {
        std::string base(appdata);
        free(appdata);

        std::string new_path = base + "\\HearThis\\config.txt";
        DWORD attr = GetFileAttributesA(new_path.c_str());
        if (attr != INVALID_FILE_ATTRIBUTES) {
            return new_path;
        }

        std::string legacy_path = base + "\\SongDetector\\native_config.txt";
        DWORD legacy_attr = GetFileAttributesA(legacy_path.c_str());
        if (legacy_attr != INVALID_FILE_ATTRIBUTES) {
            return legacy_path;
        }

        std::string new_dir = base + "\\HearThis";
        CreateDirectoryA(new_dir.c_str(), nullptr);
        return new_path;
    }
    return "config.txt";
}

std::string get_save_config_file_path() {
    char* appdata = nullptr;
    size_t len = 0;
    if (_dupenv_s(&appdata, &len, "APPDATA") == 0 && appdata) {
        std::string dir = std::string(appdata) + "\\HearThis";
        CreateDirectoryA(dir.c_str(), nullptr);
        std::string path = dir + "\\config.txt";
        free(appdata);
        return path;
    }
    return "config.txt";
}

struct AppSettings {
    int provider_index = 0; // 0 = ACRCloud, 1 = AudD
    int duration_seconds = 10; // 5 or 10
    hearthis::AudioSource audio_source = hearthis::AudioSource::Speakers;
    std::string acr_host = "identify-eu-west-1.acrcloud.com";
    std::string acr_key = "";
    std::string acr_secret = "";
    std::string audd_token = "";
};

AppSettings g_settings;

AppSettings load_settings() {
    AppSettings s;
    std::ifstream file(get_load_config_file_path());
    if (file.is_open()) {
        std::string line;
        while (std::getline(file, line)) {
            size_t eq = line.find('=');
            if (eq != std::string::npos) {
                std::string k = line.substr(0, eq);
                std::string v = line.substr(eq + 1);
                if (k == "provider") s.provider_index = std::stoi(v);
                else if (k == "duration") s.duration_seconds = std::stoi(v);
                else if (k == "audio_source" || k == "source") {
                    s.audio_source = (std::stoi(v) == 1) ? hearthis::AudioSource::Microphone : hearthis::AudioSource::Speakers;
                }
                else if (k == "acr_host") s.acr_host = v;
                else if (k == "acr_key") s.acr_key = v;
                else if (k == "acr_secret") s.acr_secret = v;
                else if (k == "audd_token") s.audd_token = v;
            }
        }
        file.close();
    }
    return s;
}

void save_settings(const AppSettings& s) {
    std::ofstream file(get_save_config_file_path());
    if (file.is_open()) {
        file << "provider=" << s.provider_index << "\n";
        file << "duration=" << s.duration_seconds << "\n";
        file << "audio_source=" << static_cast<int>(s.audio_source) << "\n";
        file << "acr_host=" << s.acr_host << "\n";
        file << "acr_key=" << s.acr_key << "\n";
        file << "acr_secret=" << s.acr_secret << "\n";
        file << "audd_token=" << s.audd_token << "\n";
        file.close();
    }
}

void copy_to_clipboard(HWND hwnd, const std::string& text) {
    if (text.empty()) return;
    if (OpenClipboard(hwnd)) {
        EmptyClipboard();
        HGLOBAL hGlob = GlobalAlloc(GMEM_MOVEABLE, text.size() + 1);
        if (hGlob) {
            char* pData = static_cast<char*>(GlobalLock(hGlob));
            if (pData) {
                memcpy(pData, text.c_str(), text.size() + 1);
                GlobalUnlock(hGlob);
                SetClipboardData(CF_TEXT, hGlob);
            }
        }
        CloseClipboard();
    }
}

void update_provider_visibility(int provider_index) {
    bool is_acr = (provider_index == 0);
    int show_acr = (g_settings_expanded && is_acr) ? SW_SHOW : SW_HIDE;
    int show_audd = (g_settings_expanded && !is_acr) ? SW_SHOW : SW_HIDE;

    ShowWindow(g_hwnd_lbl_acr_host, show_acr);
    ShowWindow(g_hwnd_edit_acr_host, show_acr);
    ShowWindow(g_hwnd_lbl_acr_key, show_acr);
    ShowWindow(g_hwnd_edit_acr_key, show_acr);
    ShowWindow(g_hwnd_lbl_acr_secret, show_acr);
    ShowWindow(g_hwnd_edit_acr_secret, show_acr);

    ShowWindow(g_hwnd_lbl_audd_token, show_audd);
    ShowWindow(g_hwnd_edit_audd_token, show_audd);

    if (is_acr) {
        SetWindowTextA(g_hwnd_btn_get_creds, "Get ACRCloud Keys");
    } else {
        SetWindowTextA(g_hwnd_btn_get_creds, "Get AudD Token");
    }
}

void apply_layout(HWND hwnd) {
    int w = 512;
    int h = g_settings_expanded ? 610 : 425;

    // Smoothly adjust window height
    SetWindowPos(hwnd, nullptr, 0, 0, w, h, SWP_NOMOVE | SWP_NOZORDER);

    int show_settings = g_settings_expanded ? SW_SHOW : SW_HIDE;
    ShowWindow(g_hwnd_lbl_provider, show_settings);
    ShowWindow(g_hwnd_provider, show_settings);
    ShowWindow(g_hwnd_btn_get_creds, show_settings);
    update_provider_visibility(g_settings.provider_index);

    int base_y = g_settings_expanded ? 245 : 74;

    // Symmetrical Segmented Toggles
    SetWindowPos(g_hwnd_lbl_src, nullptr, 28, base_y, 120, 16, SWP_NOZORDER);
    SetWindowPos(g_hwnd_btn_src_speakers, nullptr, 28, base_y + 20, 104, 28, SWP_NOZORDER);
    SetWindowPos(g_hwnd_btn_src_mic, nullptr, 134, base_y + 20, 104, 28, SWP_NOZORDER);

    SetWindowPos(g_hwnd_lbl_dur, nullptr, 258, base_y, 120, 16, SWP_NOZORDER);
    SetWindowPos(g_hwnd_btn_dur_5s, nullptr, 258, base_y + 20, 104, 28, SWP_NOZORDER);
    SetWindowPos(g_hwnd_btn_dur_10s, nullptr, 364, base_y + 20, 104, 28, SWP_NOZORDER);

    // Identify Button
    int btn_y = base_y + 60;
    SetWindowPos(g_hwnd_btn_identify, nullptr, 28, btn_y, 440, 38, SWP_NOZORDER);

    // Status Label
    int status_y = btn_y + 46;
    SetWindowPos(g_hwnd_status, nullptr, 28, status_y, 440, 18, SWP_NOZORDER);

    // Result Card Elements
    int card_y = status_y + 24;
    SetWindowPos(g_hwnd_card_badge, nullptr, 350, card_y + 12, 104, 18, SWP_NOZORDER);
    SetWindowPos(g_hwnd_song_title, nullptr, 44, card_y + 12, 300, 24, SWP_NOZORDER);
    SetWindowPos(g_hwnd_song_artist, nullptr, 44, card_y + 38, 400, 18, SWP_NOZORDER);

    int action_y = card_y + 68;
    SetWindowPos(g_hwnd_btn_browser, nullptr, 44, action_y, 115, 26, SWP_NOZORDER);
    SetWindowPos(g_hwnd_btn_youtube, nullptr, 167, action_y, 105, 26, SWP_NOZORDER);
    SetWindowPos(g_hwnd_btn_copy, nullptr, 280, action_y, 95, 26, SWP_NOZORDER);

    InvalidateRect(hwnd, nullptr, TRUE);
}

// Background recognition worker thread
void run_recognition_worker(HWND hwnd, AppSettings settings) {
    hearthis::WasapiCapture capture;
    double duration = static_cast<double>(settings.duration_seconds);
    hearthis::CapturedAudio audio = capture.capture_audio(settings.audio_source, duration, &g_cancel_scan);

    if (!audio.success) {
        auto* res = new hearthis::RecognitionResult();
        res->error_message = audio.error_message;
        PostMessage(hwnd, WM_RECOGNITION_DONE, 0, reinterpret_cast<LPARAM>(res));
        return;
    }

    std::vector<float> conditioned = hearthis::condition_audio(
        audio.samples,
        audio.channels,
        audio.sample_rate,
        settings.audio_source
    );

    if (hearthis::is_silent(conditioned, -50.0f)) {
        auto* res = new hearthis::RecognitionResult();
        res->error_message = (settings.audio_source == hearthis::AudioSource::Microphone)
            ? "Silence detected. Microphone input was below -50 dBFS."
            : "Silence detected. System playback was below -50 dBFS.";
        PostMessage(hwnd, WM_RECOGNITION_DONE, 0, reinterpret_cast<LPARAM>(res));
        return;
    }

    std::vector<uint8_t> wav = hearthis::pcm_to_wav_bytes(conditioned, audio.sample_rate);
    hearthis::ApiClient client;
    hearthis::RecognitionResult result;

    if (settings.provider_index == 0) {
        hearthis::AcrCredentials creds;
        creds.host = settings.acr_host;
        creds.access_key = settings.acr_key;
        creds.access_secret = settings.acr_secret;
        result = client.recognize_acrcloud(wav, creds);
    } else {
        result = client.recognize_audd(wav, settings.audd_token);
    }

    auto* res = new hearthis::RecognitionResult(result);
    PostMessage(hwnd, WM_RECOGNITION_DONE, 0, reinterpret_cast<LPARAM>(res));
}

// Main Window Procedure
LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
    case WM_CREATE: {
        g_hwnd_main = hwnd;
        g_bg_brush = CreateSolidBrush(RGB(20, 21, 25));
        g_input_brush = CreateSolidBrush(RGB(28, 30, 36));
        g_card_brush = CreateSolidBrush(RGB(26, 28, 34));
        g_accent_brush = CreateSolidBrush(RGB(16, 185, 129));
        g_border_pen = CreatePen(PS_SOLID, 1, RGB(42, 45, 53));
        g_border_subtle_pen = CreatePen(PS_SOLID, 1, RGB(55, 60, 72));

        // Modern Industrial Audio Typography (Bahnschrift / DIN 1451)
        g_font_title = CreateFontA(22, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE, ANSI_CHARSET, OUT_DEFAULT_PRECIS,
                                  CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, "Bahnschrift");
        g_font_song_title = CreateFontA(18, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE, ANSI_CHARSET, OUT_DEFAULT_PRECIS,
                                       CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, "Bahnschrift");
        g_font_bold = CreateFontA(14, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE, ANSI_CHARSET, OUT_DEFAULT_PRECIS,
                                 CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, "Bahnschrift");
        g_font_regular = CreateFontA(13, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, ANSI_CHARSET, OUT_DEFAULT_PRECIS,
                                    CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, "Bahnschrift");
        g_font_small = CreateFontA(11, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE, ANSI_CHARSET, OUT_DEFAULT_PRECIS,
                                  CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, "Bahnschrift");

        // Header Title & Logo Icon
        HICON hLogo = reinterpret_cast<HICON>(GetClassLongPtrA(hwnd, GCLP_HICON));
        if (!hLogo) {
            hLogo = LoadIconA(GetModuleHandleA(nullptr), MAKEINTRESOURCEA(1));
        }

        if (hLogo) {
            HWND hIconCtrl = CreateWindowA("STATIC", "", WS_VISIBLE | WS_CHILD | SS_ICON,
                                           28, 16, 32, 32, hwnd, nullptr, nullptr, nullptr);
            SendMessage(hIconCtrl, STM_SETICON, reinterpret_cast<WPARAM>(hLogo), 0);

            HWND hTitle = CreateWindowA("STATIC", "HearThis", WS_VISIBLE | WS_CHILD,
                                        70, 14, 180, 24, hwnd, nullptr, nullptr, nullptr);
            SendMessage(hTitle, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_title), TRUE);

            g_hwnd_subtitle = CreateWindowA("STATIC", "Native desktop audio recognition", WS_VISIBLE | WS_CHILD,
                                            70, 40, 240, 16, hwnd, nullptr, nullptr, nullptr);
            SendMessage(g_hwnd_subtitle, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);
        }

        // Top-Right Settings Button
        g_hwnd_btn_settings = CreateWindowA("BUTTON", "API Settings", WS_VISIBLE | WS_CHILD | BS_OWNERDRAW,
                                            364, 18, 104, 26, hwnd, reinterpret_cast<HMENU>(IDC_BTN_SETTINGS), nullptr, nullptr);
        SendMessage(g_hwnd_btn_settings, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        // --- Collapsible Settings Section ---
        g_hwnd_lbl_provider = CreateWindowA("STATIC", "Music Provider:", WS_CHILD, 28, 68, 120, 16, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_lbl_provider, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_bold), TRUE);

        g_hwnd_provider = CreateWindowA("COMBOBOX", "", WS_CHILD | CBS_DROPDOWNLIST | WS_VSCROLL,
                                       28, 88, 270, 120, hwnd, reinterpret_cast<HMENU>(IDC_COMBO_PROVIDER), nullptr, nullptr);
        SendMessage(g_hwnd_provider, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);
        SendMessage(g_hwnd_provider, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>("ACRCloud (Default)"));
        SendMessage(g_hwnd_provider, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>("AudD (Secondary)"));

        g_hwnd_btn_get_creds = CreateWindowA("BUTTON", "Get ACRCloud Keys", WS_CHILD | BS_OWNERDRAW,
                                             308, 87, 160, 26, hwnd, reinterpret_cast<HMENU>(IDC_BTN_GET_CREDS), nullptr, nullptr);
        SendMessage(g_hwnd_btn_get_creds, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        // ACRCloud Inputs
        g_hwnd_lbl_acr_host = CreateWindowA("STATIC", "ACRCloud Host:", WS_CHILD, 28, 120, 140, 16, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_lbl_acr_host, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        g_hwnd_edit_acr_host = CreateWindowA("EDIT", "", WS_CHILD | ES_AUTOHSCROLL,
                                             28, 138, 440, 22, hwnd, reinterpret_cast<HMENU>(IDC_EDIT_ACR_HOST), nullptr, nullptr);
        SendMessage(g_hwnd_edit_acr_host, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        g_hwnd_lbl_acr_key = CreateWindowA("STATIC", "ACRCloud Access Key:", WS_CHILD, 28, 162, 160, 16, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_lbl_acr_key, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        g_hwnd_edit_acr_key = CreateWindowA("EDIT", "", WS_CHILD | ES_AUTOHSCROLL,
                                            28, 178, 440, 22, hwnd, reinterpret_cast<HMENU>(IDC_EDIT_ACR_KEY), nullptr, nullptr);
        SendMessage(g_hwnd_edit_acr_key, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        g_hwnd_lbl_acr_secret = CreateWindowA("STATIC", "ACRCloud Access Secret:", WS_CHILD, 28, 202, 180, 16, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_lbl_acr_secret, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        g_hwnd_edit_acr_secret = CreateWindowA("EDIT", "", WS_CHILD | ES_AUTOHSCROLL | ES_PASSWORD,
                                               28, 218, 440, 22, hwnd, reinterpret_cast<HMENU>(IDC_EDIT_ACR_SECRET), nullptr, nullptr);
        SendMessage(g_hwnd_edit_acr_secret, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        // AudD Input
        g_hwnd_lbl_audd_token = CreateWindowA("STATIC", "AudD API Token:", WS_CHILD, 28, 120, 140, 16, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_lbl_audd_token, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        g_hwnd_edit_audd_token = CreateWindowA("EDIT", "", WS_CHILD | ES_AUTOHSCROLL | ES_PASSWORD,
                                               28, 138, 440, 22, hwnd, reinterpret_cast<HMENU>(IDC_EDIT_AUDD_TOKEN), nullptr, nullptr);
        SendMessage(g_hwnd_edit_audd_token, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        // --- Symmetrical Segmented Pill Toggles ---
        g_hwnd_lbl_src = CreateWindowA("STATIC", "Audio Source:", WS_VISIBLE | WS_CHILD, 28, 74, 120, 16, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_lbl_src, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_bold), TRUE);

        g_hwnd_btn_src_speakers = CreateWindowA("BUTTON", "Speakers", WS_VISIBLE | WS_CHILD | BS_OWNERDRAW,
                                                28, 94, 104, 28, hwnd, reinterpret_cast<HMENU>(IDC_TOGGLE_SRC_SPEAKERS), nullptr, nullptr);
        SendMessage(g_hwnd_btn_src_speakers, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_bold), TRUE);

        g_hwnd_btn_src_mic = CreateWindowA("BUTTON", "Mic", WS_VISIBLE | WS_CHILD | BS_OWNERDRAW,
                                           134, 94, 104, 28, hwnd, reinterpret_cast<HMENU>(IDC_TOGGLE_SRC_MIC), nullptr, nullptr);
        SendMessage(g_hwnd_btn_src_mic, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_bold), TRUE);

        g_hwnd_lbl_dur = CreateWindowA("STATIC", "Scan Duration:", WS_VISIBLE | WS_CHILD, 258, 74, 120, 16, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_lbl_dur, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_bold), TRUE);

        g_hwnd_btn_dur_5s = CreateWindowA("BUTTON", "5 Seconds", WS_VISIBLE | WS_CHILD | BS_OWNERDRAW,
                                          258, 94, 104, 28, hwnd, reinterpret_cast<HMENU>(IDC_TOGGLE_DUR_5S), nullptr, nullptr);
        SendMessage(g_hwnd_btn_dur_5s, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_bold), TRUE);

        g_hwnd_btn_dur_10s = CreateWindowA("BUTTON", "10 Seconds", WS_VISIBLE | WS_CHILD | BS_OWNERDRAW,
                                           364, 94, 104, 28, hwnd, reinterpret_cast<HMENU>(IDC_TOGGLE_DUR_10S), nullptr, nullptr);
        SendMessage(g_hwnd_btn_dur_10s, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_bold), TRUE);

        // Identify Button
        g_hwnd_btn_identify = CreateWindowA("BUTTON", "Identify Music Now", WS_VISIBLE | WS_CHILD | BS_OWNERDRAW,
                                            28, 134, 440, 38, hwnd, reinterpret_cast<HMENU>(IDC_BTN_IDENTIFY), nullptr, nullptr);
        SendMessage(g_hwnd_btn_identify, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_bold), TRUE);

        // Status Label
        g_hwnd_status = CreateWindowA("STATIC", "Ready. Click Identify Music Now to scan.",
                                      WS_VISIBLE | WS_CHILD | SS_CENTER, 28, 180, 440, 18, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_status, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        // Result Card Elements
        g_hwnd_card_badge = CreateWindowA("STATIC", "", WS_VISIBLE | WS_CHILD | SS_RIGHT,
                                          350, 214, 104, 18, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_card_badge, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_small), TRUE);

        g_hwnd_song_title = CreateWindowA("STATIC", "No song identified yet", WS_VISIBLE | WS_CHILD | SS_LEFT,
                                          44, 214, 300, 24, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_song_title, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_song_title), TRUE);

        g_hwnd_song_artist = CreateWindowA("STATIC", "Your detected track and links will appear here", WS_VISIBLE | WS_CHILD,
                                           44, 240, 400, 18, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_song_artist, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        // Action Row Buttons
        g_hwnd_btn_browser = CreateWindowA("BUTTON", "Search Web", WS_VISIBLE | WS_CHILD | WS_DISABLED | BS_OWNERDRAW,
                                           44, 270, 115, 26, hwnd, reinterpret_cast<HMENU>(IDC_BTN_BROWSER), nullptr, nullptr);
        SendMessage(g_hwnd_btn_browser, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        g_hwnd_btn_youtube = CreateWindowA("BUTTON", "YouTube", WS_VISIBLE | WS_CHILD | WS_DISABLED | BS_OWNERDRAW,
                                           167, 270, 105, 26, hwnd, reinterpret_cast<HMENU>(IDC_BTN_YOUTUBE), nullptr, nullptr);
        SendMessage(g_hwnd_btn_youtube, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        g_hwnd_btn_copy = CreateWindowA("BUTTON", "Copy Title", WS_VISIBLE | WS_CHILD | WS_DISABLED | BS_OWNERDRAW,
                                        280, 270, 95, 26, hwnd, reinterpret_cast<HMENU>(IDC_BTN_COPY), nullptr, nullptr);
        SendMessage(g_hwnd_btn_copy, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        // Load configuration
        g_settings = load_settings();
        SendMessage(g_hwnd_provider, CB_SETCURSEL, g_settings.provider_index, 0);
        SetWindowTextA(g_hwnd_edit_acr_host, g_settings.acr_host.c_str());
        SetWindowTextA(g_hwnd_edit_acr_key, g_settings.acr_key.c_str());
        SetWindowTextA(g_hwnd_edit_acr_secret, g_settings.acr_secret.c_str());
        SetWindowTextA(g_hwnd_edit_audd_token, g_settings.audd_token.c_str());

        // Expand settings only if credentials are completely empty
        if (g_settings.provider_index == 0 && (g_settings.acr_key.empty() || g_settings.acr_secret.empty())) {
            g_settings_expanded = true;
        } else if (g_settings.provider_index == 1 && g_settings.audd_token.empty()) {
            g_settings_expanded = true;
        }

        apply_layout(hwnd);
        break;
    }

    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC hdc = BeginPaint(hwnd, &ps);

        int base_y = g_settings_expanded ? 245 : 74;
        int status_y = base_y + 106;
        int card_y = status_y + 24;

        // Draw Soft Result Card Container
        RECT rcCard = { 28, card_y, 468, card_y + 110 };
        HGDIOBJ oldBrush = SelectObject(hdc, g_card_brush);
        HGDIOBJ oldPen = SelectObject(hdc, g_border_pen);
        RoundRect(hdc, rcCard.left, rcCard.top, rcCard.right, rcCard.bottom, 10, 10);

        // If settings are expanded, draw subtle divider and input borders
        if (g_settings_expanded) {
            SelectObject(hdc, g_border_subtle_pen);
            MoveToEx(hdc, 28, 236, nullptr);
            LineTo(hdc, 468, 236);

            // Subtle borders around edit inputs
            SelectObject(hdc, GetStockObject(HOLLOW_BRUSH));
            SelectObject(hdc, g_border_pen);
            if (g_settings.provider_index == 0) {
                Rectangle(hdc, 27, 137, 469, 161);
                Rectangle(hdc, 27, 177, 469, 201);
                Rectangle(hdc, 27, 217, 469, 241);
            } else {
                Rectangle(hdc, 27, 137, 469, 161);
            }
        }

        // Live Scanning Progress Bar
        if (g_is_scanning) {
            int pbar_y = base_y + 98;
            RECT rcTrack = { 28, pbar_y, 468, pbar_y + 4 };
            HBRUSH trackBrush = CreateSolidBrush(RGB(32, 34, 42));
            FillRect(hdc, &rcTrack, trackBrush);
            DeleteObject(trackBrush);

            int fill_w = static_cast<int>(440.0f * std::clamp(g_scan_progress, 0.0f, 1.0f));
            RECT rcFill = { 28, pbar_y, 28 + fill_w, pbar_y + 4 };
            FillRect(hdc, &rcFill, g_accent_brush);
        }

        SelectObject(hdc, oldBrush);
        SelectObject(hdc, oldPen);
        EndPaint(hwnd, &ps);
        return 0;
    }

    case WM_TIMER: {
        if (wParam == TIMER_SCAN_PROGRESS && g_is_scanning) {
            auto elapsed = std::chrono::duration<float>(std::chrono::steady_clock::now() - g_scan_start_time).count();
            g_scan_progress = elapsed / static_cast<float>(g_scan_target_seconds);
            float remaining = std::max(0.0f, static_cast<float>(g_scan_target_seconds) - elapsed);

            char buf[64] = {0};
            sprintf_s(buf, sizeof(buf), "Listening... (%.1fs remaining)", remaining);
            SetWindowTextA(g_hwnd_status, buf);

            int base_y = g_settings_expanded ? 245 : 74;
            int pbar_y = base_y + 98;
            RECT rcBar = { 28, pbar_y, 468, pbar_y + 4 };
            InvalidateRect(hwnd, &rcBar, FALSE);

            if (g_scan_progress >= 1.0f) {
                SetWindowTextA(g_hwnd_status, "Analyzing audio fingerprint...");
            }
        }
        break;
    }

    case WM_DRAWITEM: {
        auto* pDraw = reinterpret_cast<DRAWITEMSTRUCT*>(lParam);
        if (!pDraw) break;

        // Erase any background behind the button to eliminate corner clipping artifacts
        FillRect(pDraw->hDC, &pDraw->rcItem, g_bg_brush);

        if (pDraw->CtlID == IDC_BTN_IDENTIFY) {
            bool disabled = (pDraw->itemState & ODS_DISABLED);
            bool selected = (pDraw->itemState & ODS_SELECTED);

            HBRUSH btnBrush = disabled ? CreateSolidBrush(RGB(32, 34, 42)) :
                              selected ? CreateSolidBrush(RGB(13, 148, 100)) :
                                         CreateSolidBrush(RGB(16, 185, 129));
            HPEN btnPen = CreatePen(PS_SOLID, 1, disabled ? RGB(42, 45, 53) : RGB(16, 185, 129));

            HGDIOBJ oldBrush = SelectObject(pDraw->hDC, btnBrush);
            HGDIOBJ oldPen = SelectObject(pDraw->hDC, btnPen);
            RoundRect(pDraw->hDC, pDraw->rcItem.left, pDraw->rcItem.top, pDraw->rcItem.right, pDraw->rcItem.bottom, 8, 8);

            SetBkMode(pDraw->hDC, TRANSPARENT);
            SetTextColor(pDraw->hDC, disabled ? RGB(110, 115, 125) : RGB(255, 255, 255));
            SelectObject(pDraw->hDC, g_font_bold);

            char text[64] = {0};
            GetWindowTextA(pDraw->hwndItem, text, sizeof(text));
            DrawTextA(pDraw->hDC, text, -1, &pDraw->rcItem, DT_CENTER | DT_VCENTER | DT_SINGLELINE);

            SelectObject(pDraw->hDC, oldBrush);
            SelectObject(pDraw->hDC, oldPen);
            DeleteObject(btnBrush);
            DeleteObject(btnPen);
            return TRUE;
        } else if (pDraw->CtlID >= IDC_TOGGLE_SRC_SPEAKERS && pDraw->CtlID <= IDC_TOGGLE_DUR_10S) {
            // Segmented pill toggles
            bool is_active = false;
            if (pDraw->CtlID == IDC_TOGGLE_SRC_SPEAKERS) is_active = (g_settings.audio_source == hearthis::AudioSource::Speakers);
            else if (pDraw->CtlID == IDC_TOGGLE_SRC_MIC) is_active = (g_settings.audio_source == hearthis::AudioSource::Microphone);
            else if (pDraw->CtlID == IDC_TOGGLE_DUR_5S) is_active = (g_settings.duration_seconds == 5);
            else if (pDraw->CtlID == IDC_TOGGLE_DUR_10S) is_active = (g_settings.duration_seconds == 10);

            HBRUSH btnBrush = is_active ? CreateSolidBrush(RGB(22, 54, 44)) : CreateSolidBrush(RGB(28, 30, 36));
            HPEN btnPen = CreatePen(PS_SOLID, 1, is_active ? RGB(16, 185, 129) : RGB(42, 45, 53));

            HGDIOBJ oldBrush = SelectObject(pDraw->hDC, btnBrush);
            HGDIOBJ oldPen = SelectObject(pDraw->hDC, btnPen);
            RoundRect(pDraw->hDC, pDraw->rcItem.left, pDraw->rcItem.top, pDraw->rcItem.right, pDraw->rcItem.bottom, 6, 6);

            SetBkMode(pDraw->hDC, TRANSPARENT);
            SetTextColor(pDraw->hDC, is_active ? RGB(52, 211, 153) : RGB(160, 165, 175));
            SelectObject(pDraw->hDC, g_font_bold);

            char text[64] = {0};
            GetWindowTextA(pDraw->hwndItem, text, sizeof(text));
            DrawTextA(pDraw->hDC, text, -1, &pDraw->rcItem, DT_CENTER | DT_VCENTER | DT_SINGLELINE);

            SelectObject(pDraw->hDC, oldBrush);
            SelectObject(pDraw->hDC, oldPen);
            DeleteObject(btnBrush);
            DeleteObject(btnPen);
            return TRUE;
        } else if (pDraw->CtlID == IDC_BTN_SETTINGS || pDraw->CtlID == IDC_BTN_GET_CREDS ||
                   pDraw->CtlID == IDC_BTN_BROWSER || pDraw->CtlID == IDC_BTN_YOUTUBE || pDraw->CtlID == IDC_BTN_COPY) {
            bool disabled = (pDraw->itemState & ODS_DISABLED);
            bool selected = (pDraw->itemState & ODS_SELECTED);

            // Card action buttons live inside the card, so clear with card brush
            if (pDraw->CtlID == IDC_BTN_BROWSER || pDraw->CtlID == IDC_BTN_YOUTUBE || pDraw->CtlID == IDC_BTN_COPY) {
                FillRect(pDraw->hDC, &pDraw->rcItem, g_card_brush);
            }

            HBRUSH btnBrush = disabled ? CreateSolidBrush(RGB(28, 30, 36)) :
                              selected ? CreateSolidBrush(RGB(48, 52, 64)) :
                                         CreateSolidBrush(RGB(34, 37, 46));
            HPEN btnPen = CreatePen(PS_SOLID, 1, disabled ? RGB(36, 38, 46) : RGB(48, 52, 64));

            HGDIOBJ oldBrush = SelectObject(pDraw->hDC, btnBrush);
            HGDIOBJ oldPen = SelectObject(pDraw->hDC, btnPen);
            RoundRect(pDraw->hDC, pDraw->rcItem.left, pDraw->rcItem.top, pDraw->rcItem.right, pDraw->rcItem.bottom, 6, 6);

            SetBkMode(pDraw->hDC, TRANSPARENT);
            SetTextColor(pDraw->hDC, disabled ? RGB(90, 95, 105) : RGB(225, 228, 236));
            SelectObject(pDraw->hDC, g_font_regular);

            char text[64] = {0};
            GetWindowTextA(pDraw->hwndItem, text, sizeof(text));
            DrawTextA(pDraw->hDC, text, -1, &pDraw->rcItem, DT_CENTER | DT_VCENTER | DT_SINGLELINE);

            SelectObject(pDraw->hDC, oldBrush);
            SelectObject(pDraw->hDC, oldPen);
            DeleteObject(btnBrush);
            DeleteObject(btnPen);
            return TRUE;
        }
        break;
    }

    case WM_CTLCOLOREDIT: {
        HDC hdc = reinterpret_cast<HDC>(wParam);
        SetTextColor(hdc, RGB(240, 243, 248));
        SetBkColor(hdc, RGB(28, 30, 36));
        return reinterpret_cast<LRESULT>(g_input_brush);
    }

    case WM_CTLCOLORLISTBOX: {
        HDC hdc = reinterpret_cast<HDC>(wParam);
        SetTextColor(hdc, RGB(240, 243, 248));
        SetBkColor(hdc, RGB(28, 30, 36));
        return reinterpret_cast<LRESULT>(g_input_brush);
    }

    case WM_CTLCOLORSTATIC: {
        HDC hdc = reinterpret_cast<HDC>(wParam);
        HWND hCtrl = reinterpret_cast<HWND>(lParam);

        if (hCtrl == g_hwnd_song_title) {
            SetTextColor(hdc, RGB(255, 255, 255));
            SetBkColor(hdc, RGB(26, 28, 34));
            return reinterpret_cast<LRESULT>(g_card_brush);
        } else if (hCtrl == g_hwnd_song_artist) {
            SetTextColor(hdc, RGB(156, 163, 175));
            SetBkColor(hdc, RGB(26, 28, 34));
            return reinterpret_cast<LRESULT>(g_card_brush);
        } else if (hCtrl == g_hwnd_card_badge) {
            SetTextColor(hdc, RGB(52, 211, 153));
            SetBkColor(hdc, RGB(26, 28, 34));
            return reinterpret_cast<LRESULT>(g_card_brush);
        } else if (hCtrl == g_hwnd_status) {
            SetTextColor(hdc, g_status_color);
            SetBkColor(hdc, RGB(20, 21, 25));
            return reinterpret_cast<LRESULT>(g_bg_brush);
        } else if (hCtrl == g_hwnd_subtitle) {
            SetTextColor(hdc, RGB(140, 145, 155));
            SetBkColor(hdc, RGB(20, 21, 25));
            return reinterpret_cast<LRESULT>(g_bg_brush);
        }

        SetTextColor(hdc, RGB(215, 220, 230));
        SetBkColor(hdc, RGB(20, 21, 25));
        return reinterpret_cast<LRESULT>(g_bg_brush);
    }

    case WM_COMMAND: {
        int wmId = LOWORD(wParam);
        int wmEvent = HIWORD(wParam);

        if (wmId == IDC_BTN_SETTINGS) {
            g_settings_expanded = !g_settings_expanded;
            SetWindowTextA(g_hwnd_btn_settings, g_settings_expanded ? "Hide Settings" : "API Settings");
            apply_layout(hwnd);
        } else if (wmId == IDC_COMBO_PROVIDER && wmEvent == CBN_SELCHANGE) {
            int idx = static_cast<int>(SendMessage(g_hwnd_provider, CB_GETCURSEL, 0, 0));
            g_settings.provider_index = idx;
            update_provider_visibility(idx);
        } else if (wmId == IDC_TOGGLE_SRC_SPEAKERS) {
            g_settings.audio_source = hearthis::AudioSource::Speakers;
            InvalidateRect(g_hwnd_btn_src_speakers, nullptr, TRUE);
            InvalidateRect(g_hwnd_btn_src_mic, nullptr, TRUE);
        } else if (wmId == IDC_TOGGLE_SRC_MIC) {
            g_settings.audio_source = hearthis::AudioSource::Microphone;
            InvalidateRect(g_hwnd_btn_src_speakers, nullptr, TRUE);
            InvalidateRect(g_hwnd_btn_src_mic, nullptr, TRUE);
        } else if (wmId == IDC_TOGGLE_DUR_5S) {
            g_settings.duration_seconds = 5;
            InvalidateRect(g_hwnd_btn_dur_5s, nullptr, TRUE);
            InvalidateRect(g_hwnd_btn_dur_10s, nullptr, TRUE);
        } else if (wmId == IDC_TOGGLE_DUR_10S) {
            g_settings.duration_seconds = 10;
            InvalidateRect(g_hwnd_btn_dur_5s, nullptr, TRUE);
            InvalidateRect(g_hwnd_btn_dur_10s, nullptr, TRUE);
        } else if (wmId == IDC_BTN_GET_CREDS) {
            int idx = static_cast<int>(SendMessage(g_hwnd_provider, CB_GETCURSEL, 0, 0));
            if (idx == 0) {
                ShellExecuteA(hwnd, "open", "https://console.acrcloud.com", nullptr, nullptr, SW_SHOWNORMAL);
            } else {
                ShellExecuteA(hwnd, "open", "https://audd.io", nullptr, nullptr, SW_SHOWNORMAL);
            }
        } else if (wmId == IDC_BTN_BROWSER) {
            if (!g_current_track_string.empty()) {
                std::string url = "https://www.google.com/search?q=";
                for (char c : g_current_track_string) {
                    if (c == ' ') url += '+';
                    else if (isalnum(c)) url += c;
                }
                ShellExecuteA(hwnd, "open", url.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
            }
        } else if (wmId == IDC_BTN_YOUTUBE) {
            if (!g_current_youtube_url.empty()) {
                ShellExecuteA(hwnd, "open", g_current_youtube_url.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
            } else if (!g_current_track_string.empty()) {
                std::string url = "https://www.youtube.com/results?search_query=";
                for (char c : g_current_track_string) {
                    if (c == ' ') url += '+';
                    else if (isalnum(c)) url += c;
                }
                ShellExecuteA(hwnd, "open", url.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
            }
        } else if (wmId == IDC_BTN_COPY) {
            if (!g_current_track_string.empty()) {
                copy_to_clipboard(hwnd, g_current_track_string);
                SetWindowTextA(g_hwnd_btn_copy, "Copied!");
                InvalidateRect(g_hwnd_btn_copy, nullptr, TRUE);
            }
        } else if (wmId == IDC_BTN_IDENTIFY) {
            g_settings.provider_index = static_cast<int>(SendMessage(g_hwnd_provider, CB_GETCURSEL, 0, 0));

            char buf[512] = {0};
            GetWindowTextA(g_hwnd_edit_acr_host, buf, sizeof(buf)); g_settings.acr_host = buf;
            GetWindowTextA(g_hwnd_edit_acr_key, buf, sizeof(buf)); g_settings.acr_key = buf;
            GetWindowTextA(g_hwnd_edit_acr_secret, buf, sizeof(buf)); g_settings.acr_secret = buf;
            GetWindowTextA(g_hwnd_edit_audd_token, buf, sizeof(buf)); g_settings.audd_token = buf;

            save_settings(g_settings);

            // Validation
            if (g_settings.provider_index == 0) {
                if (g_settings.acr_host.empty() || g_settings.acr_key.empty() || g_settings.acr_secret.empty()) {
                    g_status_color = RGB(248, 113, 113);
                    SetWindowTextA(g_hwnd_status, "Please fill in ACRCloud Host, Key, and Secret.");
                    InvalidateRect(g_hwnd_status, nullptr, TRUE);
                    if (!g_settings_expanded) {
                        g_settings_expanded = true;
                        SetWindowTextA(g_hwnd_btn_settings, "Hide Settings");
                        apply_layout(hwnd);
                    }
                    return 0;
                }
            } else {
                if (g_settings.audd_token.empty()) {
                    g_status_color = RGB(248, 113, 113);
                    SetWindowTextA(g_hwnd_status, "Please enter your AudD API Token.");
                    InvalidateRect(g_hwnd_status, nullptr, TRUE);
                    if (!g_settings_expanded) {
                        g_settings_expanded = true;
                        SetWindowTextA(g_hwnd_btn_settings, "Hide Settings");
                        apply_layout(hwnd);
                    }
                    return 0;
                }
            }

            EnableWindow(g_hwnd_btn_identify, FALSE);
            EnableWindow(g_hwnd_btn_browser, FALSE);
            EnableWindow(g_hwnd_btn_youtube, FALSE);
            EnableWindow(g_hwnd_btn_copy, FALSE);
            SetWindowTextA(g_hwnd_btn_copy, "Copy Title");

            InvalidateRect(g_hwnd_btn_identify, nullptr, TRUE);
            InvalidateRect(g_hwnd_btn_browser, nullptr, TRUE);
            InvalidateRect(g_hwnd_btn_youtube, nullptr, TRUE);
            InvalidateRect(g_hwnd_btn_copy, nullptr, TRUE);

            g_cancel_scan = false;
            g_is_scanning = true;
            g_scan_progress = 0.0f;
            g_scan_target_seconds = g_settings.duration_seconds;
            g_scan_start_time = std::chrono::steady_clock::now();
            SetTimer(hwnd, TIMER_SCAN_PROGRESS, 50, nullptr);

            g_status_color = RGB(56, 189, 248);
            SetWindowTextA(g_hwnd_status, "Listening to audio...");
            InvalidateRect(g_hwnd_status, nullptr, TRUE);

            SetWindowTextA(g_hwnd_song_title, "Listening...");
            SetWindowTextA(g_hwnd_song_artist, "Sampling acoustic fingerprint");
            SetWindowTextA(g_hwnd_card_badge, "");

            std::thread(run_recognition_worker, hwnd, g_settings).detach();
        }
        break;
    }

    case WM_RECOGNITION_DONE: {
        KillTimer(hwnd, TIMER_SCAN_PROGRESS);
        g_is_scanning = false;
        g_scan_progress = 0.0f;

        // Force repaint of progress bar area
        int base_y = g_settings_expanded ? 245 : 74;
        int pbar_y = base_y + 98;
        RECT rcBar = { 28, pbar_y, 468, pbar_y + 4 };
        InvalidateRect(hwnd, &rcBar, TRUE);

        auto* result = reinterpret_cast<hearthis::RecognitionResult*>(lParam);
        EnableWindow(g_hwnd_btn_identify, TRUE);
        InvalidateRect(g_hwnd_btn_identify, nullptr, TRUE);

        if (!result->error_message.empty()) {
            g_status_color = RGB(248, 113, 113);
            std::string err = "Notice: " + result->error_message;
            SetWindowTextA(g_hwnd_status, err.c_str());
            SetWindowTextA(g_hwnd_song_title, "Scan Incomplete");
            SetWindowTextA(g_hwnd_song_artist, result->error_message.c_str());
            SetWindowTextA(g_hwnd_card_badge, "");
        } else if (result->matched) {
            g_status_color = RGB(52, 211, 153);
            SetWindowTextA(g_hwnd_status, "Track successfully identified!");

            SetWindowTextA(g_hwnd_song_title, result->title.c_str());
            SetWindowTextA(g_hwnd_song_artist, result->artist.c_str());

            std::string badge_text = result->provider;
            SetWindowTextA(g_hwnd_card_badge, badge_text.c_str());

            g_current_youtube_url = result->youtube_url;
            g_current_track_string = result->title + " - " + result->artist;

            EnableWindow(g_hwnd_btn_browser, TRUE);
            EnableWindow(g_hwnd_btn_youtube, TRUE);
            EnableWindow(g_hwnd_btn_copy, TRUE);

            InvalidateRect(g_hwnd_btn_browser, nullptr, TRUE);
            InvalidateRect(g_hwnd_btn_youtube, nullptr, TRUE);
            InvalidateRect(g_hwnd_btn_copy, nullptr, TRUE);
        } else {
            g_status_color = RGB(251, 146, 60);
            SetWindowTextA(g_hwnd_status, "No match found. Try again during a clear music section.");
            SetWindowTextA(g_hwnd_song_title, "No Match Found");
            SetWindowTextA(g_hwnd_song_artist, "Could not match audio against catalog.");
            SetWindowTextA(g_hwnd_card_badge, "");
        }
        InvalidateRect(g_hwnd_status, nullptr, TRUE);

        delete result;
        break;
    }

    case WM_DESTROY: {
        g_cancel_scan = true;
        KillTimer(hwnd, TIMER_SCAN_PROGRESS);
        if (g_bg_brush) DeleteObject(g_bg_brush);
        if (g_input_brush) DeleteObject(g_input_brush);
        if (g_card_brush) DeleteObject(g_card_brush);
        if (g_accent_brush) DeleteObject(g_accent_brush);
        if (g_border_pen) DeleteObject(g_border_pen);
        if (g_border_subtle_pen) DeleteObject(g_border_subtle_pen);
        if (g_font_title) DeleteObject(g_font_title);
        if (g_font_song_title) DeleteObject(g_font_song_title);
        if (g_font_bold) DeleteObject(g_font_bold);
        if (g_font_regular) DeleteObject(g_font_regular);
        if (g_font_small) DeleteObject(g_font_small);
        PostQuitMessage(0);
        break;
    }

    default:
        return DefWindowProcA(hwnd, msg, wParam, lParam);
    }
    return 0;
}

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE, LPSTR, int nCmdShow) {
    HICON hIcon = LoadIconA(hInstance, MAKEINTRESOURCEA(1));
    if (!hIcon) {
        hIcon = reinterpret_cast<HICON>(LoadImageA(nullptr, "assets\\icon.ico", IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE));
    }
    if (!hIcon) {
        char exePath[MAX_PATH] = {0};
        GetModuleFileNameA(nullptr, exePath, MAX_PATH);
        char* lastSlash = strrchr(exePath, '\\');
        if (lastSlash) {
            strcpy_s(lastSlash + 1, MAX_PATH - (lastSlash - exePath + 1), "icon.ico");
            hIcon = reinterpret_cast<HICON>(LoadImageA(nullptr, exePath, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE));
        }
    }

    WNDCLASSEXA wc = {0};
    wc.cbSize = sizeof(WNDCLASSEXA);
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInstance;
    wc.lpszClassName = "HearThisNativeWindow";
    wc.hbrBackground = CreateSolidBrush(RGB(20, 21, 25));
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    wc.hIcon = hIcon;
    wc.hIconSm = hIcon;

    if (!RegisterClassExA(&wc)) {
        return 1;
    }

    int width = 512;
    int height = 425; // Compact height by default

    int screen_w = GetSystemMetrics(SM_CXSCREEN);
    int screen_h = GetSystemMetrics(SM_CYSCREEN);
    int pos_x = (screen_w - width) / 2;
    int pos_y = (screen_h - height) / 2;

    HWND hwnd = CreateWindowExA(
        0,
        "HearThisNativeWindow",
        "HearThis",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
        pos_x, pos_y, width, height,
        nullptr, nullptr, hInstance, nullptr
    );

    if (!hwnd) {
        return 1;
    }

    if (hIcon) {
        SendMessage(hwnd, WM_SETICON, ICON_BIG, reinterpret_cast<LPARAM>(hIcon));
        SendMessage(hwnd, WM_SETICON, ICON_SMALL, reinterpret_cast<LPARAM>(hIcon));
    }

    BOOL dark_mode = TRUE;
    DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, &dark_mode, sizeof(dark_mode));

    ShowWindow(hwnd, nCmdShow);
    UpdateWindow(hwnd);

    MSG msg;
    while (GetMessageA(&msg, nullptr, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessageA(&msg);
    }

    return static_cast<int>(msg.wParam);
}
