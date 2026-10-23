"""Hardware-efficient audio waveform activity visualizer."""

import math
from PyQt6 import QtGui
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QWidget


class AudioVisualizerWidget(QWidget):
    """Custom hardware-efficient audio waveform / activity visualizer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.is_active = False
        self.phase = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def set_active(self, active: bool) -> None:
        self.is_active = active
        if active:
            self.timer.start(40)
        else:
            self.timer.stop()
            self.update()

    def _tick(self) -> None:
        self.phase = (self.phase + 1) % 360
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Background track
        painter.fillRect(0, 0, w, h, QtGui.QColor("#16161a"))

        if not self.is_active:
            # Subtle center line
            painter.setPen(QtGui.QPen(QtGui.QColor("#2a2a32"), 1))
            painter.drawLine(0, h // 2, w, h // 2)
            return

        # Active animated waveform bars
        bar_count = 32
        bar_width = max(2, (w - (bar_count * 3)) // bar_count)
        accent_color = QtGui.QColor("#10b981")

        for i in range(bar_count):
            x = i * (bar_width + 3) + 4
            sin_val = math.sin(math.radians(self.phase * 5 + i * 20))
            bar_h = int((abs(sin_val) * (h - 8)) + 4)
            y = (h - bar_h) // 2

            painter.setBrush(QtGui.QBrush(accent_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(x, y, bar_width, bar_h, 2, 2)
