import os
import subprocess
from typing import Optional


def show_windows_toast(
    title: str,
    message: str,
    app_id: str = "HearThis",
) -> None:
    """Display a native Windows 10/11 Toast Notification."""
    # Sanitize inputs for PowerShell
    safe_title = title.replace('"', '`"').replace("'", "''")
    safe_msg = message.replace('"', '`"').replace("'", "''")

    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $textNodes = $template.GetElementsByTagName("text")
    $textNodes.Item(0).AppendChild($template.CreateTextNode("{safe_title}")) | Out-Null
    $textNodes.Item(1).AppendChild($template.CreateTextNode("{safe_msg}")) | Out-Null
    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{app_id}")
    $notification = [Windows.UI.Notifications.ToastNotification]::new($template)
    $notifier.Show($notification)
    """

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            timeout=5,
            check=False,
        )
    except Exception:
        # Fallback to standard console output if Toast manager is disabled
        print(f"[{title}] {message}")


if __name__ == "__main__":
    show_windows_toast("Song Detector Active", "Press Ctrl+Alt+S anytime to identify system audio.")
