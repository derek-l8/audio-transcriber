from __future__ import annotations

import json
from pathlib import Path

import pytest

from npu_scribe.engines import MockSpeechEngine
from npu_scribe.models import Segment, Session
from npu_scribe.pipeline import run_lecture
from npu_scribe.storage import SessionStore, safe_child


def test_atomic_layers_and_recovery(tmp_path: Path, silent_wav: Path) -> None:
    store = SessionStore(tmp_path / "data")
    session = Session("session-1", "Synthetic", "recording", "source.wav")
    store.create(session)
    result = run_lecture(
        session, store, MockSpeechEngine([Segment(0, 1, "um hello hello")]), silent_wav
    )
    assert result.status == "ready"
    raw = json.loads((tmp_path / "data/lectures/session-1/raw-transcript.json").read_text())
    balanced = json.loads(
        (tmp_path / "data/lectures/session-1/balanced-transcript.json").read_text()
    )
    assert raw["segments"][0]["text"] == "um hello hello"
    assert balanced["segments"][0]["text"] == "Hello."
    with pytest.raises(FileExistsError):
        run_lecture(session, store, MockSpeechEngine(), silent_wav)


def test_recovery_and_path_safety(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    session = Session("recover", "Test", "processing", "source.wav")
    store.create(session)
    assert store.recover_interrupted() == ["recover"]
    with pytest.raises(ValueError):
        safe_child(tmp_path, "../escape")
