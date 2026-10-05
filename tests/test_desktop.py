"""Exercise the Qt workflow with real child processes; Qt remains optional."""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

from audio_transcriber.desktop_editing import RevisionHistoryDialog, SegmentEditDialog  # noqa: E402
from audio_transcriber.desktop_player import LecturePlayer, clock  # noqa: E402
from audio_transcriber.desktop_ui import LectureWindow  # noqa: E402
from audio_transcriber.editing import revision_history  # noqa: E402
from audio_transcriber.models import Segment  # noqa: E402
from audio_transcriber.storage import sha256_file  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path):
    result = LectureWindow(tmp_path / "library", tmp_path / "models")
    # The mock is a test fixture, never offered in the production model selector.
    result.model.addItem("Test fixture", "mock")
    result.model.setCurrentIndex(result.model.findData("mock"))
    result.cleanup_style.setCurrentText("off")
    result.format_style.setCurrentIndex(result.format_style.findData("off"))
    yield result
    if result.busy:
        result.pause()
        wait_finished(app, result)
    result.close()


def wait_finished(app, window):
    deadline = time.monotonic() + 30
    while window.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert not window.busy, window.output


def wait_seekable(app, player):
    deadline = time.monotonic() + 10
    while not player.player.isSeekable() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert player.player.isSeekable(), player.message.text()


def test_player_local_media_seek_clamp_and_no_reload(app, three_second_wav):
    player = LecturePlayer()
    player.audio.setMuted(True)
    player.load(three_second_wav)
    wait_seekable(app, player)
    assert 2900 <= player.player.duration() <= 3100
    player.seek(1.2)
    assert player.player.position() == 1200
    player.load(three_second_wav)
    assert player.player.position() == 1200
    player.seek(-1)
    assert player.player.position() == 0
    player.seek(100)
    assert player.player.position() == player.player.duration()
    player.load(None)
    assert not player.play_button.isEnabled()
    assert clock(3_661_999) == "01:01:01"
    player.close()


def test_slider_keyboard_and_accessibility_value_seek(app, three_second_wav):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    player = LecturePlayer()
    player.audio.setMuted(True)
    player.load(three_second_wav)
    wait_seekable(app, player)
    # Accessibility providers change the slider value without dragging it.
    player.slider.setValue(1200)
    assert player.player.position() == 1200
    QTest.keyClick(player.slider, Qt.Key.Key_Right)
    assert player.player.position() == 1200 + player.slider.singleStep()
    player.close()


def test_transcript_seek_uses_preserved_source(app, window, three_second_wav, monkeypatch):
    window.start_import(three_second_wav)
    wait_finished(app, window)
    wait_seekable(app, window.player)
    session = next(iter(window.sessions.values()))
    assert window.player.source == window.store.source_copy(session.id).resolve()
    recorded = []
    monkeypatch.setattr(window.player, "seek", recorded.append)
    window.seek_selected_segment()
    assert recorded == [window.segment_starts[0]]
    source = window.player.source
    window.layer.setCurrentText("Balanced")
    assert window.player.source == source


def test_import_search_layers_export_and_reopen(
    app, window, three_second_wav, tmp_path, monkeypatch
):
    window.start_import(three_second_wav)
    assert window.busy
    assert not window.import_button.isEnabled()
    wait_finished(app, window)
    assert len(window.sessions) == 1
    session = next(iter(window.sessions.values()))
    assert session.status == "ready", window.status.text()
    assert window.transcript.toPlainText()
    window.layer.setCurrentText("Balanced")
    text = window.transcript.toPlainText()
    window.search.setText(text.split()[-1])
    window.find_text()
    assert window.transcript.textCursor().hasSelection()
    destination = tmp_path / "lecture.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(destination), ""))
    window.export_format.setCurrentText("json")
    window.choose_export()
    assert '"layer": "balanced"' in destination.read_text()
    reopened = LectureWindow(window.store.data_dir)
    assert len(reopened.sessions) == 1
    assert reopened.model_root == window.model_root
    reopened.library.setCurrentRow(0)
    assert reopened.transcript.toPlainText()
    reopened.close()


