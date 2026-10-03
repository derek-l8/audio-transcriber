"""Start an owned frozen Windows GUI, request normal close, and check its lock.

Uses Windows messages, not screen capture or interaction with other apps.
This tests idle window lifecycle only, not transcription/editing/playback UI.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[1]
    for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        synced = os.environ.get(name)
        if synced and checkout.is_relative_to(Path(synced).resolve()):
            raise RuntimeError("Run validation from a checkout outside OneDrive")
    if os.name != "nt":
        raise RuntimeError("This check requires Windows")
    executable = args.executable.resolve(strict=True)
    data_dir = args.data_dir.resolve()
    scratch = Path(__file__).resolve().parents[1] / ".scratch"
    if not data_dir.is_relative_to(scratch.resolve()) or data_dir.exists():
        raise RuntimeError("Use a fresh data directory inside this checkout's .scratch")
    data_dir.mkdir(parents=True)
    env = os.environ.copy()
    for name in ("PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME"):
        env.pop(name, None)
    env["PATH"] = os.pathsep.join((str(Path(env["WINDIR"]) / "System32"), env["WINDIR"]))
    env["QT_QPA_PLATFORM"] = "windows"
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.ShowWindow.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.PostMessageW.restype = wintypes.BOOL
    runs = []
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    for attempt in range(2):
        log = data_dir.parent / f"frozen-window-{attempt + 1}.log"
        with log.open("w", encoding="utf-8") as stream:
            process = subprocess.Popen(  # noqa: S603 - supplied local validation executable
                [str(executable), "--data-dir", str(data_dir)],
                cwd=data_dir,
                env=env,
                startupinfo=startup,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
            windows = []

            @callback_type
            def owned_window(hwnd, _, pid_expected=process.pid, owned_windows=windows):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == pid_expected:
                    title = ctypes.create_unicode_buffer(256)
                    user32.GetWindowTextW(hwnd, title, len(title))
                    if title.value == "NPU Scribe — Lecture library":
                        user32.ShowWindow(hwnd, subprocess.SW_HIDE)
                        owned_windows.append(hwnd)
                return True

            try:
                deadline = time.monotonic() + 30
                while not windows and process.poll() is None and time.monotonic() < deadline:
                    user32.EnumWindows(owned_window, 0)
                    time.sleep(0.1)
                if not windows or not (data_dir / "desktop.lock").is_file():
                    raise RuntimeError("Frozen main window and library lock were not both ready")
                # Let the event loop run before its normal closeEvent is requested.
                time.sleep(1)
                if process.poll() is not None or not user32.PostMessageW(windows[0], 0x0010, 0, 0):
                    raise RuntimeError("Could not request normal WM_CLOSE")
                code = process.wait(timeout=30)
                if code != 0 or (data_dir / "desktop.lock").exists():
                    raise RuntimeError("Normal close did not exit cleanly and release the lock")
                runs.append({"exit_code": code, "native_window_found": True, "lock_removed": True})
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            {
                "runs": runs,
                "scope": "Native Windows frozen GUI idle close and reopen; "
                "minimal PATH; no UI workflow interaction.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("Frozen native window close/reopen passed twice")


if __name__ == "__main__":
    main()
