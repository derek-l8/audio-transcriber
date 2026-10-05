"""Local Qt smoke: real child inference, safe pause/resume, review and exports.

Provide a public multi-chunk lecture file and an already verified model folder.
This performs no downloads. Screenshots and transcripts belong in ignored data.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("media", type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--model-root", required=True, type=Path)
    parser.add_argument("--model", default="whisper-tiny.en-int4-ov")
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--single-run",
        action="store_true",
        help="skip the second uninterrupted inference for a full lecture",
    )
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--review-session", default=None)
    parser.add_argument(
        "--worker-executable",
        type=Path,
        default=None,
        help="drive an existing frozen CLI worker from the source Qt UI",
    )
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

    from audio_transcriber.desktop_ui import LectureWindow
    from audio_transcriber.storage import atomic_json

    if args.worker_executable is not None:
        from audio_transcriber import desktop_ui

        worker = args.worker_executable.resolve()
        if not worker.is_file():
            raise RuntimeError("Frozen worker executable does not exist")
        desktop_ui.worker_command = lambda arguments: (str(worker), arguments)

    app = QApplication([])

    def fail_dialog(parent, title, message):
        raise RuntimeError(f"{title}: {message}")

    QMessageBox.warning = fail_dialog
    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
    if font.is_file():
        QFontDatabase.addApplicationFont(str(font))
        app.setFont(QFont("Segoe UI", 10))
    window = LectureWindow(args.data_dir, args.model_root, args.ffmpeg)
    window.player.audio.setMuted(True)
    if window.sessions and not args.review_session:
        raise RuntimeError("Use an empty data directory for this smoke test")
    index = window.model.findData(args.model)
    if index < 1:
        raise RuntimeError("Choose a manifest-approved real model")
    window.model.setCurrentIndex(index)
    window.show()
    heartbeats = [0]
    timer = QTimer()
    timer.setInterval(25)
    timer.timeout.connect(lambda: heartbeats.__setitem__(0, heartbeats[0] + 1))
    timer.start()
    started = time.monotonic()

    def wait(pause_after_first: bool = False) -> None:
        deadline = time.monotonic() + args.timeout_seconds
        requested = False
        while window.busy and time.monotonic() < deadline:
            app.processEvents()
            if pause_after_first and not requested:
                folders = list(window.store.lectures.glob("*/checkpoint.json"))
                for file in folders:
                    value = json.loads(file.read_text(encoding="utf-8"))
                    if 0 < len(value["completed_chunks"]) < value["total_chunks"]:
                        window.pause()
                        requested = True
            time.sleep(0.01)
        app.processEvents()
        if window.busy:
            window.pause()
            raise RuntimeError("Desktop worker exceeded the smoke deadline")
        if pause_after_first and not requested:
            raise RuntimeError("No mid-session pause observed; use a longer lecture")

    committed = None
    if args.review_session:
        resumed = window.store.load_session(args.review_session)
        for row in range(window.library.count()):
            window.library.setCurrentRow(row)
            if window.selected_id() == resumed.id:
                break
    else:
        window.start_import(args.media)
        wait(pause_after_first=True)
        paused = next(iter(window.sessions.values()))
        if paused.status != "interrupted":
            raise RuntimeError(window.status.text())
        checkpoint = json.loads(window.store.checkpoint_path(paused.id).read_text(encoding="utf-8"))
        committed = len(checkpoint["completed_chunks"])
        window.resume_selected()
        wait()
        resumed = window.store.load_session(paused.id)
    if resumed.status != "ready" or not window.transcript.toPlainText():
        raise RuntimeError(window.status.text())
    deadline = time.monotonic() + 15
    while not window.player.player.isSeekable() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    if not window.player.player.isSeekable():
        raise RuntimeError(window.player.message.text())
    duration_ms = window.player.player.duration()
    window.player.seek(duration_ms / 2000)
    target_ms = window.player.player.position()
    window.player.toggle()
    deadline = time.monotonic() + 5
    while window.player.player.position() <= target_ms + 100 and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    advanced = window.player.player.position() > target_ms + 100
    window.player.player.pause()
    if not advanced:
        raise RuntimeError("Muted playback did not advance after seeking")
    cursor = window.transcript.textCursor()
    cursor.setPosition(0)
    window.transcript.setTextCursor(cursor)
    window.seek_selected_segment()
    if abs(window.player.player.position() - round(window.segment_starts[0] * 1000)) > 100:
        raise RuntimeError("Transcript segment seek failed")
    exports: list[dict[str, object]] = []
    for layer in ("Raw", "Balanced"):
        window.layer.setCurrentText(layer)
        for fmt in ("text", "markdown", "srt", "json"):
            window.export_format.setCurrentText(fmt)
            destination = args.data_dir / f"smoke.{layer.lower()}.{fmt}"
            QFileDialog.getSaveFileName = lambda *a, dest=destination: (str(dest), "")
            window.choose_export()
            if not destination.exists() or not destination.stat().st_size:
                raise RuntimeError(f"Desktop export failed: {layer}/{fmt}")
            exports.append(
                {"layer": layer.lower(), "format": fmt, "bytes": destination.stat().st_size}
            )
    window.search.setText(window.store.load_transcript(resumed.id, "balanced").text.split()[0])
    window.find_text()
    if not window.transcript.textCursor().hasSelection():
        raise RuntimeError("Transcript search failed")
    window.grab().save(str(args.data_dir / "desktop-preview.png"))
    identical = None
    if not args.single_run and not args.review_session:
        window.start_import(args.media)
        wait()
        uninterrupted_id = next(i for i in window.sessions if i != resumed.id)
        uninterrupted = window.store.load_session(uninterrupted_id)
        if uninterrupted.status != "ready":
            raise RuntimeError(window.status.text())
        identical = (
            window.store.load_transcript(resumed.id, "raw").segments
            == window.store.load_transcript(uninterrupted.id, "raw").segments
        )
        if not identical:
            raise RuntimeError("Resumed segments differ from uninterrupted output")
    report = {
        "model": args.model,
        "requested_device": "CPU",
        "actual_device": resumed.diagnostics.get("actual_device"),
        "pause_committed_chunks": committed,
        "resumed_chunks": len(resumed.diagnostics.get("chunk_records", [])),
        "status": resumed.status,
        "resume_matches_uninterrupted_segments": identical,
        "fallback_events": len(resumed.diagnostics.get("fallback_events", [])),
        "qt_heartbeats": heartbeats[0],
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "exports": exports,
        "search_selection": True,
        "source_duration_seconds": resumed.diagnostics.get("source_duration_seconds"),
        "player_duration_ms": duration_ms,
        "muted_playback_advanced": advanced,
        "transcript_segment_seek": True,
        "workflow": "review-existing-session" if args.review_session else "import-pause-resume",
        "worker": "frozen-executable" if args.worker_executable else "python-module",
        "inference_seconds": resumed.diagnostics.get("inference_seconds"),
        "scope": "One Windows host, offscreen Qt, real CPU inference; "
        "source Qt UI; no microphone or visual interaction validation",
    }
    atomic_json(args.report, report)
    print(json.dumps(report, indent=2))
    window.close()


if __name__ == "__main__":
    main()