def test_pause_and_resume_in_child_process(app, window, three_second_wav):
    window.start_import(three_second_wav)
    window.pause()
    wait_finished(app, window)
    session = next(iter(window.sessions.values()))
    assert session.status == "interrupted", window.status.text()
    assert window.store.checkpoint_path(session.id).exists()
    assert window.resume_button.isEnabled()
    assert window.progress.maximum() > 0
    window.resume_selected()
    wait_finished(app, window)
    session = window.store.load_session(session.id)
    assert session.status == "ready", window.status.text()
    assert not window.store.checkpoint_path(session.id).exists()
    assert window.transcript.toPlainText()


def test_close_waits_for_safe_pause(app, window, three_second_wav):
    window.show()
    window.start_import(three_second_wav)
    window.close()
    assert window.closing
    wait_finished(app, window)
    assert not window.isVisible()
    assert next(iter(window.sessions.values())).status == "interrupted"


def test_invalid_model_does_not_start(app, window, three_second_wav):
    window.model.setCurrentIndex(0)
    window.start_import(three_second_wav)
    assert not window.busy
    assert "Choose" in window.status.text()
    window.model.setCurrentIndex(1)
    window.start_import(three_second_wav)
    wait_finished(app, window)
    assert "failed" in window.status.text()
    assert not window.sessions
    assert window.import_button.isEnabled()


def test_bad_metadata_and_settings_are_visible(app, tmp_path):
    root = tmp_path / "library"
    folder = root / "lectures" / "broken"
    folder.mkdir(parents=True)
    (folder / "session.json").write_text("[]")
    (root / "desktop-settings.json").write_text("[]")
    result = LectureWindow(root)
    assert "Skipped 1" in result.status.text()
    assert not result.sessions
    assert (folder / "session.json").read_text() == "[]"
    result.close()


def test_gui_edit_save_reopen_history_and_export(
    app, window, three_second_wav, tmp_path, monkeypatch
):
    window.start_import(three_second_wav)
    wait_finished(app, window)
    session_id = window.selected_id()
    raw = window.store.session_dir(session_id) / "raw-transcript.json"
    raw_hash = sha256_file(raw)

    def edit_dialog(dialog):
        dialog.text.setPlainText("Manual correction for the GUI test.")
        dialog.uncertain.setChecked(True)
        dialog.save()
        return dialog.result()

    monkeypatch.setattr(SegmentEditDialog, "exec", edit_dialog)
    window.edit_selected_segment()
    assert window.layer.currentText() == "Edited"
    assert "Edited by user" in window.details.text()
    assert "Manual correction" in window.transcript.toPlainText()
    assert "[?]" in window.transcript.toPlainText()
    assert sha256_file(raw) == raw_hash
    window.layer.setCurrentText("Raw")
    assert not window.edit_button.isEnabled()
    window.layer.setCurrentText("Edited")
    assert window.edit_button.isEnabled()
    history = RevisionHistoryDialog(revision_history(window.store, session_id))
    assert history.preview.isReadOnly()
    assert "Manual correction" in history.preview.toPlainText()
    history.close()
    reopened = LectureWindow(window.store.data_dir)
    reopened.library.setCurrentRow(0)
    reopened.layer.setCurrentText("Edited")
    assert "Manual correction" in reopened.transcript.toPlainText()
    destination = tmp_path / "edited.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(destination), ""))
    reopened.export_format.setCurrentText("json")
    reopened.choose_export()
    assert '"edit_provenance"' in destination.read_text()
    reopened.close()


def test_edit_dialog_keeps_draft_when_save_fails(app):
    def failed_commit(text, uncertain):
        raise PermissionError("synthetic write denial")

    dialog = SegmentEditDialog(Segment(0, 1, "original"), failed_commit)
    dialog.show()
    dialog.text.setPlainText("Keep this unsaved draft")
    dialog.save()
    assert dialog.isVisible()
    assert dialog.saved is None
    assert dialog.text.toPlainText() == "Keep this unsaved draft"
    assert "not saved" in dialog.error.text()
    dialog.reject()


