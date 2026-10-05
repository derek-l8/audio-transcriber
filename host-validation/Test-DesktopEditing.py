"""Check synthetic manual edits in an isolated copy of a completed lecture."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_library", type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

    from audio_transcriber.desktop_editing import RevisionHistoryDialog, SegmentEditDialog
    from audio_transcriber.desktop_ui import LectureWindow
    from audio_transcriber.editing import revision_history
    from audio_transcriber.storage import SessionStore, atomic_json, sha256_file

    source = SessionStore(args.source_library)
    candidates = [
        p.name
        for p in source.lectures.iterdir()
        if p.is_dir() and source.load_session(p.name).status == "ready"
    ]
    if not candidates:
        raise RuntimeError("Provide a completed lecture library")
    session_id = candidates[0]
    target = SessionStore(args.data_dir)
    destination = target.lectures / session_id
    if destination.exists():
        raise RuntimeError("Use a new validation directory")
    shutil.copytree(source.session_dir(session_id), destination)
    if target.load_session(session_id).edited_transcript is not None:
        raise RuntimeError("Use a source fixture without existing edits")
    paths = [destination / f"{layer}-transcript.json" for layer in ("raw", "balanced")]
    hashes = [sha256_file(path) for path in paths]
    app = QApplication([])
    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
    if font.is_file():
        QFontDatabase.addApplicationFont(str(font))
        app.setFont(QFont("Segoe UI", 10))

    def error_dialog(parent, title, message):
        raise RuntimeError(f"{title}: {message}")

    QMessageBox.warning = error_dialog
    window = LectureWindow(target.data_dir)
    window.player.audio.setMuted(True)
    window.library.setCurrentRow(0)
    window.layer.setCurrentText("Balanced")
    window.show()
    app.processEvents()
    edits = [0]

    def synthetic_edit(dialog):
        edits[0] += 1
        dialog.text.setPlainText(dialog.text.toPlainText() + f" [validation edit {edits[0]}]")
        dialog.uncertain.setChecked(True)
        dialog.save()
        if dialog.saved is None:
            raise RuntimeError(dialog.error.text())
        return dialog.result()

    SegmentEditDialog.exec = synthetic_edit
    window.edit_selected_segment()
    window.edit_selected_segment()
    records = revision_history(target, session_id)
    if len(records) != 2 or "validation edit 2" not in window.transcript.toPlainText():
        raise RuntimeError("Edited revision did not populate the window")
    if [sha256_file(path) for path in paths] != hashes:
        raise RuntimeError("Original transcript layers changed")
    original = target.load_transcript(session_id, "balanced")
    edited = target.load_transcript(session_id, "edited")
    timestamps_match = [(s.start, s.end) for s in original.segments] == [
        (s.start, s.end) for s in edited.segments
    ]
    if not timestamps_match:
        raise RuntimeError("Editing changed timestamps")
    history = RevisionHistoryDialog(records)
    history.list.setCurrentRow(1)
    if "validation edit 2" in history.preview.toPlainText():
        raise RuntimeError("Previous revision was overwritten")
    history.close()
    exports = []
    for fmt in ("text", "markdown", "srt", "json"):
        window.export_format.setCurrentText(fmt)
        output = target.data_dir / f"edited-smoke.{fmt}"
        QFileDialog.getSaveFileName = lambda *args, path=output: (str(path), "")
        window.choose_export()
        if not output.exists() or not output.stat().st_size:
            raise RuntimeError(f"Edited {fmt} export failed")
        exports.append({"format": fmt, "bytes": output.stat().st_size})
    app.processEvents()
    window.grab().save(str(target.data_dir / "edited-preview.png"))
    window.close()
    reopened = LectureWindow(target.data_dir)
    reopened.player.audio.setMuted(True)
    reopened.library.setCurrentRow(0)
    reopened.layer.setCurrentText("Edited")
    if "validation edit 2" not in reopened.transcript.toPlainText():
        raise RuntimeError("Edited version did not survive reopening")
    reopened.close()
    payload = json.loads((target.data_dir / "edited-smoke.json").read_text(encoding="utf-8"))
    report = {
        "scope": "Synthetic edit inputs in a copy of the completed full CS lecture; "
        "no accuracy correction or listening audit",
        "segments": len(edited.segments),
        "revisions": len(records),
        "raw_balanced_unchanged": True,
        "timestamps_unchanged": timestamps_match,
        "history_preserved": True,
        "reopened_edited_text": True,
        "json_edit_revision_matches": payload["edit_provenance"]["revision"] == records[0].revision,
        "exports": exports,
    }
    atomic_json(args.report, report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
