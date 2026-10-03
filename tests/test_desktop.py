"""Exercise the Qt workflow with real child processes; Qt remains optional."""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

from npu_scribe.desktop_editing import RevisionHistoryDialog, SegmentEditDialog  # noqa: E402
from npu_scribe.desktop_player import LecturePlayer, clock  # noqa: E402
from npu_scribe.desktop_ui import LectureWindow  # noqa: E402
from npu_scribe.editing import revision_history  # noqa: E402
from npu_scribe.models import Segment  # noqa: E402
from npu_scribe.storage import sha256_file  # noqa: E402


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

    from npu_scribe.ai_cleanup import DEFAULT_MODEL

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
from npu_scribe.ai_cleanup import cleanup_session
from npu_scribe.storage import SessionStore
args=sys.argv[1:]
store=SessionStore(Path(args[args.index('--data-dir')+1]))
session=args[args.index('cleanup')+1]
class Fixture:
    def generate(self, text, mode, style):
        return text.capitalize()+'.'
cleanup_session(store,session,Fixture(),mode='dictation',style='medium')
""")
    monkeypatch.setattr(
        "npu_scribe.desktop_ui.worker_command", lambda args: (sys.executable, [str(worker), *args])
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
    window.cleanup_style.setCurrentText("off")
    window.device.setCurrentText("GPU")
    window._save_settings()
    window.close()
    reopened = LectureWindow(tmp_path / "library")
    assert reopened.cleanup_style.currentText() == "off"
    assert reopened.device.currentText() == "GPU"
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
from npu_scribe.ai_cleanup import cleanup_session
from npu_scribe.storage import SessionStore
args=sys.argv[1:]
store=SessionStore(Path(args[args.index('--data-dir')+1]))
session=args[args.index('summarize')+1]
class Notes:
    def generate(self, text, mode, style):
        return '{"sections":[{"heading":"Synthetic transcript","sentences":[0]}]}' 
cleanup_session(store,session,Notes(),mode='summary')
""")
    monkeypatch.setattr(
        "npu_scribe.desktop_ui.worker_command", lambda args: (sys.executable, [str(worker), *args])
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
import npu_scribe.cli as cli
class Fixture:
    device='CPU'
    def generate(self, text, mode, style):
        return text.capitalize()+'.'
cli.make_model=lambda *args: Fixture()
raise SystemExit(cli.main(sys.argv[1:]))
""")
    monkeypatch.setattr(
        "npu_scribe.desktop_ui.worker_command", lambda args: (sys.executable, [str(worker), *args])
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