def test_desktop_ai_cleanup_worker_review_export_and_reopen(
    app, window, three_second_wav, tmp_path, monkeypatch
):
    import sys

    from audio_transcriber.ai_cleanup import DEFAULT_MODEL

    assert window.model.findData(DEFAULT_MODEL) == -1
    assert window.cleanup_model.findData(DEFAULT_MODEL) >= 0
    window.start_import(three_second_wav)
    wait_finished(app, window)
    session = next(iter(window.sessions.values()))
    before = sha256_file(window.store.session_dir(session.id) / "raw-transcript.json")
    worker = tmp_path / "fixture-cleanup-worker.py"
    worker.write_text("""
import sys
from pathlib import Path
from audio_transcriber.ai_cleanup import cleanup_session
from audio_transcriber.storage import SessionStore
args=sys.argv[1:]
store=SessionStore(Path(args[args.index('--data-dir')+1]))
session=args[args.index('cleanup')+1]
class Fixture:
    def generate(self, text, mode, style):
        return text.capitalize()+'.'
cleanup_session(store,session,Fixture(),mode='dictation',style='medium')
""")
    monkeypatch.setattr(
        "audio_transcriber.desktop_ui.worker_command",
        lambda args: (sys.executable, [str(worker), *args]),
    )
    window.cleanup_mode.setCurrentIndex(window.cleanup_mode.findData("dictation"))
    window.cleanup_style.setCurrentText("medium")
    window.cleanup_device.setCurrentText("NPU")
    window.start_cleanup()
    assert window.busy
    wait_finished(app, window)
    assert window.layer.currentText() == "AI"
    assert window.transcript.toPlainText() == "Synthetic transcript."
    assert not window.edit_button.isEnabled()
    assert not window.player.seek_button.isEnabled()
    assert window.export_button.isEnabled()
    assert before == sha256_file(window.store.session_dir(session.id) / "raw-transcript.json")
    destination = tmp_path / "ai-export.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(destination), ""))
    window.export_format.setCurrentText("json")
    window.choose_export()
    assert '"transformation"' in destination.read_text()
    reopened = LectureWindow(window.store.data_dir)
    assert reopened.cleanup_mode.currentData() == "dictation"
    assert reopened.cleanup_style.currentText() == "medium"
    assert reopened.cleanup_device.currentText() == "NPU"
    reopened.library.setCurrentRow(0)
    reopened.layer.setCurrentText("AI")
    assert reopened.transcript.toPlainText() == "Synthetic transcript."
    reopened.close()


def test_automatic_cleanup_failure_preserves_raw(app, window, three_second_wav):
    window.cleanup_style.setCurrentText("light")
    window.start_import(three_second_wav)
    wait_finished(app, window)
    session = next(iter(window.sessions.values()))
    assert session.status == "ready"
    assert "Transcript remains ready" in window.status.text()
    assert "not installed" in window.status.text()
    assert window.layer.currentText() == "Raw"
    assert window.export_button.isEnabled()


def test_cleanup_defaults_and_off_persist(app, tmp_path):
    window = LectureWindow(tmp_path / "library")
    assert window.cleanup_style.currentText() == "light"
    assert window.cleanup_device.currentText() == "AUTO"
    assert window.device.currentText() == "CPU"
    assert window.format_style.currentData() == "structured"
    window.open_dictation()
    assert window.dictation_window.cleanup.currentText() == "medium"
    window.dictation_window.close()
    window.cleanup_style.setCurrentText("off")
    window.format_style.setCurrentIndex(window.format_style.findData("off"))
    window.device.setCurrentText("GPU")
    window._save_settings()
    window.close()
    reopened = LectureWindow(tmp_path / "library")
    assert reopened.cleanup_style.currentText() == "off"
    assert reopened.device.currentText() == "GPU"
    assert reopened.format_style.currentData() == "off"
    reopened.close()


