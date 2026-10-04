from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .cli import default_data_dir


def worker_command(arguments: list[str]) -> tuple[str, list[str]]:
    """Use a console worker beside the frozen GUI, or this Python environment."""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).with_name("npu-scribe-worker.exe")), arguments
    return sys.executable, ["-m", "npu_scribe.cli", *arguments]


def main() -> int:
    parser = argparse.ArgumentParser(prog="npu-scribe-desktop")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--model-root", type=Path, default=None)
    parser.add_argument("--ffmpeg", default=None)
    args = parser.parse_args()
    data_dir = (args.data_dir or default_data_dir()).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        from PySide6.QtCore import QLockFile
        from PySide6.QtWidgets import QApplication, QMessageBox

        from .desktop_ui import LectureWindow
    except ImportError as error:
        import traceback

        log = data_dir / "startup-error.log"
        log.write_text(traceback.format_exc(), encoding="utf-8")
        error_message = (
            "Desktop dependencies could not load"
            if getattr(sys, "frozen", False)
            else ("Install the 'desktop' extra to run the Windows application")
        )
        raise SystemExit(f"{error_message}. Details: {log}") from error

    app = QApplication(sys.argv)
    app.setApplicationName("NPU Scribe")
    lock = QLockFile(str(data_dir / "desktop.lock"))
    if not lock.tryLock(0):
        message = QMessageBox()
        message.setWindowTitle("NPU Scribe")
        message.setIcon(QMessageBox.Icon.Warning)
        message.setText("This lecture library is already open in another window.")
        message.exec()
        return 1
    window = LectureWindow(data_dir, args.model_root, args.ffmpeg)
    window.show()
    result = app.exec()
    lock.unlock()
    return int(result)


if __name__ == "__main__":
    sys.exit(main())
