#include "hearthis/audio_processor.h"
#include "hearthis/wasapi_capture.h"
#include "hearthis/api_client.h"

#include <windows.h>
#include <commctrl.h>
#include <dwmapi.h>
#include <shellapi.h>
#include <string>
#include <vector>
#include <thread>
#include <fstream>
#include <sstream>

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
#define IDC_COMBO_PROVIDER     101
#define IDC_BTN_IDENTIFY       102
#define IDC_BTN_BROWSER        103
#define IDC_BTN_GET_CREDS      104
#define IDC_COMBO_DURATION     105

#define IDC_EDIT_ACR_HOST      201
#define IDC_EDIT_ACR_KEY       202
#define IDC_EDIT_ACR_SECRET    203
#define IDC_EDIT_AUDD_TOKEN    204

// Custom Windows message sent when recognition finishes
#define WM_RECOGNITION_DONE    (WM_USER + 1)

// Global UI Handles
HWND g_hwnd_provider = nullptr;
HWND g_hwnd_duration = nullptr;
HWND g_hwnd_btn_identify = nullptr;
HWND g_hwnd_btn_browser = nullptr;
HWND g_hwnd_btn_get_creds = nullptr;
HWND g_hwnd_status = nullptr;
HWND g_hwnd_song_title = nullptr;
HWND g_hwnd_song_artist = nullptr;
HWND g_hwnd_card_header = nullptr;
HWND g_hwnd_subtitle = nullptr;

// ACRCloud Control Handles
HWND g_hwnd_lbl_acr_host = nullptr;
HWND g_hwnd_edit_acr_host = nullptr;
HWND g_hwnd_lbl_acr_key = nullptr;
HWND g_hwnd_edit_acr_key = nullptr;
HWND g_hwnd_lbl_acr_secret = nullptr;
HWND g_hwnd_edit_acr_secret = nullptr;

// AudD Control Handles
HWND g_hwnd_lbl_audd_token = nullptr;
HWND g_hwnd_edit_audd_token = nullptr;

HFONT g_font_regular = nullptr;
HFONT g_font_title = nullptr;
HFONT g_font_bold = nullptr;

HBRUSH g_bg_brush = nullptr;
HBRUSH g_input_brush = nullptr;
HBRUSH g_card_brush = nullptr;
HPEN g_border_pen = nullptr;
COLORREF g_status_color = RGB(156, 163, 175);

std::string g_current_youtube_url = "";

// Configuration path in %APPDATA%/SongDetector/native_config.txt
std::string get_config_file_path() {
    char* appdata = nullptr;
    size_t len = 0;
    if (_dupenv_s(&appdata, &len, "APPDATA") == 0 && appdata) {
        std::string dir = std::string(appdata) + "\\SongDetector";
        CreateDirectoryA(dir.c_str(), nullptr);
        std::string path = dir + "\\native_config.txt";
        free(appdata);
        return path;
    }
    return "native_config.txt";
}

struct AppSettings {
    int provider_index = 0; // 0 = ACRCloud (Default), 1 = AudD
    int duration_seconds = 10; // Default: 10 Seconds (Recommended)
    std::string acr_host = "identify-eu-west-1.acrcloud.com";
    std::string acr_key = "";
    std::string acr_secret = "";
    std::string audd_token = "";
};