def test_desktop_summary_keeps_ai_and_disallows_subtitles(
    app, window, three_second_wav, tmp_path, monkeypatch
):
    import sys

    window.start_import(three_second_wav)
    wait_finished(app, window)
    session = next(iter(window.sessions.values()))
    worker = tmp_path / "notes-worker.py"
    worker.write_text("""
import sys
from pathlib import Path
from audio_transcriber.ai_cleanup import cleanup_session
from audio_transcriber.storage import SessionStore
args=sys.argv[1:]
store=SessionStore(Path(args[args.index('--data-dir')+1]))
session=args[args.index('summarize')+1]
class Notes:
    def generate(self, text, mode, style):
        return '{"sections":[{"heading":"Synthetic transcript","sentences":[0]}]}' 
cleanup_session(store,session,Notes(),mode='summary')
""")
    monkeypatch.setattr(
        "audio_transcriber.desktop_ui.worker_command",
        lambda args: (sys.executable, [str(worker), *args]),
    )
    window.start_summary()
    wait_finished(app, window)
    assert window.layer.currentText() == "Summary"
    assert "## Synthetic transcript" in window.transcript.toPlainText()
    assert window.summary_button.isEnabled()
    assert not window.edit_button.isEnabled()
    assert not window.player.seek_button.isEnabled()
    window.export_format.setCurrentText("srt")
    assert not window.export_button.isEnabled()
    window.export_format.setCurrentText("markdown")
    assert window.export_button.isEnabled()
    assert window.store.load_transcript(session.id, "raw").text == "synthetic transcript"


def test_automatic_cleanup_success_after_import(
    app, window, three_second_wav, tmp_path, monkeypatch
):
    import sys

    worker = tmp_path / "auto-worker.py"
    worker.write_text("""
import sys
import audio_transcriber.cli as cli
class Fixture:
    device='CPU'
    def generate(self, text, mode, style):
        return text.capitalize()+'.'
cli.make_model=lambda *args: Fixture()
raise SystemExit(cli.main(sys.argv[1:]))
""")
    monkeypatch.setattr(
        "audio_transcriber.desktop_ui.worker_command",
        lambda args: (sys.executable, [str(worker), *args]),
    )
    window.cleanup_style.setCurrentText("medium")
    window.start_import(three_second_wav)
    wait_finished(app, window)
    session = next(iter(window.sessions.values()))
    assert window.layer.currentText() == "AI"
    assert window.transcript.toPlainText() == "Synthetic transcript."
    assert window.store.load_transcript(session.id, "ai").transformation["style"] == "medium"
    assert window.store.load_transcript(session.id, "raw").text == "synthetic transcript"
    window.cleanup_style.setCurrentText("off")
    assert not window.cleanup_button.isEnabled()
    assert window.summary_button.isEnabled()


def test_job_stays_busy_until_completion_is_handled(app, window, three_second_wav):
    # Hold completion delivery to exercise a worker exit before the UI updates.
    window.process.finished.disconnect(window._finished)
    try:
        window.start_import(three_second_wav)
        assert window.process.waitForFinished(10_000), window.output
        assert window.busy
        assert not window.import_button.isEnabled()
    finally:
        window.process.finished.connect(window._finished)
        window._finished(window.process.exitCode(), window.process.exitStatus())
    assert not window.busy
    assert window.import_button.isEnabled()
    assert window.layer.currentText() == "Raw"
    assert "synthetic transcript" in window.transcript.toPlainText()


def test_pause_at_speech_completion_does_not_start_cleanup(app, window, three_second_wav):
    from PySide6.QtCore import QProcess

    window.start_import(three_second_wav)
    wait_finished(app, window)
    window.cleanup_style.setCurrentText("light")
    window.job_kind = "transcription"
    window.stop_file.touch()
    window._finished(0, QProcess.ExitStatus.NormalExit)
    assert not window.busy
    session = next(iter(window.sessions.values()))
    assert not (window.store.session_dir(session.id) / "ai-transcript.json").exists()


