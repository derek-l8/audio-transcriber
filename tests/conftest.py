from __future__ import annotations

import wave
from pathlib import Path

import pytest


@pytest.fixture
def silent_wav(tmp_path: Path) -> Path:
    path = tmp_path / "silence.wav"
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(b"\0\0" * 16_000)
    return path
