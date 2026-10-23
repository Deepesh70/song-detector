import sys
from pathlib import Path
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QImage, QPainter, QColor, QPen, QBrush, QPainterPath

def generate_app_icon():
    assets_dir = Path(__file__).resolve().parent.parent / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    icon_path_png = assets_dir / "icon.png"

    size = 256
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # 1. Rounded squircle background
    bg_path = QPainterPath()
    margin = 8.0
    rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    bg_path.addRoundedRect(rect, 48.0, 48.0)

    # Deep dark slate container
    painter.fillPath(bg_path, QColor("#16161a"))

    # Subtle outer border
    painter.setPen(QPen(QColor("#2a2a32"), 4.0))
    painter.drawPath(bg_path)

    # 2. Soundwave / Audio Equalizer Landmark Motif
    # 5 prominent vertical bars representing time-frequency acoustic landmarks
    bar_color = QColor("#10b981") # Emerald accent
    bar_secondary = QColor("#059669")

    # Heights of 5 dynamic bars:
    # [center highest, harmonics around it]
    bars = [
        (46, 60),    # x, height
        (82, 110),
        (118, 160),
        (154, 110),
        (190, 60),
    ]

    for x, h in bars:
        bar_path = QPainterPath()
        bar_rect = QRectF(x, (size - h) / 2.0, 20.0, h)
        bar_path.addRoundedRect(bar_rect, 10.0, 10.0)

        # Gradient or solid emerald
        painter.fillPath(bar_path, bar_color)

    # 3. Small constellation peak points (Shazam landmark stars)
    peak_points = [
        (128, 40),
        (80, 62),
        (176, 62),
    ]
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor("#34d399")))
    for px, py in peak_points:
        painter.drawEllipse(QPointF(px, py), 5.0, 5.0)

    painter.end()

    image.save(str(icon_path_png), "PNG")

    # Generate full Windows Explorer multi-resolution ICO (16, 24, 32, 48, 64, 128, 256)
    import struct
    sizes = [16, 24, 32, 48, 64, 128, 256]
    png_blobs = []
    for s in sizes:
        scaled = image.scaled(
            s, s, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        ba = QtCore.QByteArray()
        buf = QtCore.QBuffer(ba)
        buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        scaled.save(buf, "PNG")
        png_blobs.append((s, bytes(ba)))

    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = []
    for s, blob in png_blobs:
        w = 0 if s == 256 else s
        h = 0 if s == 256 else s
        entry = struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(blob), offset)
        entries.append(entry)
        offset += len(blob)

    ico_data = header + b"".join(entries) + b"".join(b for _, b in png_blobs)
    icon_path_ico = assets_dir / "icon.ico"
    icon_path_ico.write_bytes(ico_data)
    print(f"Generated multi-res app icon at {icon_path_png} and {icon_path_ico}")

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    generate_app_icon()
