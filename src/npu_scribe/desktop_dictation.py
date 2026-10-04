"""Microphone dictation using Qt capture and the existing isolated CLI worker."""

from __future__ import annotations

import array
import json
import math
import re
import sys
import time
import uuid
from collections.abc import Callable
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO

from PySide6.QtCore import (
    QAbstractNativeEventFilter,
    QByteArray,
    QIODevice,
    QProcess,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import QCloseEvent
from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices, QtAudio
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from .acquisition import MANIFEST
from .ai_cleanup import DEFAULT_MODEL
from .config import PROCESSING_DEFAULTS
from .desktop import worker_command
from .dictation import MAX_SECONDS, DictationHistory, Hotkey, normalize_capture, parse_hotkey
from .insertion import FocusTarget
from .storage import SessionStore, atomic_json, safe_child
from .windows_dictation import WindowsInput

if TYPE_CHECKING:
    from .desktop_ui import LectureWindow


class Task(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, action: Callable[[], Any], parent: QDialog) -> None:
        super().__init__(parent)
        self.action = action

    def run(self) -> None:
        try:
            self.result.emit(self.action())
        except Exception as error:
            self.failed.emit(str(error))


class Microphone:
    """Pull native PCM promptly; normalization is done after recording stops."""

    def __init__(self, owner: QDialog) -> None:
        self.owner = owner
        self.source: QAudioSource | None = None
        self.stream: QIODevice | None = None
        self.file: BinaryIO | None = None
        self.format = QAudioFormat()
        self.bytes_written = 0
        self.failure = ""
        self.limit = 0
        self.level = 0

    def start(self, device_id: bytes, path: Path, failed: Callable[[], None]) -> None:
        devices = QMediaDevices.audioInputs()
        device = next((d for d in devices if d.id().data() == device_id), None)
        if device is None:
            raise OSError("Microphone is unavailable. Refresh the microphone list.")
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):
            fmt = device.preferredFormat()
        if (
            not 8000 <= fmt.sampleRate() <= 192000
            or not 1 <= fmt.channelCount() <= 8
            or fmt.sampleFormat() == QAudioFormat.SampleFormat.Unknown
        ):
            raise OSError("This microphone has an unsupported recording format.")
        self.format = fmt
        self.failure = ""
        self.bytes_written = 0
        self.limit = min(64 * 1024 * 1024, MAX_SECONDS * fmt.sampleRate() * fmt.bytesPerFrame())
        self.file = path.open("wb")
        self.source = QAudioSource(device, fmt, self.owner)
        self.source.setBufferSize(fmt.bytesForDuration(100000))
        self.stream = self.source.start()
        if self.stream is None or self.source.error() != QtAudio.Error.NoError:
            self.stop()
            raise OSError("Could not start the microphone. Check Windows microphone permissions.")
        self.stream.readyRead.connect(lambda: self._read(failed))

    def check_error(self) -> bool:
        if self.source is not None and self.source.error() != QtAudio.Error.NoError:
            self.failure = "Microphone stopped unexpectedly. Check its connection and permissions."
            return True
        return False

    def _read(self, failed: Callable[[], None]) -> None:
        if self.stream is None or self.file is None:
            return
        try:
            data = self.stream.readAll().data()
            remaining = self.limit - self.bytes_written
            frame = self.format.bytesPerFrame()
            data = data[: max(0, remaining // frame * frame)]
            self.file.write(data)
            self.bytes_written += len(data)
            kind, scale, offset = {
                QAudioFormat.SampleFormat.Int16: ("h", 32768, 0),
                QAudioFormat.SampleFormat.Int32: ("i", 2147483648, 0),
                QAudioFormat.SampleFormat.Float: ("f", 1, 0),
                QAudioFormat.SampleFormat.UInt8: ("B", 128, 128),
            }[self.format.sampleFormat()]
            samples = array.array(kind)
            samples.frombytes(data[: len(data) // samples.itemsize * samples.itemsize])
            if sys.byteorder != "little":
                samples.byteswap()
            peak = max(
                (abs(float(v) - offset) / scale for v in samples if math.isfinite(v)), default=0
            )
            self.level = max(
                0, min(100, round((20 * math.log10(max(peak, 1e-10)) + 60) / 60 * 100))
            )
            if self.bytes_written >= self.limit:
                QTimer.singleShot(0, failed)
        except OSError as error:
            self.failure = f"Could not save the recording: {error}"
            QTimer.singleShot(0, failed)

    def stop(self) -> tuple[int, int, str]:
        if self.stream is not None:
            self._read(lambda: None)
        source, self.source = self.source, None
        self.stream = None
        if source is not None:
            source.stop()
            source.deleteLater()
        if self.file is not None:
            file, self.file = self.file, None
            try:
                file.close()
            except OSError as error:
                self.failure = f"Could not finish saving the recording: {error}"
        kind = {
            QAudioFormat.SampleFormat.Int16: "int16",
            QAudioFormat.SampleFormat.Int32: "int32",
            QAudioFormat.SampleFormat.Float: "float",
            QAudioFormat.SampleFormat.UInt8: "uint8",
        }.get(self.format.sampleFormat(), "")
        return self.format.sampleRate(), self.format.channelCount(), kind


class Shortcut(QAbstractNativeEventFilter):
    IDENT = 0x4E53

    def __init__(self, api: WindowsInput, activate: Callable[[], None]) -> None:
        super().__init__()
        self.api = api
        self.activate = activate
        self.enabled = False
        self.hotkey: Hotkey | None = None

    def enable(self, text: str) -> None:
        self.disable()
        hotkey = parse_hotkey(text)
        self.api.register(self.IDENT, hotkey)
        app = QApplication.instance()
        if app is None:
            self.api.unregister(self.IDENT)
            raise RuntimeError("The desktop application is unavailable.")
        app.installNativeEventFilter(self)
        self.hotkey = hotkey
        self.enabled = True

    def disable(self) -> None:
        if self.enabled:
            self.api.unregister(self.IDENT)
            app = QApplication.instance()
            if app is not None:
                app.removeNativeEventFilter(self)
        self.enabled = False
        self.hotkey = None

    def released(self) -> bool:
        if self.hotkey is None or not self.api.held(self.hotkey.key):
            return True
        return any(
            self.hotkey.modifiers & mask and not self.api.held(key)
            for mask, key in ((1, 18), (2, 17), (4, 16))
        ) or bool(self.hotkey.modifiers & 8 and not (self.api.held(91) or self.api.held(92)))

    def nativeEventFilter(
        self, event_type: QByteArray | bytes | bytearray | memoryview, message: int
    ) -> tuple[bool, int]:
        if self.enabled and event_type in (b"windows_dispatcher_MSG", b"windows_generic_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == self.IDENT:
                QTimer.singleShot(0, self.activate)
                return True, 0
        return False, 0


class DictationWindow(QDialog):
    """Nonmodal controls; never raise the window when a shortcut completes."""

    changed = Signal()

    def __init__(self, owner: LectureWindow) -> None:
        super().__init__(owner)
        self.owner = owner
        self.root = owner.store.data_dir / "dictation"
        self.history = DictationHistory(self.root)
        self.store = SessionStore(self.root / "engine")
        self.settings_path = self.root / "settings.json"
        self.state = "idle"
        self.closing = False
        self.cancelled = False
        self.holding = False
        self.intended: FocusTarget | None = None
        self.job: Path | None = None
        self.ident = ""
        self.output = ""
        self.created_at = ""
        self.task: Task | None = None
        self.task_result: Any = None
        self.task_error = ""
        self.task_done: Callable[[Any], None] | None = None
        self.mic = Microphone(self)
        self.native: WindowsInput | None = None
        self.shortcut: Shortcut | None = None
        native_error = ""
        try:
            self.native = WindowsInput()
            self.shortcut = Shortcut(self.native, self.activate_shortcut)
        except (OSError, RuntimeError) as error:
            native_error = str(error)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._tick)
        self.started = 0.0
        self.setWindowTitle("NPU Scribe — Live dictation")
        self.resize(650, 650)
        layout = QVBoxLayout(self)
        description = QLabel(
            "Enable the shortcut, focus a text field in another app, then speak. "
            "Wait for Recording before speaking. Text is saved before insertion. "
            "Each recording can last up to two minutes."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        self.microphone = QComboBox()
        self.microphone.setAccessibleName("Microphone")
        mic_row = QHBoxLayout()
        mic_row.addWidget(self.microphone, 1)
        self.refresh_mics = QPushButton("Refresh")
        self.refresh_mics.clicked.connect(self.load_microphones)
        mic_row.addWidget(self.refresh_mics)
        form.addRow("Microphone", mic_row)
        self.model = QComboBox()
        for i in range(owner.model.count()):
            self.model.addItem(owner.model.itemText(i), owner.model.itemData(i))
        self.model.setCurrentIndex(owner.model.currentIndex())
        form.addRow("Speech model", self.model)
        self.device = QComboBox()
        self.device.addItems(["CPU", "GPU", "NPU"])
        self.device.setCurrentText("CPU")
        form.addRow("Speech device", self.device)
        self.cleanup = QComboBox()
        self.cleanup.addItems(["off", "light", "medium"])
        self.cleanup.setCurrentText(PROCESSING_DEFAULTS["dictation"][0])
        form.addRow("Cleanup", self.cleanup)
        form.addRow("Formatting", QLabel("Mostly prose"))
        self.cleanup_model = QComboBox()
        for model_id, spec in MANIFEST.items():
            if spec.task == "text-cleanup":
                self.cleanup_model.addItem(model_id, model_id)
        self.cleanup_model.setCurrentIndex(max(0, self.cleanup_model.findData(DEFAULT_MODEL)))
        form.addRow("Cleanup model", self.cleanup_model)
        self.cleanup_device = QComboBox()
        self.cleanup_device.addItems(["AUTO", "GPU", "CPU", "NPU"])
        form.addRow("Cleanup device", self.cleanup_device)
        self.hotkey_text = QLineEdit("Ctrl+Alt+Space")
        self.hotkey_text.setAccessibleName("Dictation shortcut")
        form.addRow("Shortcut", self.hotkey_text)
        self.mode = QComboBox()
        self.mode.addItems(["Toggle", "Hold to talk"])
        form.addRow("Shortcut mode", self.mode)
        self.enable = QCheckBox("Enable global shortcut")
        self.enable.toggled.connect(self._enable_shortcut)
        self.enable.setEnabled(self.shortcut is not None)
        form.addRow(self.enable)
        layout.addLayout(form)
        self.status = QLabel(native_error or "Ready. Shortcut is disabled until you enable it.")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setValue(0)
        self.level.setFormat("Microphone input")
        self.level.setAccessibleName("Microphone input level")
        layout.addWidget(self.level)
        row = QHBoxLayout()
        self.record = QPushButton("Record a copy")
        self.record.clicked.connect(self.record_or_stop)
        row.addWidget(self.record)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)
        layout.addWidget(QLabel("Recovered text"))
        self.results = QListWidget()
        self.results.setMaximumHeight(110)
        self.results.currentRowChanged.connect(self._show_record)
        layout.addWidget(self.results)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text, 1)
        row = QHBoxLayout()
        self.raw = QCheckBox("Show unedited transcript")
        self.raw.toggled.connect(lambda: self._show_record(self.results.currentRow()))
        row.addWidget(self.raw)
        self.copy = QPushButton("Copy text")
        self.copy.clicked.connect(self.copy_text)
        row.addWidget(self.copy)
        layout.addLayout(row)
        self.records: list[dict[str, Any]] = []
        self.load_microphones()
        self._load_settings()
        self._refresh_history()
        self._buttons()

    @property
    def busy(self) -> bool:
        return self.state != "idle"

    def load_microphones(self) -> None:
        selected = self.microphone.currentData()
        self.microphone.clear()
        default = QMediaDevices.defaultAudioInput().id().data()
        for device in QMediaDevices.audioInputs():
            self.microphone.addItem(device.description(), device.id().data())
        self.microphone.setCurrentIndex(max(0, self.microphone.findData(selected or default)))

    def _load_settings(self) -> None:
        try:
            value = json.loads(self.settings_path.read_text(encoding="utf-8"))
            for name in ("model", "device", "cleanup", "cleanup_model", "cleanup_device", "mode"):
                combo: QComboBox = getattr(self, name)
                index = combo.findText(str(value.get(name, "")))
                if index >= 0:
                    combo.setCurrentIndex(index)
            self.hotkey_text.setText(str(value.get("hotkey", "Ctrl+Alt+Space")))
            saved_mic = bytes.fromhex(str(value.get("microphone", "")))
            index = self.microphone.findData(saved_mic)
            if index >= 0:
                self.microphone.setCurrentIndex(index)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, AttributeError) as error:
            self.status.setText(f"Could not load dictation settings: {error}")
        # Enabling is explicit each launch; saved settings cannot register a shortcut silently.

    def _save_settings(self) -> None:
        value = {
            name: getattr(self, name).currentText()
            for name in ("model", "device", "cleanup", "cleanup_model", "cleanup_device", "mode")
        }
        value["hotkey"] = self.hotkey_text.text()
        value["microphone"] = bytes(self.microphone.currentData() or b"").hex()
        atomic_json(self.settings_path, value)

    def _enable_shortcut(self, enabled: bool) -> None:
        if self.shortcut is None:
            return
        if enabled:
            try:
                self._save_settings()
                self.shortcut.enable(self.hotkey_text.text())
                self.status.setText(
                    "Shortcut enabled. Focus another app's text field before recording."
                )
            except (OSError, ValueError, RuntimeError) as error:
                self.enable.setChecked(False)
                self.status.setText(str(error))
        else:
            self.shortcut.disable()
            if self.state == "recording" and self.holding:
                self.stop_recording()
        self._buttons()

    def activate_shortcut(self) -> None:
        if self.closing or self.shortcut is None or not self.shortcut.enabled:
            return
        if self.state == "recording":
            if self.mode.currentText() == "Toggle":
                self.stop_recording()
        elif self.state == "idle":
            self.holding = self.mode.currentText() == "Hold to talk"
            self.start_recording(insert=True)

    def record_or_stop(self) -> None:
        if self.state == "recording":
            self.stop_recording()
        elif not self.busy:
            self.holding = False
            self.start_recording(insert=False)

    def _state(self, value: str) -> None:
        self.state = value
        self._buttons()
        self.changed.emit()

    def _buttons(self) -> None:
        for control in (
            self.microphone,
            self.refresh_mics,
            self.model,
            self.device,
            self.cleanup,
            self.cleanup_model,
            self.cleanup_device,
        ):
            control.setEnabled(not self.busy)
        self.hotkey_text.setEnabled(not self.busy and not self.enable.isChecked())
        self.mode.setEnabled(not self.busy and not self.enable.isChecked())
        self.record.setText("Stop recording" if self.state == "recording" else "Record a copy")
        self.record.setEnabled(self.state in ("idle", "recording") and not self.closing)
        self.cancel_button.setEnabled(self.busy and not self.cancelled)
        self.copy.setEnabled(bool(self.text.toPlainText()))

    def start_recording(self, insert: bool) -> None:
        if self.busy or self.closing:
            return
        if self.owner._job_active:
            self.status.setText("Wait for file processing to finish before recording.")
            return
        model = str(self.model.currentData() or "")
        if not model:
            self.status.setText("Choose an installed speech model first.")
            return
        if model in MANIFEST and not (self.owner.model_root / model).is_dir():
            self.status.setText("Download the selected speech model into the model folder first.")
            return
        if (
            self.cleanup.currentText() != "off"
            and not (self.owner.model_root / str(self.cleanup_model.currentData())).is_dir()
        ):
            self.status.setText("Download the cleanup model first, or set Cleanup to Off.")
            return
        if self.microphone.currentData() is None:
            self.status.setText("No microphone is available. Connect one and press Refresh.")
            return
        self.cancelled = False
        self.intended = None
        self.output = ""
        try:
            self._save_settings()
            self.ident = uuid.uuid4().hex
            self.job = safe_child(self.root / "jobs", self.ident)
            self.job.mkdir(parents=True, exist_ok=False)
            self.created_at = datetime.now(UTC).isoformat()
        except (OSError, ValueError) as error:
            self.status.setText(f"Could not prepare recording storage: {error}")
            return
        if insert and self.native is not None:
            self._state("preparing")
            self.status.setText("Checking the target field…")
            self.timer.start()
            self._task(self.native.current, self._target_ready)
        else:
            self._begin_capture()

    def _task(self, action: Callable[[], Any], done: Callable[[Any], None]) -> None:
        self.task_result = None
        self.task_error = ""
        self.task_done = done
        self.task = Task(action, self)
        self.task.result.connect(self._task_result)
        self.task.failed.connect(self._task_failed)
        self.task.finished.connect(self._task_finished)
        self.task.start()

    def _task_result(self, value: Any) -> None:
        self.task_result = value

    def _task_failed(self, message: str) -> None:
        self.task_error = message

    def _task_finished(self) -> None:
        task, self.task = self.task, None
        if task is not None:
            task.deleteLater()
        if self.cancelled:
            self._idle("Cancelled. Any captured audio remains in dictation/jobs.")
        elif self.task_error:
            self._idle(f"Dictation stopped: {self.task_error}")
        elif self.task_done is not None:
            self.task_done(self.task_result)

    def _target_ready(self, target: FocusTarget) -> None:
        self.intended = target
        if self.holding and self.shortcut is not None and self.shortcut.released():
            self._idle("Hold the shortcut until recording starts, then speak.")
        elif not target.editable or target.password or target.elevated:
            self._idle(
                "Focus an editable text field in another app, then try again. "
                "Password fields are not supported."
            )
        else:
            self._begin_capture()

    def _begin_capture(self) -> None:
        if self.job is None:
            return
        try:
            self.mic.start(
                bytes(self.microphone.currentData()),
                self.job / "capture.pcm",
                self._microphone_stopped,
            )
        except (OSError, ValueError) as error:
            self._idle(str(error))
            return
        self.started = time.monotonic()
        self._state("recording")
        self.status.setText("Recording… speak now.")
        self.timer.start()

    def _microphone_stopped(self) -> None:
        if self.state != "recording":
            return
        if self.mic.failure:
            message = self.mic.failure
            self.mic.stop()
            self._idle(message + " Captured audio remains in dictation/jobs.")
        else:
            self.stop_recording()

    def _tick(self) -> None:
        if self.state != "recording":
            return
        if self.mic.check_error():
            self._microphone_stopped()
            return
        self.level.setValue(self.mic.level)
        elapsed = time.monotonic() - self.started
        if (
            elapsed >= MAX_SECONDS
            or self.holding
            and self.shortcut is not None
            and self.shortcut.released()
        ):
            self.stop_recording()
        else:
            self.status.setText(f"Recording… {int(elapsed)} s / {MAX_SECONDS} s")

    def stop_recording(self) -> None:
        if self.state != "recording" or self.job is None:
            return
        rate, channels, kind = self.mic.stop()
        if self.mic.failure:
            self._idle(self.mic.failure + " Captured audio remains in dictation/jobs.")
            return
        self.timer.stop()
        self._state("converting")
        self.status.setText("Preparing recorded audio…")
        source, destination = self.job / "capture.pcm", self.job / "recording.wav"
        self._task(
            lambda: normalize_capture(
                source, destination, rate, channels, kind, require_sound=True
            ),
            self._start_worker,
        )

    def _start_worker(self, wav: Path) -> None:
        if self.job is None:
            return
        try:
            (self.job / "capture.pcm").unlink(missing_ok=True)
        except OSError:
            pass
        args = [
            "--data-dir",
            str(self.store.data_dir),
            "--model-root",
            str(self.owner.model_root),
            "transcribe",
            str(wav),
            "--model",
            str(self.model.currentData()),
            "--device",
            self.device.currentText(),
            "--cleanup",
            self.cleanup.currentText(),
            "--cleanup-model",
            str(self.cleanup_model.currentData()),
            "--cleanup-device",
            self.cleanup_device.currentText(),
            "--cleanup-mode",
            "dictation",
            "--formatting",
            PROCESSING_DEFAULTS["dictation"][1],
            "--stop-file",
            str(self.job / "stop"),
        ]
        program, arguments = worker_command(args)
        self.output = ""
        self._state("processing")
        self.status.setText("Transcribing and cleaning… first use may take longer to load models.")
        self.process.setProgram(program)
        self.process.setArguments(arguments)
        self.process.start()

    def _read_output(self) -> None:
        self.output = (
            self.output
            + bytes(self.process.readAllStandardOutput().data()).decode("utf-8", errors="replace")
        )[-32000:]

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart and self.state == "processing":
            self._finished(1, QProcess.ExitStatus.CrashExit)

    def _finished(self, code: int, status: QProcess.ExitStatus) -> None:
        if self.state != "processing":
            return
        self._read_output()
        text = raw = ""
        error = ""
        match = re.search(r"^session: ([A-Za-z0-9_-]+)\r?$", self.output, re.MULTILINE)
        session_id = match.group(1) if match else ""
        success = code == 0 and status == QProcess.ExitStatus.NormalExit and not self.cancelled
        if success and not session_id:
            success = False
            error = "Worker returned no session identifier."
        try:
            if session_id:
                raw = self.store.load_transcript(session_id, "raw").text
                text = self.store.load_transcript(session_id, "formatted").text if success else raw
        except (OSError, ValueError) as caught:
            success = False
            text = raw
            error = str(caught)
        record = {
            "id": self.ident,
            "created_at": self.created_at,
            "raw": raw,
            "text": text,
            "session_id": session_id,
            "recording": str(self.job / "recording.wav") if self.job else "",
            "status": "cancelled" if self.cancelled else "ready" if success else "failed",
            "diagnostics": self.output[-4000:] or error or self.process.errorString(),
        }
        try:
            self.history.save(record)
        except (OSError, ValueError) as caught:
            self.text.setPlainText(text or raw)
            self._idle(
                f"Could not save recovery history: {caught}. "
                "Copy the text below; insertion skipped."
            )
            return
        self._refresh_history()
        if success and text.strip() and self.intended is not None and self.native is not None:
            # History is durable before the focus check or any generated keystrokes.
            self._state("inserting")
            self.status.setText("Checking focus before insertion…")
            intended = self.intended
            self._task(
                lambda: (
                    self.native.insert(
                        text, intended, lambda: not self.cancelled and not self.closing
                    )
                    if self.native
                    else None
                ),
                self._inserted,
            )
        elif success:
            self._idle(
                "Text saved. Use Copy text to paste it."
                if text.strip()
                else "No speech was recognized."
            )
        else:
            message = "Cancelled." if self.cancelled else "Processing failed."
            self._idle(
                f"{message} Recovered text and audio are retained. "
                f"{error or self.output[-1200:] or self.process.errorString()}"
            )

    def _inserted(self, result: Any) -> None:
        self._idle(
            "Text saved and input sent to the target field."
            if result and result.inserted
            else f"Text saved. {result.reason if result else 'Use Copy text to paste it.'}"
        )

    def cancel(self) -> None:
        if not self.busy:
            return
        self.cancelled = True
        if self.state == "recording":
            self.mic.stop()
            self._idle("Recording cancelled. Captured audio remains in dictation/jobs.")
        elif self.state == "processing" and self.job is not None:
            try:
                (self.job / "stop").touch()
                self.status.setText(
                    "Stopping after the current step… model loading may need to finish first."
                )
            except OSError as error:
                self.status.setText(f"Could not request cancellation: {error}")
                self.cancelled = False
        self._buttons()

    def _idle(self, message: str) -> None:
        self.timer.stop()
        self.level.setValue(0)
        self.holding = False
        self._state("idle")
        self.status.setText(message)
        if self.closing:
            QTimer.singleShot(0, self.close)

    def _refresh_history(self) -> None:
        self.records = self.history.records()
        self.results.clear()
        for record in self.records:
            self.results.addItem(
                f"{record.get('created_at', '')[:19].replace('T', ' ')} UTC — "
                f"{record.get('status', 'saved')}"
            )
        if self.records:
            self.results.setCurrentRow(0)

    def _show_record(self, row: int) -> None:
        if not 0 <= row < len(self.records):
            return
        record = self.records[row]
        self.text.setPlainText(str(record.get("raw" if self.raw.isChecked() else "text", "")))
        self._buttons()

    def copy_text(self) -> None:
        QApplication.clipboard().setText(self.text.toPlainText())
        self.status.setText("Copied text to the clipboard.")

    def closeEvent(self, event: QCloseEvent) -> None:
        self.closing = True
        self.enable.setChecked(False)
        if self.shortcut is not None:
            self.shortcut.disable()
        if self.busy:
            self.cancel()
            event.ignore()
        else:
            event.accept()
            self.closing = False
            self.changed.emit()