def test_automatic_prose_formatting_with_cleanup_off(app, window, three_second_wav):
    window.format_style.setCurrentIndex(window.format_style.findData("prose"))
    window.start_import(three_second_wav)
    wait_finished(app, window)
    session = next(iter(window.sessions.values()))
    assert window.layer.currentText() == "Formatted"
    assert window.transcript.toPlainText() == "synthetic transcript"
    assert (
        window.store.load_transcript(session.id, "formatted").transformation["source_layer"]
        == "raw"
    )
    assert not window.edit_button.isEnabled()
    assert not window.player.seek_button.isEnabled()
    window.export_format.setCurrentText("srt")
    assert not window.export_button.isEnabled()
    window.export_format.setCurrentText("markdown")
    assert window.export_button.isEnabled()


def test_desktop_cleanup_then_format_and_rerun_keep_sources(
    app, window, three_second_wav, tmp_path, monkeypatch
):
    import sys

    worker = tmp_path / "cleanup-layout-worker.py"
    worker.write_text("""
import json, sys
import audio_transcriber.cli as cli
class Fixture:
    device='CPU'
    def generate(self, text, mode, style):
        if mode == 'format':
            return json.dumps({'blocks':[{'kind':'bullets','passages':[0]}]})
        return text.capitalize()+'.'
cli.make_model=lambda *args: Fixture()
raise SystemExit(cli.main(sys.argv[1:]))
""")
    monkeypatch.setattr(
        "audio_transcriber.desktop_ui.worker_command",
        lambda args: (sys.executable, [str(worker), *args]),
    )
    window.cleanup_style.setCurrentText("light")
    window.format_style.setCurrentIndex(window.format_style.findData("mixed"))
    window.start_import(three_second_wav)
    wait_finished(app, window)
    session = next(iter(window.sessions.values()))
    output = window.store.load_transcript(session.id, "formatted")
    assert output.text == "- Synthetic transcript."
    assert output.transformation["source_layer"] == "ai"
    assert window.layer.currentText() == "Formatted"
    assert "Synthetic transcript." in window.transcript.toPlainText()
    directory = window.store.session_dir(session.id)
    hashes = {layer: sha256_file(directory / f"{layer}-transcript.json") for layer in ("raw", "ai")}
    window.layer.setCurrentText("AI")
    window.format_style.setCurrentIndex(window.format_style.findData("prose"))
    window.start_formatting()
    wait_finished(app, window)
    assert len(list((directory / "formatting-history").glob("*.json"))) == 2
    assert all(
        sha256_file(directory / f"{layer}-transcript.json") == digest
        for layer, digest in hashes.items()
    )


@pytest.fixture
def dictation(window):
    window.open_dictation()
    result = window.dictation_window
    result.model.setCurrentIndex(result.model.findData("mock"))
    result.cleanup.setCurrentText("off")
    yield result
    if result.busy:
        result.cancel()
        wait_finished(QApplication.instance(), result)
    result.close()


def prepare_dictation(dictation, wav):
    import uuid
    from datetime import UTC, datetime

    dictation.ident = uuid.uuid4().hex
    dictation.job = dictation.root / "jobs" / dictation.ident
    dictation.job.mkdir(parents=True)
    dictation.created_at = datetime.now(UTC).isoformat()
    dictation.cancelled = False
    dictation._start_worker(wav)


def test_dictation_pipeline_saves_history_before_insertion(
    app, window, dictation, three_second_wav
):
    from audio_transcriber.insertion import FocusTarget, InsertResult

    class Native:
        def insert(self, text, target, allowed):
            assert allowed()
            assert dictation.history.records()[0]["text"] == text
            return InsertResult(True, text)

    dictation.native = Native()
    dictation.intended = FocusTarget(1, 2, "Test", True)
    prepare_dictation(dictation, three_second_wav)
    assert window.busy
    assert not window.import_button.isEnabled()
    wait_finished(app, dictation)
    assert "input sent" in dictation.status.text()
    assert dictation.text.toPlainText()
    record = dictation.history.records()[0]
    assert record["raw"] == dictation.text.toPlainText()
    assert dictation.store.load_transcript(record["session_id"], "formatted").text == record["text"]
    assert not window.sessions  # Dictation has its own store, outside the file library.
    assert window.import_button.isEnabled()