AppSettings load_settings() {
    AppSettings s;
    std::ifstream file(get_config_file_path());
    if (file.is_open()) {
        std::string line;
        while (std::getline(file, line)) {
            size_t eq = line.find('=');
            if (eq != std::string::npos) {
                std::string k = line.substr(0, eq);
                std::string v = line.substr(eq + 1);
                if (k == "provider") s.provider_index = std::stoi(v);
                else if (k == "duration") s.duration_seconds = std::stoi(v);
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
    std::ofstream file(get_config_file_path());
    if (file.is_open()) {
        file << "provider=" << s.provider_index << "\n";
        file << "duration=" << s.duration_seconds << "\n";
        file << "acr_host=" << s.acr_host << "\n";
        file << "acr_key=" << s.acr_key << "\n";
        file << "acr_secret=" << s.acr_secret << "\n";
        file << "audd_token=" << s.audd_token << "\n";
        file.close();
    }
}

void update_provider_visibility(int provider_index) {
    bool is_acr = (provider_index == 0);

    // Show/hide ACRCloud controls
    int show_acr = is_acr ? SW_SHOW : SW_HIDE;
    ShowWindow(g_hwnd_lbl_acr_host, show_acr);
    ShowWindow(g_hwnd_edit_acr_host, show_acr);
    ShowWindow(g_hwnd_lbl_acr_key, show_acr);
    ShowWindow(g_hwnd_edit_acr_key, show_acr);
    ShowWindow(g_hwnd_lbl_acr_secret, show_acr);
    ShowWindow(g_hwnd_edit_acr_secret, show_acr);

    // Show/hide AudD controls
    int show_audd = is_acr ? SW_HIDE : SW_SHOW;
    ShowWindow(g_hwnd_lbl_audd_token, show_audd);
    ShowWindow(g_hwnd_edit_audd_token, show_audd);

    // Update portal button label
    if (is_acr) {
        SetWindowTextA(g_hwnd_btn_get_creds, "Get ACRCloud Keys");
    } else {
        SetWindowTextA(g_hwnd_btn_get_creds, "Get AudD Token");
    }
}

// Background recognition thread
void run_recognition_worker(HWND hwnd, AppSettings settings) {
    hearthis::WasapiCapture capture;
    double duration = static_cast<double>(settings.duration_seconds);
    hearthis::CapturedAudio audio = capture.capture_loopback(duration);

    if (!audio.success) {
        auto* res = new hearthis::RecognitionResult();
        res->error_message = audio.error_message;
        PostMessage(hwnd, WM_RECOGNITION_DONE, 0, reinterpret_cast<LPARAM>(res));
        return;
    }

    std::vector<float> mono = hearthis::stereo_to_mono(audio.samples);

    if (hearthis::is_silent(mono, -50.0f)) {
        auto* res = new hearthis::RecognitionResult();
        res->error_message = "Silence detected. Audio was below -50 dBFS.";
        PostMessage(hwnd, WM_RECOGNITION_DONE, 0, reinterpret_cast<LPARAM>(res));
        return;
    }

    std::vector<uint8_t> wav = hearthis::pcm_to_wav_bytes(mono, audio.sample_rate);
    hearthis::ApiClient client;
    hearthis::RecognitionResult result;

    if (settings.provider_index == 0) {
        // Priority 1: ACRCloud
        hearthis::AcrCredentials creds;
        creds.host = settings.acr_host;
        creds.access_key = settings.acr_key;
        creds.access_secret = settings.acr_secret;
        result = client.recognize_acrcloud(wav, creds);
    } else {
        // Choice 2: AudD
        result = client.recognize_audd(wav, settings.audd_token);
    }

    auto* res = new hearthis::RecognitionResult(result);
    PostMessage(hwnd, WM_RECOGNITION_DONE, 0, reinterpret_cast<LPARAM>(res));
}

// Main Window Procedure
LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
    case WM_CREATE: {
        g_bg_brush = CreateSolidBrush(RGB(20, 21, 25));
        g_input_brush = CreateSolidBrush(RGB(32, 34, 42));
        g_card_brush = CreateSolidBrush(RGB(28, 30, 36));
        g_border_pen = CreatePen(PS_SOLID, 1, RGB(48, 52, 64));

        g_font_title = CreateFontA(22, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE, ANSI_CHARSET, OUT_DEFAULT_PRECIS,
                                  CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, "Segoe UI");
        g_font_bold = CreateFontA(14, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE, ANSI_CHARSET, OUT_DEFAULT_PRECIS,
                                 CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, "Segoe UI");
        g_font_regular = CreateFontA(13, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, ANSI_CHARSET, OUT_DEFAULT_PRECIS,
                                    CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, "Segoe UI");

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
                                        70, 14, 200, 24, hwnd, nullptr, nullptr, nullptr);
            SendMessage(hTitle, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_title), TRUE);

            g_hwnd_subtitle = CreateWindowA("STATIC", "Identify songs playing through your speakers.", WS_VISIBLE | WS_CHILD,
                                            70, 40, 400, 16, hwnd, nullptr, nullptr, nullptr);
            SendMessage(g_hwnd_subtitle, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);
        } else {
            HWND hTitle = CreateWindowA("STATIC", "HearThis", WS_VISIBLE | WS_CHILD, 28, 16, 200, 24, hwnd, nullptr, nullptr, nullptr);
            SendMessage(hTitle, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_title), TRUE);

            g_hwnd_subtitle = CreateWindowA("STATIC", "Identify songs playing through your speakers.", WS_VISIBLE | WS_CHILD,
                                            28, 40, 440, 16, hwnd, nullptr, nullptr, nullptr);
            SendMessage(g_hwnd_subtitle, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);
        }

        // Provider Selector Row
        HWND hLblProv = CreateWindowA("STATIC", "Music Provider:", WS_VISIBLE | WS_CHILD, 28, 72, 120, 16, hwnd, nullptr, nullptr, nullptr);
        SendMessage(hLblProv, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_bold), TRUE);

        g_hwnd_provider = CreateWindowA("COMBOBOX", "", WS_VISIBLE | WS_CHILD | CBS_DROPDOWNLIST | WS_VSCROLL,
                                       28, 92, 280, 120, hwnd, reinterpret_cast<HMENU>(IDC_COMBO_PROVIDER), nullptr, nullptr);
        SendMessage(g_hwnd_provider, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);
        SendMessage(g_hwnd_provider, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>("ACRCloud (Default Provider)"));
        SendMessage(g_hwnd_provider, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>("AudD (Secondary Choice)"));

        // Helper Portal Link Button
        g_hwnd_btn_get_creds = CreateWindowA("BUTTON", "Get ACRCloud Keys", WS_VISIBLE | WS_CHILD | BS_OWNERDRAW,
                                             320, 91, 148, 26, hwnd, reinterpret_cast<HMENU>(IDC_BTN_GET_CREDS), nullptr, nullptr);
        SendMessage(g_hwnd_btn_get_creds, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        // --- ACRCloud Inputs (3 Keys) ---
        g_hwnd_lbl_acr_host = CreateWindowA("STATIC", "ACRCloud Host:", WS_VISIBLE | WS_CHILD, 28, 128, 140, 16, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_lbl_acr_host, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        g_hwnd_edit_acr_host = CreateWindowExA(WS_EX_CLIENTEDGE, "EDIT", "", WS_VISIBLE | WS_CHILD | ES_AUTOHSCROLL,
                                               28, 146, 440, 24, hwnd, reinterpret_cast<HMENU>(IDC_EDIT_ACR_HOST), nullptr, nullptr);
        SendMessage(g_hwnd_edit_acr_host, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        g_hwnd_lbl_acr_key = CreateWindowA("STATIC", "ACRCloud Access Key:", WS_VISIBLE | WS_CHILD, 28, 178, 160, 16, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_lbl_acr_key, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        g_hwnd_edit_acr_key = CreateWindowExA(WS_EX_CLIENTEDGE, "EDIT", "", WS_VISIBLE | WS_CHILD | ES_AUTOHSCROLL,
                                              28, 196, 440, 24, hwnd, reinterpret_cast<HMENU>(IDC_EDIT_ACR_KEY), nullptr, nullptr);
        SendMessage(g_hwnd_edit_acr_key, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        g_hwnd_lbl_acr_secret = CreateWindowA("STATIC", "ACRCloud Access Secret:", WS_VISIBLE | WS_CHILD, 28, 228, 180, 16, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_lbl_acr_secret, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        g_hwnd_edit_acr_secret = CreateWindowExA(WS_EX_CLIENTEDGE, "EDIT", "", WS_VISIBLE | WS_CHILD | ES_AUTOHSCROLL | ES_PASSWORD,
                                                 28, 246, 440, 24, hwnd, reinterpret_cast<HMENU>(IDC_EDIT_ACR_SECRET), nullptr, nullptr);
        SendMessage(g_hwnd_edit_acr_secret, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        // --- AudD Input (Single Token) ---
        g_hwnd_lbl_audd_token = CreateWindowA("STATIC", "AudD API Token:", WS_CHILD, 28, 128, 140, 16, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_lbl_audd_token, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        g_hwnd_edit_audd_token = CreateWindowExA(WS_EX_CLIENTEDGE, "EDIT", "", WS_CHILD | ES_AUTOHSCROLL | ES_PASSWORD,
                                                 28, 146, 440, 24, hwnd, reinterpret_cast<HMENU>(IDC_EDIT_AUDD_TOKEN), nullptr, nullptr);
        SendMessage(g_hwnd_edit_audd_token, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        // Load saved settings
        AppSettings saved = load_settings();
        SendMessage(g_hwnd_provider, CB_SETCURSEL, saved.provider_index, 0);
        SetWindowTextA(g_hwnd_edit_acr_host, saved.acr_host.c_str());
        SetWindowTextA(g_hwnd_edit_acr_key, saved.acr_key.c_str());
        SetWindowTextA(g_hwnd_edit_acr_secret, saved.acr_secret.c_str());
        SetWindowTextA(g_hwnd_edit_audd_token, saved.audd_token.c_str());
        update_provider_visibility(saved.provider_index);

        // Duration Selector Row
        HWND hLblDur = CreateWindowA("STATIC", "Scan Duration:", WS_VISIBLE | WS_CHILD, 28, 280, 120, 16, hwnd, nullptr, nullptr, nullptr);
        SendMessage(hLblDur, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_bold), TRUE);

        g_hwnd_duration = CreateWindowA("COMBOBOX", "", WS_VISIBLE | WS_CHILD | CBS_DROPDOWNLIST | WS_VSCROLL,
                                        28, 300, 440, 100, hwnd, reinterpret_cast<HMENU>(IDC_COMBO_DURATION), nullptr, nullptr);
        SendMessage(g_hwnd_duration, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);
        SendMessage(g_hwnd_duration, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>("10 Seconds (Recommended - Best Match)"));
        SendMessage(g_hwnd_duration, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>("5 Seconds (Fast Scan)"));

        int dur_idx = (saved.duration_seconds == 5) ? 1 : 0;
        SendMessage(g_hwnd_duration, CB_SETCURSEL, dur_idx, 0);

        // Identify Button
        g_hwnd_btn_identify = CreateWindowA("BUTTON", "Identify Music Now", WS_VISIBLE | WS_CHILD | BS_OWNERDRAW,
                                            28, 340, 440, 36, hwnd, reinterpret_cast<HMENU>(IDC_BTN_IDENTIFY), nullptr, nullptr);
        SendMessage(g_hwnd_btn_identify, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_bold), TRUE);

        // Status Label
        g_hwnd_status = CreateWindowA("STATIC", "Ready. Click Identify Music Now to scan audio.",
                                      WS_VISIBLE | WS_CHILD | SS_CENTER, 28, 384, 440, 18, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_status, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        // Result Card Elements (Painted on top of card background)
        g_hwnd_card_header = CreateWindowA("STATIC", "Identified Track", WS_VISIBLE | WS_CHILD,
                                           44, 422, 200, 16, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_card_header, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_bold), TRUE);

        g_hwnd_song_title = CreateWindowA("STATIC", "Title:  -", WS_VISIBLE | WS_CHILD,
                                          44, 444, 400, 16, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_song_title, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_bold), TRUE);

        g_hwnd_song_artist = CreateWindowA("STATIC", "Artist: -", WS_VISIBLE | WS_CHILD,
                                           44, 466, 400, 16, hwnd, nullptr, nullptr, nullptr);
        SendMessage(g_hwnd_song_artist, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        g_hwnd_btn_browser = CreateWindowA("BUTTON", "Search on Web", WS_VISIBLE | WS_CHILD | WS_DISABLED | BS_OWNERDRAW,
                                           44, 490, 128, 24, hwnd, reinterpret_cast<HMENU>(IDC_BTN_BROWSER), nullptr, nullptr);
        SendMessage(g_hwnd_btn_browser, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_regular), TRUE);

        break;
    }

    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC hdc = BeginPaint(hwnd, &ps);

        // Soft result card container
        RECT rcCard = { 28, 410, 468, 526 };
        HGDIOBJ oldBrush = SelectObject(hdc, g_card_brush);
        HGDIOBJ oldPen = SelectObject(hdc, g_border_pen);
        RoundRect(hdc, rcCard.left, rcCard.top, rcCard.right, rcCard.bottom, 8, 8);
        SelectObject(hdc, oldBrush);
        SelectObject(hdc, oldPen);

        EndPaint(hwnd, &ps);
        return 0;
    }

    case WM_DRAWITEM: {
        auto* pDraw = reinterpret_cast<DRAWITEMSTRUCT*>(lParam);
        if (!pDraw) break;

        if (pDraw->CtlID == IDC_BTN_IDENTIFY) {
            bool disabled = (pDraw->itemState & ODS_DISABLED);
            bool selected = (pDraw->itemState & ODS_SELECTED);

            HBRUSH btnBrush = disabled ? CreateSolidBrush(RGB(38, 40, 48)) :
                              selected ? CreateSolidBrush(RGB(13, 148, 100)) :
                                         CreateSolidBrush(RGB(16, 185, 129));
            HPEN btnPen = CreatePen(PS_SOLID, 1, disabled ? RGB(48, 50, 60) : RGB(16, 185, 129));

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
        } else if (pDraw->CtlID == IDC_BTN_GET_CREDS || pDraw->CtlID == IDC_BTN_BROWSER) {
            bool disabled = (pDraw->itemState & ODS_DISABLED);
            bool selected = (pDraw->itemState & ODS_SELECTED);

            HBRUSH btnBrush = disabled ? CreateSolidBrush(RGB(28, 30, 36)) :
                              selected ? CreateSolidBrush(RGB(48, 52, 64)) :
                                         CreateSolidBrush(RGB(36, 38, 48));
            HPEN btnPen = CreatePen(PS_SOLID, 1, disabled ? RGB(36, 38, 46) : RGB(56, 60, 74));

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
        SetBkColor(hdc, RGB(32, 34, 42));
        return reinterpret_cast<LRESULT>(g_input_brush);
    }

    case WM_CTLCOLORLISTBOX: {
        HDC hdc = reinterpret_cast<HDC>(wParam);
        SetTextColor(hdc, RGB(240, 243, 248));
        SetBkColor(hdc, RGB(32, 34, 42));
        return reinterpret_cast<LRESULT>(g_input_brush);
    }

    case WM_CTLCOLORSTATIC: {
        HDC hdc = reinterpret_cast<HDC>(wParam);
        HWND hCtrl = reinterpret_cast<HWND>(lParam);

        if (hCtrl == g_hwnd_song_title) {
            SetTextColor(hdc, RGB(255, 255, 255));
            SetBkColor(hdc, RGB(28, 30, 36));
            return reinterpret_cast<LRESULT>(g_card_brush);
        } else if (hCtrl == g_hwnd_song_artist) {
            SetTextColor(hdc, RGB(180, 185, 195));
            SetBkColor(hdc, RGB(28, 30, 36));
            return reinterpret_cast<LRESULT>(g_card_brush);
        } else if (hCtrl == g_hwnd_card_header) {
            SetTextColor(hdc, RGB(16, 185, 129));
            SetBkColor(hdc, RGB(28, 30, 36));
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

        if (wmId == IDC_COMBO_PROVIDER && wmEvent == CBN_SELCHANGE) {
            int idx = static_cast<int>(SendMessage(g_hwnd_provider, CB_GETCURSEL, 0, 0));
            update_provider_visibility(idx);
        } else if (wmId == IDC_BTN_GET_CREDS) {
            int idx = static_cast<int>(SendMessage(g_hwnd_provider, CB_GETCURSEL, 0, 0));
            if (idx == 0) {
                ShellExecuteA(hwnd, "open", "https://console.acrcloud.com", nullptr, nullptr, SW_SHOWNORMAL);
            } else {
                ShellExecuteA(hwnd, "open", "https://audd.io", nullptr, nullptr, SW_SHOWNORMAL);
            }
        } else if (wmId == IDC_BTN_BROWSER) {
            if (!g_current_youtube_url.empty()) {
                ShellExecuteA(hwnd, "open", g_current_youtube_url.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
            }
        } else if (wmId == IDC_BTN_IDENTIFY) {
            AppSettings settings;
            settings.provider_index = static_cast<int>(SendMessage(g_hwnd_provider, CB_GETCURSEL, 0, 0));

            int dur_sel = static_cast<int>(SendMessage(g_hwnd_duration, CB_GETCURSEL, 0, 0));
            settings.duration_seconds = (dur_sel == 1) ? 5 : 10;

            char buf[512] = {0};
            GetWindowTextA(g_hwnd_edit_acr_host, buf, sizeof(buf)); settings.acr_host = buf;
            GetWindowTextA(g_hwnd_edit_acr_key, buf, sizeof(buf)); settings.acr_key = buf;
            GetWindowTextA(g_hwnd_edit_acr_secret, buf, sizeof(buf)); settings.acr_secret = buf;
            GetWindowTextA(g_hwnd_edit_audd_token, buf, sizeof(buf)); settings.audd_token = buf;

            save_settings(settings);

            // Validation
            if (settings.provider_index == 0) {
                if (settings.acr_host.empty() || settings.acr_key.empty() || settings.acr_secret.empty()) {
                    g_status_color = RGB(248, 113, 113);
                    SetWindowTextA(g_hwnd_status, "Please fill in ACRCloud Host, Key, and Secret.");
                    InvalidateRect(g_hwnd_status, nullptr, TRUE);
                    return 0;
                }
            } else {
                if (settings.audd_token.empty()) {
                    g_status_color = RGB(248, 113, 113);
                    SetWindowTextA(g_hwnd_status, "Please enter your AudD API Token.");
                    InvalidateRect(g_hwnd_status, nullptr, TRUE);
                    return 0;
                }
            }

            EnableWindow(g_hwnd_btn_identify, FALSE);
            EnableWindow(g_hwnd_btn_browser, FALSE);
            InvalidateRect(g_hwnd_btn_identify, nullptr, TRUE);
            InvalidateRect(g_hwnd_btn_browser, nullptr, TRUE);

            g_status_color = RGB(56, 189, 248);
            std::string status_msg = "Recording audio playback (" + std::to_string(settings.duration_seconds) + " seconds)...";
            SetWindowTextA(g_hwnd_status, status_msg.c_str());
            InvalidateRect(g_hwnd_status, nullptr, TRUE);

            SetWindowTextA(g_hwnd_song_title, "Title:  -");
            SetWindowTextA(g_hwnd_song_artist, "Artist: -");

            std::thread(run_recognition_worker, hwnd, settings).detach();
        }
        break;
    }

    case WM_RECOGNITION_DONE: {
        auto* result = reinterpret_cast<hearthis::RecognitionResult*>(lParam);
        EnableWindow(g_hwnd_btn_identify, TRUE);
        InvalidateRect(g_hwnd_btn_identify, nullptr, TRUE);

        if (!result->error_message.empty()) {
            g_status_color = RGB(248, 113, 113);
            std::string err = "Notice: " + result->error_message;
            SetWindowTextA(g_hwnd_status, err.c_str());
        } else if (result->matched) {
            g_status_color = RGB(52, 211, 153);
            std::string status_msg = "Matched via " + result->provider + "!";
            SetWindowTextA(g_hwnd_status, status_msg.c_str());

            std::string title_str = "Title:  " + result->title;
            std::string artist_str = "Artist: " + result->artist;
            SetWindowTextA(g_hwnd_song_title, title_str.c_str());
            SetWindowTextA(g_hwnd_song_artist, artist_str.c_str());

            g_current_youtube_url = result->youtube_url;
            EnableWindow(g_hwnd_btn_browser, TRUE);
            InvalidateRect(g_hwnd_btn_browser, nullptr, TRUE);
        } else {
            g_status_color = RGB(251, 146, 60);
            SetWindowTextA(g_hwnd_status, "No match found. Try again during a clear music section.");
            SetWindowTextA(g_hwnd_song_title, "Title:  No match found");
            SetWindowTextA(g_hwnd_song_artist, "Artist: -");
        }
        InvalidateRect(g_hwnd_status, nullptr, TRUE);

        delete result;
        break;
    }

    case WM_DESTROY: {
        if (g_bg_brush) DeleteObject(g_bg_brush);
        if (g_input_brush) DeleteObject(g_input_brush);
        if (g_card_brush) DeleteObject(g_card_brush);
        if (g_border_pen) DeleteObject(g_border_pen);
        if (g_font_title) DeleteObject(g_font_title);
        if (g_font_bold) DeleteObject(g_font_bold);
        if (g_font_regular) DeleteObject(g_font_regular);
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
    int height = 585;

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
