import ctypes
from ctypes import wintypes
import io
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional
import httpx
import numpy as np
import soundfile as sf
import certifi

# Ensure project root in sys.path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Sanitize SSL_CERT_FILE
os.environ["SSL_CERT_FILE"] = certifi.where()

from client.capture import WasapiLoopbackCapture
from client.preprocessor import SAMPLE_RATE_CANONICAL
from client.notifier import show_windows_toast

API_BASE_URL: str = "http://127.0.0.1:8000"

# Win32 Constants
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20
WM_HOTKEY = 0x0312
WM_COMMAND = 0x0111
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_DESTROY = 0x0002

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000

VK_S = 0x53
VK_D = 0x44
VK_F9 = 0x78

HOTKEY_ID_CTRL_SHIFT_S = 1
HOTKEY_ID_F9 = 2
HOTKEY_ID_CTRL_ALT_S = 3

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010

IDI_APPLICATION = 32512
MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
TPM_RIGHTBUTTON = 0x0002

MENU_ID_IDENTIFY = 1001
MENU_ID_EXIT = 1002


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


class SongDetectorTrayApp:
    """Windows system tray daemon with global hotkeys and tray icon listener."""

    def __init__(self, api_url: str = API_BASE_URL):
        self.api_url = api_url
        self.capture = WasapiLoopbackCapture()
        self.capture.start_keepalive()
        self.is_recognizing = False
        self.running = True
        self.hwnd = None

    def _identify_worker(self) -> None:
        """Run loopback recording, local index matching, and two-step fallback."""
        if self.is_recognizing:
            print("[Busy] Recognition already in progress. Please wait...")
            return

        self.is_recognizing = True
        try:
            print("\n[Listening] Capturing 5 seconds of system playback via WASAPI...")
            show_windows_toast("Song Detector", "Listening to system audio (5s)...")
            passed_gate, hashes, pcm_buffer = self.capture.capture_and_fingerprint()

            if not passed_gate:
                print("[Silence Gate] Audio below -50 dBFS silence threshold.")
                show_windows_toast("Song Detector", "Silence detected. Audio was below -50 dBFS.")
                return

            print(f"[Fingerprinted] Extracted {len(hashes)} landmark pairs. Checking local catalog...")
            with httpx.Client(base_url=self.api_url, timeout=12.0, verify=False) as client:
                # Step 1: Query local catalog
                resp = client.post("/v1/recognize", json={"hashes": hashes})
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("matched"):
                        track = data["track"]
                        title = track.get("title", "Unknown")
                        artist = track.get("artist", "Unknown")
                        print(f"[Match Hit] 🎵 {title} by {artist} (Local Catalog)")
                        show_windows_toast(
                            f"🎵 {title}",
                            f"Artist: {artist} (Local Hit)",
                        )
                        return

                    # Step 2: Fallback query
                    fallback_token = data.get("fallback_token")
                    if fallback_token:
                        print("[Local Miss] Forwarding 5s audio to global provider fallback...")
                        wav_bio = io.BytesIO()
                        sf.write(wav_bio, pcm_buffer, SAMPLE_RATE_CANONICAL, format="WAV")
                        wav_bytes = wav_bio.getvalue()

                        fb_resp = client.post(
                            "/v1/recognize/fallback",
                            content=wav_bytes,
                            headers={
                                "Authorization": f"Bearer {fallback_token}",
                                "Content-Type": "audio/wav",
                            },
                        )

                        if fb_resp.status_code == 200:
                            fb_data = fb_resp.json()
                            if fb_data.get("matched"):
                                fb_track = fb_data["track"]
                                title = fb_track.get("title", "Unknown")
                                artist = fb_track.get("artist", "Unknown")
                                album = fb_track.get("album", "")
                                print(f"[Match Hit] 🎵 {title} by {artist} ({album}) (Global Fallback)")
                                show_windows_toast(
                                    f"🎵 {title}",
                                    f"Artist: {artist}\nAlbum: {album}",
                                )
                                return

            print("[No Match] No matching track found in local or global databases.")
            show_windows_toast("Song Detector", "No match found in local or global databases.")

        except Exception as e:
            print(f"[Error] Recognition failed: {e}")
            show_windows_toast("Song Detector Error", f"Recognition failed: {str(e)[:100]}")
        finally:
            self.is_recognizing = False

    def trigger_identification(self) -> None:
        """Spawn recognition thread."""
        threading.Thread(target=self._identify_worker, daemon=True).start()

    def _keyboard_listener_loop(self) -> None:
        """Direct hardware key-state polling thread via Win32 GetAsyncKeyState.

        Bypasses OEM hotkey collisions (e.g. HP OMEN / HP System Info error 1409).
        """
        user32 = ctypes.windll.user32
        VK_CONTROL = 0x11
        VK_SHIFT = 0x10
        VK_MENU = 0x12  # Alt
        VK_S = 0x53
        VK_F9 = 0x78
        VK_F8 = 0x77

        was_combo_pressed = False
        while self.running:
            ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
            shift = bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)
            alt = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
            s_key = bool(user32.GetAsyncKeyState(VK_S) & 0x8000)
            f9_key = bool(user32.GetAsyncKeyState(VK_F9) & 0x8000)
            f8_key = bool(user32.GetAsyncKeyState(VK_F8) & 0x8000)

            is_pressed = False
            detected_key = ""
            if ctrl and shift and s_key:
                is_pressed = True
                detected_key = "Ctrl+Shift+S"
            elif ctrl and alt and s_key:
                is_pressed = True
                detected_key = "Ctrl+Alt+S"
            elif f9_key:
                is_pressed = True
                detected_key = "F9"
            elif f8_key:
                is_pressed = True
                detected_key = "F8"

            if is_pressed and not was_combo_pressed:
                print(f"\n[Hotkey Pressed: {detected_key}] Triggering recognition...")
                self.trigger_identification()
                was_combo_pressed = True
            elif not is_pressed:
                was_combo_pressed = False

            time.sleep(0.04)

    def run(self) -> None:
        """Run the Win32 window message loop for hotkey and system tray events."""
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        shell32 = ctypes.windll.shell32

        # Explicitly declare 64-bit argument and return types to prevent OverflowError on 64-bit Windows
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = wintypes.LPARAM
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = wintypes.LPARAM
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID
        ]
        user32.CreateWindowExW.restype = wintypes.HWND

        WNDPROC = ctypes.WINFUNCTYPE(
            wintypes.LPARAM,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )

        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_HOTKEY:
                if wparam in (HOTKEY_ID_CTRL_SHIFT_S, HOTKEY_ID_F9, HOTKEY_ID_CTRL_ALT_S):
                    self.trigger_identification()
                return 0

            elif msg == WM_TRAYICON:
                if lparam == WM_RBUTTONUP:
                    # Show tray context menu
                    hmenu = user32.CreatePopupMenu()
                    user32.AppendMenuW(hmenu, MF_STRING, MENU_ID_IDENTIFY, "Identify Song Now")
                    user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
                    user32.AppendMenuW(hmenu, MF_STRING, MENU_ID_EXIT, "Exit")

                    pt = wintypes.POINT()
                    user32.GetCursorPos(ctypes.byref(pt))
                    user32.SetForegroundWindow(hwnd)
                    user32.TrackPopupMenu(hmenu, TPM_RIGHTBUTTON, pt.x, pt.y, 0, hwnd, None)
                    user32.DestroyMenu(hmenu)
                    return 0

                elif lparam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self.trigger_identification()
                    return 0

            elif msg == WM_COMMAND:
                cmd_id = wparam & 0xFFFF
                if cmd_id == MENU_ID_IDENTIFY:
                    self.trigger_identification()
                elif cmd_id == MENU_ID_EXIT:
                    user32.PostQuitMessage(0)
                return 0

            elif msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0

            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        proc = WNDPROC(wnd_proc)

        # Register Window Class
        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        wndclass = WNDCLASSW()
        wndclass.lpfnWndProc = proc
        wndclass.hInstance = kernel32.GetModuleHandleW(None)
        wndclass.lpszClassName = "SongDetectorTrayWindow"
        user32.RegisterClassW(ctypes.byref(wndclass))

        # Create hidden window to handle messages
        self.hwnd = user32.CreateWindowExW(
            0,
            wndclass.lpszClassName,
            "Song Detector Listener",
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            wndclass.hInstance,
            None,
        )

        # Start background hardware keyboard listener
        kb_thread = threading.Thread(target=self._keyboard_listener_loop, daemon=True)
        kb_thread.start()

        # Register OS-level hotkeys as secondary mechanism
        active_shortcuts = ["Ctrl+Shift+S", "Ctrl+Alt+S", "F9", "F8"]
        user32.RegisterHotKey(self.hwnd, HOTKEY_ID_CTRL_SHIFT_S, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_S)
        user32.RegisterHotKey(self.hwnd, HOTKEY_ID_F9, MOD_NOREPEAT, VK_F9)
        user32.RegisterHotKey(self.hwnd, HOTKEY_ID_CTRL_ALT_S, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_S)

        shortcuts_str = " / ".join(active_shortcuts)

        # Create System Tray Icon
        h_icon = user32.LoadIconW(None, wintypes.LPCWSTR(IDI_APPLICATION))
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = h_icon
        nid.szTip = f"Song Detector ({shortcuts_str})"

        user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
        user32.PeekMessageW.restype = wintypes.BOOL
        PM_REMOVE = 0x0001
        WM_QUIT = 0x0012

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        show_windows_toast("Song Detector Active", f"Running in tray. Press {shortcuts_str} or click the tray icon.")
        print(f"[Daemon Active] Running in Windows system tray.")
        print(f"[Hotkeys Active] {shortcuts_str}")
        print("[Direct Click] Left-click the taskbar tray icon to identify immediately.")
        print("[Controls] Press Ctrl+C in this terminal, or right-click the tray icon and click Exit.")

        # Message loop with sleep to allow Python signal handlers (Ctrl+C) to trigger
        msg = wintypes.MSG()
        try:
            while self.running:
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    if msg.message == WM_QUIT or msg.message == WM_DESTROY:
                        return
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                time.sleep(0.05)
        except KeyboardInterrupt:
            print("\n[Exiting] Tray daemon stopped by user.")
        finally:
            # Cleanup on exit
            self.running = False
            for h_id in (HOTKEY_ID_CTRL_SHIFT_S, HOTKEY_ID_F9, HOTKEY_ID_CTRL_ALT_S):
                user32.UnregisterHotKey(self.hwnd, h_id)
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            self.capture.stop_keepalive()


if __name__ == "__main__":
    app = SongDetectorTrayApp()
    app.run()
