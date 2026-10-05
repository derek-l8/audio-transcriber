"""Check Windows shortcuts and insertion in a temporary test-owned Qt editor.

No microphone, models, clipboard writes, or other application text are used.
Run with an output directory outside cloud sync; see TESTING.md.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget

from audio_transcriber.desktop_dictation import Shortcut
from audio_transcriber.dictation import Hotkey
from audio_transcriber.windows_dictation import Input, InputUnion, KeyboardInput, WindowsInput


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def editor(root: Path) -> None:
    app = QApplication([])
    window = QWidget()
    window.setWindowTitle("Audio Transcriber — owned dictation test field")
    window.resize(450, 160)
    layout = QVBoxLayout(window)
    fields = {name: QLineEdit() for name in ("first", "second", "password")}
    fields["password"].setEchoMode(QLineEdit.EchoMode.Password)
    for field in fields.values():
        layout.addWidget(field)
    window.show()
    window.activateWindow()
    fields["first"].setFocus()
    last = ""

    def tick() -> None:
        nonlocal last
        command = root / "command.txt"
        if command.exists():
            name = command.read_text(encoding="utf-8")
            if name != last:
                last = name
                if name == "quit":
                    app.quit()
                    return
                fields[name].setFocus()
        state = {
            "hwnd": int(window.winId()),
            "pid": os.getpid(),
            "focus": next((name for name, field in fields.items() if field.hasFocus()), ""),
        }
        state.update({name: field.text() for name, field in fields.items()})
        temporary = root / "state.tmp"
        temporary.write_text(json.dumps(state), encoding="utf-8")
        temporary.replace(root / "state.json")

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(50)
    QTimer.singleShot(60000, app.quit)
    app.exec()


def validate(app: QApplication, root: Path, text: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("QT_QPA_PLATFORM", None)
    child = subprocess.Popen(  # noqa: S603 -- this script launches its fixed helper mode
        [sys.executable, str(Path(__file__).resolve()), "--owned-editor", str(root)],
        env=env,
        creationflags=0x08000000,
    )
    report: dict[str, str] = {}
    shortcut: Shortcut | None = None

    def wait_state(test: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
            try:
                state = json.loads((root / "state.json").read_text(encoding="utf-8"))
                if test(state):
                    return dict(state)
            except OSError, ValueError:
                pass
            time.sleep(0.02)
        raise RuntimeError("Owned editor did not reach the required state; keep its field focused.")

    try:
        state = wait_state(lambda s: s["focus"] == "first")
        native = WindowsInput()
        native.api.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        native.api.SetForegroundWindow(state["hwnd"])
        target = native.current()
        require(
            target.handle == state["hwnd"]
            and target.process_id == state["pid"]
            and target.editable,
            "The target is not the owned test field.",
        )
        result = native.insert(text, target)
        require(result.inserted, result.reason or "Insertion failed")
        wait_state(lambda s: s["first"] == text)
        report["unicode_insertion"] = "passed"
        (root / "command.txt").write_text("second", encoding="utf-8")
        wait_state(lambda s: s["focus"] == "second")
        require(
            not native.insert("MUST NOT APPEAR", target).inserted, "Changed focus was not rejected"
        )
        require(
            wait_state(lambda s: s["focus"] == "second")["second"] == "",
            "Changed field received input",
        )
        report["same_window_focus_change"] = "passed"
        (root / "command.txt").write_text("password", encoding="utf-8")
        wait_state(lambda s: s["focus"] == "password")
        secret = native.current()
        require(secret.password, "Password field was not identified")
        require(
            not native.insert("MUST NOT APPEAR", secret).inserted, "Password field was not rejected"
        )
        require(
            wait_state(lambda s: s["focus"] == "password")["password"] == "",
            "Password field received input",
        )
        report["password_rejection"] = "passed"  # noqa: S105 -- outcome, not a credential
        (root / "command.txt").write_text("second", encoding="utf-8")
        wait_state(lambda s: s["focus"] == "second")
        activated: list[bool] = []
        shortcut = Shortcut(native, lambda: activated.append(True))
        shortcut.enable("Ctrl+Alt+F9")
        try:
            native.register(shortcut.IDENT + 1, Hotkey(3, 120))
        except OSError:
            report["shortcut_conflict"] = "passed"
        else:
            native.unregister(shortcut.IDENT + 1)
            raise RuntimeError("Shortcut conflict was not detected")
        require(
            int(native.api.GetForegroundWindow() or 0) == target.handle,
            "Focus changed before shortcut validation",
        )
        events = [
            Input(1, InputUnion(keyboard=KeyboardInput(key, 0, flag, 0, 0)))
            for key, flag in ((17, 0), (18, 0), (120, 0), (120, 2), (18, 2), (17, 2))
        ]
        batch = (Input * len(events))(*events)
        require(
            native.api.SendInput(len(batch), batch, ctypes.sizeof(Input)) == len(batch),
            "Shortcut input was rejected",
        )
        wait_state(lambda s: bool(activated))
        require(activated == [True] and shortcut.released(), "Incorrect shortcut dispatch/release")
        report["native_shortcut_dispatch_and_release"] = "passed"
        shortcut.disable()
        native.register(shortcut.IDENT + 1, Hotkey(3, 120))
        native.unregister(shortcut.IDENT + 1)
        report["shortcut_unregistered"] = "passed"
    finally:
        if shortcut:
            shortcut.disable()
        (root / "command.txt").write_text("quit", encoding="utf-8")
        try:
            child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            child.terminate()
            child.wait(timeout=5)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--text-file", type=Path, help="UTF-8 text to insert in the owned editor")
    parser.add_argument("--owned-editor", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("This validation requires Windows.")
    if args.owned_editor:
        editor(args.owned_editor)
        return
    if args.output_dir is None:
        parser.error("Supply --output-dir outside cloud sync.")
    args.output_dir = args.output_dir.expanduser().resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    text = "Café 😀 dictation check."
    if args.text_file is not None:
        require(args.text_file.stat().st_size <= 16384, "Insertion fixture exceeds 16 KB")
        text = args.text_file.read_text(encoding="utf-8").strip().replace("\n", " ")
        require(bool(text), "Insertion fixture is empty")
    app = QApplication([])
    with tempfile.TemporaryDirectory(prefix="owned-dictation-", dir=args.output_dir) as folder:
        report = validate(app, Path(folder), text)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
