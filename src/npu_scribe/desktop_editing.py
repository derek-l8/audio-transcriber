"""Explicit manual segment corrections and read-only revision history."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QVBoxLayout,
)

from .editing import EditRevision
from .models import Segment


class SegmentEditDialog(QDialog):
    def __init__(self, segment: Segment, commit: Callable[[str, bool], EditRevision]) -> None:
        super().__init__()
        self.commit = commit
        self.saved: EditRevision | None = None
        self.setWindowTitle("Edit transcript segment")
        self.resize(640, 360)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(f"{segment.start:.2f}–{segment.end:.2f}s · timestamps stay unchanged")
        )
        layout.addWidget(
            QLabel("Saved as a separate Edited revision. Raw and Balanced stay intact.")
        )
        self.text = QPlainTextEdit(segment.text)
        self.text.setAccessibleName("Segment text")
        self.text.setObjectName("segmentText")
        layout.addWidget(self.text, 1)
        self.uncertain = QCheckBox("Flag this segment as uncertain")
        self.uncertain.setChecked(segment.uncertain)
        layout.addWidget(self.uncertain)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self) -> None:
        try:
            self.saved = self.commit(self.text.toPlainText(), self.uncertain.isChecked())
        except (OSError, ValueError, TypeError, KeyError) as error:
            self.error.setText(f"Edit not saved: {error}")
            return  # Keep the user's draft in the open dialog for retry/copy.
        self.accept()


class RevisionHistoryDialog(QDialog):
    def __init__(self, records: list[EditRevision]) -> None:
        super().__init__()
        self.records = records
        self.setWindowTitle("Edited transcript history")
        self.resize(900, 620)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Read-only saved revisions, newest first. "
                "The library keeps the current version selected."
            )
        )
        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.setAccessibleName("Saved revisions")
        self.list.setObjectName("savedRevisions")
        for record in records:
            self.list.addItem(
                f"{record.transcript.created_at[:19]}\n{record.revision[:8]} "
                f"· segment {record.changed_segment + 1}"
            )
        body.addWidget(self.list)
        self.preview = QPlainTextEdit()
        self.preview.setAccessibleName("Revision transcript")
        self.preview.setObjectName("revisionTranscript")
        self.preview.setReadOnly(True)
        body.addWidget(self.preview, 3)
        layout.addLayout(body, 1)
        self.list.currentRowChanged.connect(self.show_revision)
        if records:
            self.list.setCurrentRow(0)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def show_revision(self, index: int) -> None:
        if 0 <= index < len(self.records):
            transcript = self.records[index].transcript
            self.preview.setPlainText(
                "\n\n".join(
                    f"[{s.start:.2f}–{s.end:.2f}s]{' [?]' if s.uncertain else ''} {s.text}"
                    for s in transcript.segments
                )
            )
