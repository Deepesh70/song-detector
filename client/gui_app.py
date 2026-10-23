"""Desktop GUI entrypoint for Song Detector."""

import sys
from pathlib import Path

# Ensure project root in sys.path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from client.gui.main_window import SongDetectorMainWindow, main
from client.gui.worker import RecognitionWorker
from client.gui.visualizer import AudioVisualizerWidget

__all__ = [
    "SongDetectorMainWindow",
    "RecognitionWorker",
    "AudioVisualizerWidget",
    "main",
]

if __name__ == "__main__":
    try:
        import ctypes
        ctypes.windll.ole32.CoUninitialize()
    except Exception:
        pass
    main()
