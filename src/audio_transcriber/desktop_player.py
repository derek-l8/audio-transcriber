"""Local audio playback for preserved lecture media, including audio in MP4."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget


def clock(milliseconds: int) -> str:
    seconds = max(0, milliseconds) // 1000
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


class LecturePlayer(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.source: Path | None = None
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.7)
        self.player.setAudioOutput(self.audio)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.toggle)
        row.addWidget(self.play_button)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setAccessibleName("Audio position")
        self.slider.setObjectName("audioPosition")
        self.slider.setEnabled(False)
        self.slider.setRange(0, 0)
        self.slider.valueChanged.connect(self.player.setPosition)
        row.addWidget(self.slider, 1)
        self.time = QLabel("00:00:00 / 00:00:00")
        row.addWidget(self.time)
        self.seek_button = QPushButton("Seek to segment")
        self.seek_button.setToolTip("Select transcript text, then seek to that segment's start.")
        self.seek_button.setEnabled(False)
        row.addWidget(self.seek_button)
        layout.addLayout(row)
        self.message = QLabel("Select a lecture to load its preserved audio.")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.player.durationChanged.connect(self._duration)
        self.player.positionChanged.connect(self._position)
        self.player.playbackStateChanged.connect(self._state)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.player.errorOccurred.connect(self._error)

    def load(self, source: Path | None) -> None:
        source = source.resolve() if source else None
        if source == self.source:
            return
        self.player.stop()
        self.source = source
        self.play_button.setEnabled(False)
        self.slider.setEnabled(False)
        self.seek_button.setEnabled(False)
        self.slider.setRange(0, 0)
        self.time.setText("00:00:00 / 00:00:00")
        if source is None or not source.is_file():
            self.player.setSource(QUrl())
            self.message.setText(
                "Preserved audio is unavailable."
                if source
                else "Select a lecture to load its preserved audio."
            )
            return
        self.message.setText("Loading preserved audio…")
        self.player.setSource(QUrl.fromLocalFile(str(source)))

    def toggle(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def seek(self, seconds: float) -> None:
        if self.player.isSeekable():
            self.player.setPosition(min(self.player.duration(), max(0, round(seconds * 1000))))

    def _duration(self, duration: int) -> None:
        self.slider.setRange(0, max(0, duration))
        self._position(self.player.position())

    def _position(self, position: int) -> None:
        if not self.slider.isSliderDown():
            # Playback updates must not feed back into the seek handler.
            with QSignalBlocker(self.slider):
                self.slider.setValue(position)
        self.time.setText(f"{clock(position)} / {clock(self.player.duration())}")

    def _state(self, state: QMediaPlayer.PlaybackState) -> None:
        self.play_button.setText(
            "Pause audio" if state == QMediaPlayer.PlaybackState.PlayingState else "Play"
        )

    def _media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self.player.setActiveVideoTrack(-1)
            self.play_button.setEnabled(True)
            self.slider.setEnabled(self.player.isSeekable())
            self.message.setText(
                "Preserved source audio. Select transcript text and seek to review it."
            )

    def _error(self, error: QMediaPlayer.Error, message: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            self.play_button.setEnabled(False)
            self.slider.setEnabled(False)
            self.seek_button.setEnabled(False)
            self.message.setText(f"Audio playback failed: {message}")