def test_dictation_focus_change_recovers_without_insertion(app, dictation, three_second_wav):
    from audio_transcriber.insertion import FocusTarget, InsertResult

    class Native:
        def insert(self, text, target, allowed):
            return InsertResult(False, text, "Focus changed; text was saved instead.")

    dictation.native = Native()
    dictation.intended = FocusTarget(1, 2, "Test", True)
    prepare_dictation(dictation, three_second_wav)
    wait_finished(app, dictation)
    assert "Focus changed" in dictation.status.text()
    assert dictation.text.toPlainText() == dictation.history.records()[0]["text"]


def test_dictation_failed_cleanup_keeps_raw_and_skips_insertion(app, dictation, three_second_wav):
    class Native:
        def insert(self, *args):
            raise AssertionError("A failed job must not insert text")

    dictation.native = Native()
    dictation.cleanup.setCurrentText(
        "light"
    )  # Model is deliberately absent from this test library.
    prepare_dictation(dictation, three_second_wav)
    wait_finished(app, dictation)
    assert "Processing failed" in dictation.status.text()
    record = dictation.history.records()[0]
    assert record["status"] == "failed"
    assert record["raw"] and record["text"] == record["raw"]


def test_dictation_history_write_failure_skips_insertion(
    app, dictation, three_second_wav, monkeypatch
):
    class Native:
        def insert(self, *args):
            raise AssertionError("Unsaved text must not be inserted")

    def fail(record):
        raise OSError("disk unavailable")

    monkeypatch.setattr(dictation.history, "save", fail)
    dictation.native = Native()
    prepare_dictation(dictation, three_second_wav)
    wait_finished(app, dictation)
    assert "insertion skipped" in dictation.status.text()
    assert dictation.text.toPlainText()
    assert dictation.copy.isEnabled()


def test_dictation_toggle_hold_and_repeat_behavior(dictation, monkeypatch):
    calls = []
    shortcut = type("Shortcut", (), {"enabled": True, "released": lambda self: True})()
    dictation.shortcut = shortcut
    monkeypatch.setattr(
        dictation, "start_recording", lambda insert: calls.append(("start", insert))
    )
    monkeypatch.setattr(dictation, "stop_recording", lambda: calls.append(("stop",)))
    dictation.activate_shortcut()
    dictation.state = "preparing"
    dictation.activate_shortcut()
    assert calls == [("start", True)]
    dictation.state = "recording"
    dictation.activate_shortcut()
    assert calls[-1] == ("stop",)
    calls.clear()
    dictation.mode.setCurrentText("Hold to talk")
    dictation.state = "idle"
    dictation.activate_shortcut()
    assert dictation.holding
    dictation.state = "recording"
    dictation.started = time.monotonic()
    dictation.activate_shortcut()  # Repeated key-down is ignored in hold mode.
    dictation._tick()  # Release ends it.
    assert calls == [("start", True), ("stop",)]
    dictation.state = "idle"
    dictation.shortcut = None


def test_dictation_recording_limit_and_cancel(dictation, monkeypatch):
    stopped = []
    monkeypatch.setattr(dictation.mic, "stop", lambda: stopped.append(True))
    dictation._state("recording")
    dictation.cancel()
    assert stopped and not dictation.busy
    assert "cancelled" in dictation.status.text()
    calls = []
    monkeypatch.setattr(dictation, "stop_recording", lambda: calls.append(True))
    dictation.state = "recording"
    dictation.started = time.monotonic() - 121
    dictation._tick()
    assert calls == [True]
    dictation.state = "idle"


