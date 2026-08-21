from __future__ import annotations

import sys
from typing import cast


def main() -> int:
    try:
        from PySide6.QtWidgets import (  # type: ignore[import-not-found]
            QApplication,
            QLabel,
            QMainWindow,
            QSystemTrayIcon,
        )
    except ImportError as error:
        raise SystemExit("Install the 'desktop' extra to run the Windows application") from error

    app = QApplication(sys.argv)
    app.setApplicationName("NPU Scribe")
    app.setQuitOnLastWindowClosed(False)
    window = QMainWindow()
    window.setWindowTitle("NPU Scribe — host validation pending")
    window.setCentralWidget(QLabel("NPU Scribe\nWindows and NPU validation pending"))
    window.resize(640, 360)
    tray = QSystemTrayIcon(window)
    tray.setToolTip("NPU Scribe")
    tray.show()
    window.show()
    return cast(int, app.exec())
