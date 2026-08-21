from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .cleanup import deterministic_cleanup
from .engines import SpeechEngine
from .models import Session, Transcript
from .storage import SessionStore


def run_lecture(
    session: Session, store: SessionStore, engine: SpeechEngine, audio: Path
) -> Session:
    session.status = "processing"
    store.save_session(session)
    raw = engine.transcribe(audio)
    store.save_transcript(session.id, "raw", raw)
    cleaned = Transcript(
        tuple(replace(s, text=deterministic_cleanup(s.text)) for s in raw.segments), raw.provenance
    )
    store.save_transcript(session.id, "cleaned", cleaned)
    session.raw_transcript = "raw-transcript.json"
    session.cleaned_transcript = "cleaned-transcript.json"
    session.status = "ready"
    store.save_session(session)
    return session
