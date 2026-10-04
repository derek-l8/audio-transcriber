"""Imported lecture library; inference runs in a child CLI process."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .acquisition import MANIFEST
from .ai_cleanup import DEFAULT_MODEL
from .desktop import worker_command
from .desktop_editing import RevisionHistoryDialog, SegmentEditDialog
from .desktop_player import LecturePlayer
from .editing import (
    EditRevision,
    current_revision,
    load_revision,
    revision_history,
    save_segment_edit,
)
from .export import ExportError, write_export
from .media import resolve_ffmpeg
from .models import Session
from .storage import SessionStore, atomic_json


class LectureWindow(QMainWindow):
    def __init__(
        self, data_dir: Path, model_root: Path | None = None, ffmpeg: str | None = None
    ) -> None:
        super().__init__()
        self.store = SessionStore(data_dir)
        self.settings_path = self.store.data_dir / "desktop-settings.json"
        settings: dict[str, str] = {}
        settings_error = ""
        if self.settings_path.exists():
            try:
                value = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if not isinstance(value, dict) or not all(
                    isinstance(v, str) for v in value.values()
                ):
                    raise ValueError("settings must contain text values")
                settings = value
            except (OSError, ValueError) as error:
                settings_error = f"Could not read settings: {error}"
        self.model_root = (
            (model_root or Path(settings.get("model_root", str(self.store.data_dir / "models"))))
            .expanduser()
            .resolve()
        )
        self.ffmpeg = resolve_ffmpeg(ffmpeg or settings.get("ffmpeg")) or ""
        if self.ffmpeg and Path(self.ffmpeg).expanduser().is_file():
            self.ffmpeg = str(Path(self.ffmpeg).expanduser().resolve())
        self.sessions: dict[str, Session] = {}
        self.active_id: str | None = None
        self.before_ids: set[str] = set()
        self.stop_file: Path | None = None
        self.output = ""
        self._job_active = False
        self.closing = False
        self.job_kind = "transcription"
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.refresh)
        self.setWindowTitle("NPU Scribe — Lecture library")
        self.resize(1100, 760)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 18, 20, 18)
        header = QLabel("Lecture library")
        header.setStyleSheet("font-size: 24px; font-weight: 600;")
        layout.addWidget(header)
        folder = QLabel(f"Recordings and transcripts: {self.store.data_dir}")
        folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        folder.setWordWrap(True)
        layout.addWidget(folder)
        self.models_label = QLabel()
        self.models_label.setWordWrap(True)
        setup = QHBoxLayout()
        setup.addWidget(self.models_label, 1)
        self.models_button = QPushButton("Choose model folder…")
        self.models_button.clicked.connect(self.choose_models)
        setup.addWidget(self.models_button)
        self.ffmpeg_button = QPushButton("Choose FFmpeg…")
        self.ffmpeg_button.clicked.connect(self.choose_ffmpeg)
        setup.addWidget(self.ffmpeg_button)
        layout.addLayout(setup)
        self.ffmpeg_label = QLabel()
        self.ffmpeg_label.setWordWrap(True)
        layout.addWidget(self.ffmpeg_label)
        controls = QHBoxLayout()
        self.model = QComboBox()
        self.model.setAccessibleName("Speech model")
        self.model.setObjectName("speechModel")
        self.model.addItem("Choose a speech model", "")
        for model_id, spec in MANIFEST.items():
            if spec.task == "speech":
                self.model.addItem(model_id, model_id)
        self.model.setCurrentIndex(max(0, self.model.findData(settings.get("model", ""))))
        controls.addWidget(self.model, 1)
        self.device = QComboBox()
        self.device.setAccessibleName("Transcription device")
        self.device.setObjectName("transcriptionDevice")
        self.device.addItems(["CPU", "GPU", "NPU", "auto"])
        self.device.setCurrentText(settings.get("device", "CPU"))
        controls.addWidget(QLabel("Device"))
        controls.addWidget(self.device)
        self.import_button = QPushButton("Import lecture…")
        self.import_button.clicked.connect(self.choose_import)
        controls.addWidget(self.import_button)
        self.resume_button = QPushButton("Resume selected")
        self.resume_button.clicked.connect(self.resume_selected)
        controls.addWidget(self.resume_button)
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause)
        controls.addWidget(self.pause_button)
        layout.addLayout(controls)
        cleanup_controls = QHBoxLayout()
        cleanup_controls.addWidget(QLabel("AI cleanup"))
        self.cleanup_model = QComboBox()
        self.cleanup_model.setAccessibleName("Cleanup model")
        for model_id, spec in MANIFEST.items():
            if spec.task == "text-cleanup":
                self.cleanup_model.addItem(model_id, model_id)
        self.cleanup_model.setCurrentIndex(
            max(0, self.cleanup_model.findData(settings.get("cleanup_model", DEFAULT_MODEL)))
        )
        cleanup_controls.addWidget(self.cleanup_model, 1)
        self.cleanup_mode = QComboBox()
        self.cleanup_mode.setAccessibleName("Cleanup mode")
        self.cleanup_mode.addItem("Lecture: preserve detail", "lecture")
        self.cleanup_mode.addItem("Dictation: resolve corrections", "dictation")
        self.cleanup_mode.setCurrentIndex(
            max(0, self.cleanup_mode.findData(settings.get("cleanup_mode", "lecture")))
        )
        cleanup_controls.addWidget(self.cleanup_mode)
        self.cleanup_style = QComboBox()
        self.cleanup_style.setAccessibleName("Cleanup style")
        self.cleanup_style.addItems(["off", "light", "medium"])
        self.cleanup_style.setToolTip(
            "Applied automatically after import/resume. Off keeps the unedited transcript."
        )
        self.cleanup_style.setCurrentText(settings.get("cleanup_style", "light"))
        cleanup_controls.addWidget(self.cleanup_style)
        self.cleanup_device = QComboBox()
        self.cleanup_device.setAccessibleName("Cleanup device")
        self.cleanup_device.addItems(["AUTO", "CPU", "GPU", "NPU"])
        self.cleanup_device.setCurrentText(settings.get("cleanup_device", "AUTO"))
        self.cleanup_device.setToolTip(
            "AUTO tries an available OpenVINO GPU, then CPU. NPU is an explicit choice."
        )
        cleanup_controls.addWidget(self.cleanup_device)
        self.cleanup_button = QPushButton("Clean selected")
        self.cleanup_button.setAccessibleName("Clean selected transcript with AI")
        self.cleanup_button.setToolTip(
            "Reads Raw and saves a separate AI version. Requires a downloaded cleanup model."
        )
        self.cleanup_button.clicked.connect(self.start_cleanup)
        cleanup_controls.addWidget(self.cleanup_button)
        self.summary_button = QPushButton("Summarize selected")
        self.summary_button.setToolTip(
            "Save separate study notes from Raw; review against the transcript."
        )
        self.summary_button.clicked.connect(self.start_summary)
        cleanup_controls.addWidget(self.summary_button)
        layout.addLayout(cleanup_controls)
        format_controls = QHBoxLayout()
        format_controls.addWidget(QLabel("Formatting"))
        self.format_style = QComboBox()
        self.format_style.setAccessibleName("Formatting style")
        for label, value in (
            ("Off", "off"),
            ("Mostly prose", "prose"),
            ("Mixed", "mixed"),
            ("Mostly structured", "structured"),
        ):
            self.format_style.addItem(label, value)
        self.format_style.setCurrentIndex(
            max(0, self.format_style.findData(settings.get("format_style", "prose")))
        )
        self.format_style.setToolTip(
            "Prose needs no model pass. Mixed and structured request a layout after cleanup, "
            "preserving every source passage."
        )
        format_controls.addWidget(self.format_style)
        self.format_button = QPushButton("Format selected")
        self.format_button.clicked.connect(self.start_formatting)
        self.format_button.setToolTip(
            "Formats the selected Raw, Balanced, or AI layer into a separate version. "
            "Does not summarize."
        )
        format_controls.addWidget(self.format_button)
        format_controls.addStretch()
        layout.addLayout(format_controls)
        split = QSplitter()
        self.library = QListWidget()
        self.library.setAccessibleName("Lecture library")
        self.library.setObjectName("lectureLibrary")
        self.library.setMinimumWidth(260)
        self.library.currentItemChanged.connect(self.show_selected)
        split.addWidget(self.library)
        viewer = QWidget()
        right = QVBoxLayout(viewer)
        self.details = QLabel("Import a lecture or select one from the library.")
        self.details.setWordWrap(True)
        right.addWidget(self.details)
        tools = QHBoxLayout()
        self.layer = QComboBox()
        self.layer.setAccessibleName("Transcript layer")
        self.layer.setObjectName("transcriptLayer")
        self.layer.addItems(["Raw", "Balanced", "Edited", "AI", "Formatted", "Summary"])
        self.layer.setToolTip(
            "Raw: unedited recognition. Balanced: rule-based formatting. "
            "AI: model cleanup. Formatted: complete text with layout. Summary: shorter study notes."
        )
        self.layer.currentIndexChanged.connect(self.show_selected)
        tools.addWidget(self.layer)
        self.search = QLineEdit()
        self.search.setAccessibleName("Find in transcript")
        self.search.setObjectName("transcriptSearch")
        self.search.setPlaceholderText("Find in transcript")
        self.search.returnPressed.connect(self.find_text)
        tools.addWidget(self.search, 1)
        find = QPushButton("Find next")
        find.clicked.connect(self.find_text)
        tools.addWidget(find)
        self.export_format = QComboBox()
        self.export_format.setAccessibleName("Export format")
        self.export_format.setObjectName("exportFormat")
        self.export_format.addItems(["text", "markdown", "srt", "json"])
        tools.addWidget(self.export_format)
        self.export_button = QPushButton("Export…")
        self.export_button.clicked.connect(self.choose_export)
        tools.addWidget(self.export_button)
        right.addLayout(tools)
        self.player = LecturePlayer()
        self.player.seek_button.clicked.connect(self.seek_selected_segment)
        self.segment_starts: list[float] = []
        right.addWidget(self.player)
        edit_controls = QHBoxLayout()
        self.edit_button = QPushButton("Edit selected segment…")
        self.edit_button.clicked.connect(self.edit_selected_segment)
        edit_controls.addWidget(self.edit_button)
        self.history_button = QPushButton("Revision history…")
        self.history_button.clicked.connect(self.show_history)
        edit_controls.addWidget(self.history_button)
        edit_controls.addStretch(1)
        right.addLayout(edit_controls)
        self.transcript = QTextEdit()
        self.transcript.setAccessibleName("Transcript")
        self.transcript.setObjectName("transcript")
        self.transcript.setReadOnly(True)
        self.transcript.setPlaceholderText(
            "Completed transcript segments appear here with timestamps."
        )
        right.addWidget(self.transcript, 1)
        split.addWidget(viewer)
        split.setStretchFactor(1, 3)
        layout.addWidget(split, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.status = QLabel(
            settings_error or "Ready to import. Audio stays in the selected library folder."
        )
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)
        self.cleanup_style.currentTextChanged.connect(self._buttons)
        self.format_style.currentIndexChanged.connect(self._buttons)
        self.export_format.currentTextChanged.connect(self._buttons)
        self.setCentralWidget(central)
        self.setStyleSheet(
            "QPushButton { padding: 7px 12px; } QComboBox, QLineEdit { padding: 5px; } "
            "QTextEdit { font-size: 14px; }"
        )
        self._folder_labels()
        self.refresh()

    @property
    def busy(self) -> bool:
        return self._job_active

    def _folder_labels(self) -> None:
        self.models_label.setText(f"Models: {self.model_root}")
        decoder_location = self.ffmpeg or "install on PATH or choose an executable"
        self.ffmpeg_label.setText(f"FFmpeg: {decoder_location}")

    def _save_settings(self) -> None:
        atomic_json(
            self.settings_path,
            {
                "model_root": str(self.model_root),
                "ffmpeg": self.ffmpeg,
                "cleanup_model": str(self.cleanup_model.currentData()),
                "cleanup_mode": str(self.cleanup_mode.currentData()),
                "cleanup_style": self.cleanup_style.currentText(),
                "cleanup_device": self.cleanup_device.currentText(),
                "format_style": str(self.format_style.currentData()),
                "model": self.model.currentData(),
                "device": self.device.currentText(),
            },
        )

    def choose_models(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Folder containing approved models", str(self.model_root)
        )
        if folder:
            self.model_root = Path(folder).resolve()
            self._folder_labels()

    def choose_ffmpeg(self) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self, "Choose FFmpeg executable", self.ffmpeg, "Executable (*.exe);;All files (*)"
        )
        if file:
            self.ffmpeg = file
            self._folder_labels()

    def choose_import(self) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Import lecture",
            "",
            "Media (*.wav *.mp3 *.m4a *.mp4);;All files (*)",
        )
        if file:
            self.start_import(Path(file))

    def start_import(self, source: Path) -> None:
        if self.busy:
            return
        model_id = self.model.currentData()
        if not model_id:
            self.status.setText("Choose an installed speech model before importing.")
            return
        self.active_id = None
        self._start(["transcribe", str(source.expanduser().resolve()), "--model", model_id])

    def selected_id(self) -> str | None:
        item = self.library.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def resume_selected(self) -> None:
        session_id = self.selected_id()
        if self.busy or session_id is None:
            return
        session = self.sessions[session_id]
        if session.status not in ("interrupted", "failed"):
            return
        diag = session.diagnostics
        self.active_id = session_id
        self._start(
            [
                "resume",
                session_id,
                "--model",
                str(diag.get("model_id", "")),
                "--chunk-seconds",
                str(diag.get("chunk_seconds", 30)),
                "--overlap-seconds",
                str(diag.get("overlap_seconds", 0)),
                "--chunk-strategy",
                str(diag.get("chunk_strategy", "fixed")),
            ]
        )

    def start_cleanup(self) -> None:
        session_id = self.selected_id()
        if self.busy or not session_id or not self.cleanup_button.isEnabled():
            return
        self._run_cleanup(session_id)

    def _run_cleanup(self, session_id: str) -> None:
        self.active_id = session_id
        self._start(
            [
                "cleanup",
                session_id,
                "--model",
                str(self.cleanup_model.currentData()),
                "--mode",
                str(self.cleanup_mode.currentData()),
                "--style",
                self.cleanup_style.currentText(),
                "--formatting",
                str(self.format_style.currentData()),
            ]
        )

    def start_formatting(self) -> None:
        session_id = self.selected_id()
        if self.busy or not session_id or not self.format_button.isEnabled():
            return
        source = self.layer.currentText().lower()
        if source not in ("raw", "balanced", "ai"):
            source = (
                "ai"
                if (self.store.session_dir(session_id) / "ai-transcript.json").is_file()
                else "raw"
            )
        self._run_formatting(session_id, source)

    def _run_formatting(self, session_id: str, source: str) -> None:
        self.active_id = session_id
        self._start(
            [
                "format",
                session_id,
                "--source",
                source,
                "--style",
                str(self.format_style.currentData()),
                "--model",
                str(self.cleanup_model.currentData()),
            ]
        )

    def start_summary(self) -> None:
        session_id = self.selected_id()
        if self.busy or not session_id or not self.summary_button.isEnabled():
            return
        self.active_id = session_id
        self._start(["summarize", session_id, "--model", str(self.cleanup_model.currentData())])

    def _start(self, arguments: list[str]) -> None:
        try:
            self._save_settings()
            jobs = self.store.data_dir / "jobs"
            jobs.mkdir(parents=True, exist_ok=True)
            self.stop_file = jobs / f"{uuid.uuid4().hex}.stop"
        except OSError as error:
            self.status.setText(f"Could not save settings: {error}")
            return
        self.job_kind = (
            arguments[0] if arguments[0] in ("cleanup", "summarize", "format") else "transcription"
        )
        self.before_ids = set(self.sessions)
        self.output = ""
        command = [
            "--data-dir",
            str(self.store.data_dir),
            "--model-root",
            str(self.model_root),
            *arguments,
            "--device",
            self.cleanup_device.currentText()
            if self.job_kind in ("cleanup", "summarize", "format")
            else self.device.currentText(),
            "--stop-file",
            str(self.stop_file),
        ]
        if self.ffmpeg and self.job_kind == "transcription":
            command += ["--ffmpeg", self.ffmpeg]
        program, command = worker_command(command)
        self.process.setProgram(program)
        self.process.setArguments(command)
        self.status.setText(
            (
                "Preparing formatted study notes…"
                if self.job_kind == "summarize"
                else "Preparing transcript layout…"
                if self.job_kind == "format"
                else "Preparing local AI cleanup…"
            )
            + " Raw and prior versions stay available."
            if self.job_kind in ("cleanup", "summarize", "format")
            else "Preparing lecture… Pause waits for the current chunk to finish."
        )
        self.progress.setRange(0, 0)
        self._job_active = True
        self.process.start()
        self.timer.start()
        self._buttons()

    def pause(self) -> None:
        if self.busy and self.stop_file:
            try:
                self.stop_file.touch()
                self.status.setText(
                    "Pause requested. Waiting for preparation or the current chunk to finish…"
                )
                self.pause_button.setEnabled(False)
            except OSError as error:
                self.status.setText(f"Could not request pause: {error}")

    def _read_output(self) -> None:
        self.output = (
            self.output
            + bytes(self.process.readAllStandardOutput().data()).decode("utf-8", errors="replace")
        )[-8192:]
        if self.job_kind in ("cleanup", "summarize", "format"):
            for line in reversed(self.output.splitlines()):
                if line.startswith(("cleanup_blocks: ", "format_blocks: ")):
                    try:
                        done, total = map(int, line.split(": ", 1)[1].split("/"))
                        self.progress.setRange(0, max(1, total))
                        self.progress.setValue(done)
                        self.progress.setFormat(f"{done} / {total} text blocks")
                    except ValueError:
                        pass
                    break

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._finished(1, QProcess.ExitStatus.CrashExit)

    def _finished(self, code: int, exit_status: QProcess.ExitStatus) -> None:
        self._job_active = False
        self._read_output()
        self.timer.stop()
        cleanup_error = ""
        was_paused = self.stop_file is not None and self.stop_file.exists()
        if self.stop_file:
            try:
                self.stop_file.unlink(missing_ok=True)
            except OSError as error:
                cleanup_error = f" Could not remove the completed job's pause marker: {error}"
        self.refresh()
        if code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            self.progress.setRange(0, 1)
            self.progress.setValue(1)
            self.progress.setFormat("Complete")
            if self.job_kind in ("cleanup", "summarize", "format"):
                target_layer = "Summary" if self.job_kind == "summarize" else "AI"
                if self.job_kind == "format" or (
                    self.job_kind == "cleanup" and self.format_style.currentData() != "off"
                ):
                    target_layer = "Formatted"
                self.layer.setCurrentText(target_layer)
                self.show_selected()
                self.status.setText(
                    "Summary ready. Review these notes against Raw."
                    if self.job_kind == "summarize"
                    else "Transcript formatting ready. Review the layout against its source."
                    if target_layer == "Formatted"
                    else "AI cleanup ready. Review the AI version against Raw before using it."
                )
            else:
                self.layer.setCurrentText("Raw")
                if self.active_id:
                    for row in range(self.library.count()):
                        if self.library.item(row).data(Qt.ItemDataRole.UserRole) == self.active_id:
                            self.library.setCurrentRow(row)
                            break
                if (
                    not self.closing
                    and not was_paused
                    and self.cleanup_style.currentText() != "off"
                ):
                    # The speech worker has exited, so its model memory is released first.
                    self._buttons()
                    if self.active_id:
                        self._run_cleanup(self.active_id)
                    if self.busy:
                        return
                if (
                    not self.closing
                    and not was_paused
                    and self.format_style.currentData() != "off"
                    and self.active_id
                ):
                    self._run_formatting(self.active_id, "raw")
                    if self.busy:
                        return
                self.status.setText(
                    "Transcript ready. Select Raw or Balanced to review and export."
                )
        elif code == 130 and exit_status == QProcess.ExitStatus.NormalExit:
            self.status.setText(
                (
                    "Summary stopped safely. Summarize selected restarts it. "
                    if self.job_kind == "summarize"
                    else "Formatting stopped safely. Format selected restarts it. "
                    if self.job_kind == "format"
                    else "AI cleanup stopped safely. Clean selected restarts it. "
                )
                + "Previous versions remain available."
                if self.job_kind in ("cleanup", "summarize", "format")
                else "Paused safely. Select this lecture and Resume selected to continue."
            )
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
            self.status.setText(
                (
                    "Transcript remains ready. "
                    if self.job_kind in ("cleanup", "summarize", "format")
                    else ""
                )
                + f"{self.job_kind.capitalize()} failed (exit {code}). "
                f"{self.output.strip() or self.process.errorString()}"
            )
        self._buttons()
        if cleanup_error:
            self.status.setText(self.status.text() + cleanup_error)
        if self.closing:
            self.close()

    def refresh(self) -> None:
        selected = self.selected_id()
        sessions: dict[str, Session] = {}
        errors = 0
        try:
            folders = list(self.store.lectures.iterdir()) if self.store.lectures.exists() else []
        except OSError as error:
            self.status.setText(f"Could not read the lecture library: {error}")
            self._buttons()
            return
        if folders:
            for folder in folders:
                if not folder.is_dir():
                    continue
                try:
                    session = self.store.load_session(folder.name)
                    if (
                        session.id != folder.name
                        or not isinstance(session.title, str)
                        or not isinstance(session.created_at, str)
                        or not isinstance(session.diagnostics, dict)
                    ):
                        raise ValueError("invalid session metadata")
                    sessions[session.id] = session
                except (OSError, ValueError, TypeError, KeyError, AttributeError):
                    errors += 1
        self.sessions = sessions
        target = selected
        if self.active_id is None:
            created = set(sessions) - self.before_ids
            if len(created) == 1:
                self.active_id = next(iter(created))
                target = self.active_id
        self.library.blockSignals(True)
        self.library.clear()
        for session in sorted(sessions.values(), key=lambda s: s.created_at, reverse=True):
            item = QListWidgetItem(f"{session.title}\n{session.status} · {session.created_at[:10]}")
            item.setData(Qt.ItemDataRole.UserRole, session.id)
            item.setToolTip(session.id)
            self.library.addItem(item)
            if session.id == target:
                self.library.setCurrentItem(item)
        self.library.blockSignals(False)
        self.show_selected()
        if self.active_id and self.job_kind == "transcription":
            checkpoint = self.store.checkpoint_path(self.active_id)
            if checkpoint.exists():
                try:
                    value = json.loads(checkpoint.read_text(encoding="utf-8"))
                    total = int(value["total_chunks"])
                    done = len(value["completed_chunks"])
                    self.progress.setRange(0, max(1, total))
                    self.progress.setValue(done)
                    self.progress.setFormat(f"{done} / {total} chunks")
                except (OSError, ValueError, KeyError, TypeError):
                    pass  # Atomic replacements can briefly be unavailable on Windows.
        if errors and not self.busy:
            self.status.setText(
                f"Skipped {errors} unreadable session(s). Their files were left intact."
            )
        self._buttons()

    def _buttons(self) -> None:
        for control in (
            self.import_button,
            self.models_button,
            self.ffmpeg_button,
            self.model,
            self.device,
            self.cleanup_model,
            self.cleanup_mode,
            self.cleanup_style,
            self.cleanup_device,
            self.format_style,
        ):
            control.setEnabled(not self.busy)
        self.pause_button.setEnabled(
            self.busy and self.stop_file is not None and not self.stop_file.exists()
        )
        session = self.sessions.get(self.selected_id() or "")
        self.resume_button.setEnabled(
            not self.busy and session is not None and session.status in ("interrupted", "failed")
        )
        completed = session is not None and session.status == "ready"
        edited = session is not None and session.edited_transcript is not None
        ai_ready = (
            session is not None
            and (self.store.session_dir(session.id) / "ai-transcript.json").is_file()
        )
        summary_ready = (
            session is not None
            and (self.store.session_dir(session.id) / "summary-transcript.json").is_file()
        )
        self.cleanup_button.setEnabled(
            not self.busy and completed and self.cleanup_style.currentText() != "off"
        )
        self.summary_button.setEnabled(not self.busy and completed)
        self.format_button.setEnabled(
            not self.busy and completed and self.format_style.currentData() != "off"
        )
        formatted_ready = (
            session is not None
            and (self.store.session_dir(session.id) / "formatted-transcript.json").is_file()
        )
        self.export_button.setEnabled(
            completed
            and (self.layer.currentText() != "Edited" or edited)
            and (self.layer.currentText() != "AI" or ai_ready)
            and (
                self.layer.currentText() != "Formatted"
                or (formatted_ready and self.export_format.currentText() != "srt")
            )
            and (
                self.layer.currentText() != "Summary"
                or (summary_ready and self.export_format.currentText() != "srt")
            )
        )
        self.edit_button.setEnabled(
            not self.busy
            and completed
            and self.layer.currentText() not in ("AI", "Summary", "Formatted")
            and ((self.layer.currentText() == "Edited") == edited)
        )
        self.history_button.setEnabled(edited)

    def show_selected(self, *_: object) -> None:
        session = self.sessions.get(self.selected_id() or "")
        if session is None:
            self.player.load(None)
            self.segment_starts = []
            self.transcript.clear()
            self.details.setText("Import a lecture or select one from the library.")
            self._buttons()
            return
        diag = session.diagnostics
        try:
            self.player.load(self.store.source_copy(session.id))
        except (OSError, ValueError, KeyError):
            self.player.load(None)
        self.segment_starts = []
        self.details.setText(
            f"{session.title} · {session.status}\nModel: {diag.get('model_id', 'unknown')} "
            f"· Device: {diag.get('actual_device', 'pending')}"
        )
        if session.status == "ready":
            try:
                transcript = self.store.load_transcript(
                    session.id, self.layer.currentText().lower()
                )
                text = "\n\n".join(
                    f"[{s.start:07.2f}–{s.end:07.2f}s]{' [?]' if s.uncertain else ''} "
                    f"{' '.join(s.text.split())}"
                    for s in transcript.segments
                )
                if self.layer.currentText() in ("AI", "Summary", "Formatted"):
                    text = "\n\n".join(s.text for s in transcript.segments)
                    records = (transcript.transformation or {}).get("blocks", [])
                    retained = sum(bool(record.get("used_source")) for record in records)
                    if self.layer.currentText() == "Formatted":
                        metadata = transcript.transformation or {}
                        styles = {
                            "prose": "Mostly prose",
                            "mixed": "Mixed",
                            "structured": "Mostly structured",
                        }
                        description = (
                            "\nFormatting: "
                            + styles.get(str(metadata.get("style")), "Unknown")
                            + " · source: "
                            + str(metadata.get("source_layer", "unknown")).upper()
                            + (
                                " · no AI pass"
                                if transcript.provenance.actual_device == "none"
                                else " · " + transcript.provenance.actual_device
                            )
                        )
                    else:
                        description = (
                            (
                                "\nSummary: "
                                if self.layer.currentText() == "Summary"
                                else "\nAI cleanup: "
                            )
                            + f"{transcript.provenance.model} · "
                            + transcript.provenance.actual_device
                            + " · source-block timing; review against Raw"
                        )
                    self.details.setText(
                        self.details.text()
                        + description
                        + (f" · {retained} block(s) used source after warnings" if retained else "")
                    )
                if self.layer.currentText() == "Formatted":
                    self.transcript.document().setMarkdown(
                        text, QTextDocument.MarkdownFeature.MarkdownNoHTML
                    )
                else:
                    self.transcript.setPlainText(text)
                self.segment_starts = (
                    []
                    if self.layer.currentText() in ("AI", "Summary", "Formatted")
                    else [s.start for s in transcript.segments]
                )
                if self.layer.currentText() == "Edited":
                    self.details.setText(
                        self.details.text()
                        + "\nEdited by user · original inference provenance retained"
                    )
            except (OSError, ValueError, TypeError, KeyError) as error:
                self.transcript.setPlainText(f"Could not read transcript: {error}")
        else:
            self.transcript.clear()
        self._buttons()
        self.player.seek_button.setEnabled(bool(self.segment_starts))

    def seek_selected_segment(self) -> None:
        index = self.transcript.textCursor().blockNumber() // 2
        if 0 <= index < len(self.segment_starts):
            self.player.seek(self.segment_starts[index])

    def find_text(self) -> None:
        query = self.search.text()
        if query and not self.transcript.find(query):
            self.transcript.moveCursor(QTextCursor.MoveOperation.Start)
            self.transcript.find(query)

    def edit_selected_segment(self) -> None:
        session_id = self.selected_id()
        if self.busy or session_id is None or not self.edit_button.isEnabled():
            return
        try:
            layer = self.layer.currentText().lower()
            expected = current_revision(self.store, session_id)
            base = load_revision(self.store, session_id).base_layer if expected else layer
            transcript = self.store.load_transcript(session_id, layer)
            index = self.transcript.textCursor().blockNumber() // 2
            if not 0 <= index < len(transcript.segments):
                return

            def commit(text: str, uncertain: bool) -> EditRevision:
                return save_segment_edit(
                    self.store,
                    session_id,
                    index,
                    text,
                    uncertain,
                    base_layer=base,
                    expected_revision=expected,
                )

            dialog = SegmentEditDialog(transcript.segments[index], commit)
            dialog.exec()
            if dialog.saved:
                self.sessions[session_id] = self.store.load_session(session_id)
                self.layer.setCurrentText("Edited")
                self.show_selected()
                self.status.setText("Edited revision saved. Raw and Balanced remain unchanged.")
        except (OSError, ValueError, TypeError, KeyError) as error:
            self.status.setText(f"Could not open edit: {error}")

    def show_history(self) -> None:
        session_id = self.selected_id()
        if session_id:
            try:
                RevisionHistoryDialog(revision_history(self.store, session_id)).exec()
            except (OSError, ValueError, TypeError, KeyError) as error:
                self.status.setText(f"Could not open history: {error}")

    def choose_export(self) -> None:
        session_id = self.selected_id()
        if not session_id:
            return
        fmt = self.export_format.currentText()
        suffix = {"markdown": "md", "text": "txt"}.get(fmt, fmt)
        file, _ = QFileDialog.getSaveFileName(
            self,
            "Export transcript",
            f"{session_id}.{self.layer.currentText().lower()}.{suffix}",
            f"{fmt} (*.{suffix})",
        )
        if file:
            try:
                path = write_export(
                    self.store,
                    session_id,
                    self.layer.currentText().lower(),
                    fmt,
                    out_path=Path(file),
                    overwrite=True,
                )
                self.status.setText(f"Exported: {path}")
            except (OSError, ValueError, RuntimeError, ExportError) as error:
                QMessageBox.warning(self, "Export failed", str(error))

    def closeEvent(self, event: QCloseEvent) -> None:
        self.player.player.stop()
        if self.busy:
            self.closing = True
            self.pause()
            event.ignore()
        else:
            event.accept()