def test_dictation_normalization_then_worker(app, dictation, three_second_wav):
    import uuid
    import wave
    from datetime import UTC, datetime

    dictation.ident = uuid.uuid4().hex
    dictation.created_at = datetime.now(UTC).isoformat()
    dictation.job = dictation.root / "jobs" / dictation.ident
    dictation.job.mkdir(parents=True)
    with wave.open(str(three_second_wav), "rb") as wav:
        (dictation.job / "capture.pcm").write_bytes(b"\x00\x10" * wav.getnframes())
    dictation.mic.stop = lambda: (16000, 1, "int16")
    dictation._state("recording")
    dictation.stop_recording()
    wait_finished(app, dictation)
    assert dictation.history.records()[0]["status"] == "ready"
    assert not (dictation.job / "capture.pcm").exists()
    assert (dictation.job / "recording.wav").is_file()


def test_dictation_settings_restore_without_enabling_shortcut(window, dictation):
    from audio_transcriber.desktop_dictation import DictationWindow

    dictation.hotkey_text.setText("Ctrl+Shift+F9")
    dictation.mode.setCurrentText("Hold to talk")
    dictation.device.setCurrentText("GPU")
    dictation._save_settings()
    restored = DictationWindow(window)
    assert restored.hotkey_text.text() == "Ctrl+Shift+F9"
    assert restored.mode.currentText() == "Hold to talk"
    assert restored.device.currentText() == "GPU"
    assert restored.cleanup.currentText() == "off"
    assert not restored.enable.isChecked()
    restored.close()


def test_dictation_close_cancels_worker_without_destroying_it(
    app, window, dictation, three_second_wav
):
    prepare_dictation(dictation, three_second_wav)
    window.close()
    assert dictation.closing and dictation.cancelled
    assert (dictation.job / "stop").is_file()
    wait_finished(app, dictation)
    app.processEvents()
    assert not window.busy
    assert dictation.history.records()[0]["status"] == "cancelled"


def test_dictation_worker_requires_result_identifier(dictation):
    import uuid

    from PySide6.QtCore import QProcess

    dictation.ident = uuid.uuid4().hex
    dictation._state("processing")
    dictation._finished(0, QProcess.ExitStatus.NormalExit)
    assert "no session identifier" in dictation.status.text()
    assert dictation.history.records()[0]["status"] == "failed"


def test_dictation_cancellation_while_preparing_does_not_capture(app, dictation, monkeypatch):
    from audio_transcriber.insertion import FocusTarget

    captured = []
    monkeypatch.setattr(dictation, "_begin_capture", lambda: captured.append(True))
    dictation._state("preparing")
    dictation._task(lambda: FocusTarget(1, 2, "Test", True), dictation._target_ready)
    dictation.cancel()
    wait_finished(app, dictation)
    assert not captured


def test_microphone_polling_reports_device_error(dictation):
    from PySide6.QtMultimedia import QtAudio

    class BrokenSource:
        def error(self):
            return QtAudio.Error.IOError

        def stop(self):
            pass

        def deleteLater(self):
            pass

    dictation.mic.source = BrokenSource()
    dictation._state("recording")
    dictation._tick()
    assert not dictation.busy
    assert "stopped unexpectedly" in dictation.status.text()


def test_native_shortcut_accepts_both_qt_windows_event_routes(app):
    import ctypes
    from ctypes import wintypes

    from PySide6.QtCore import QByteArray

    from audio_transcriber.desktop_dictation import Shortcut

    called = []
    shortcut = Shortcut(None, lambda: called.append(True))
    shortcut.enabled = True
    msg = wintypes.MSG()
    msg.message = 0x0312
    msg.wParam = shortcut.IDENT
    for route in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
        assert shortcut.nativeEventFilter(QByteArray(route), ctypes.addressof(msg)) == (True, 0)
        app.processEvents()
    assert called == [True, True]
    msg.wParam += 1
    assert shortcut.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg)) == (False, 0)
