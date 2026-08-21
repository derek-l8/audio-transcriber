from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .models import SCHEMA_VERSION, Session, Transcript

SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def atomic_json(path: Path, value: Any) -> None:
    atomic_write(path, (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode())


def safe_child(root: Path, name: str) -> Path:
    if not SAFE_ID.fullmatch(name):
        raise ValueError("unsafe identifier")
    root = root.resolve()
    child = (root / name).resolve()
    if root not in child.parents:
        raise ValueError("path escapes data directory")
    return child


class SessionStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir.resolve()
        self.lectures = self.data_dir / "lectures"

    def create(self, session: Session) -> Path:
        directory = safe_child(self.lectures, session.id)
        directory.mkdir(parents=True, exist_ok=False)
        atomic_json(directory / "session.json", session.to_dict())
        return directory

    def save_session(self, session: Session) -> None:
        directory = safe_child(self.lectures, session.id)
        if not directory.is_dir():
            raise FileNotFoundError(session.id)
        atomic_json(directory / "session.json", session.to_dict())

    def save_transcript(self, session_id: str, layer: str, transcript: Transcript) -> Path:
        if layer not in {"raw", "cleaned"}:
            raise ValueError("immutable transcript layer must be raw or cleaned")
        path = safe_child(self.lectures, session_id) / f"{layer}-transcript.json"
        if path.exists():
            raise FileExistsError(f"{layer} transcript is immutable")
        payload = {
            "schema_version": SCHEMA_VERSION,
            "created_at": transcript.created_at,
            "provenance": transcript.provenance.__dict__,
            "segments": [segment.__dict__ for segment in transcript.segments],
        }
        atomic_json(path, payload)
        return path

    def recover_interrupted(self) -> list[str]:
        recovered: list[str] = []
        if not self.lectures.exists():
            return recovered
        for metadata in self.lectures.glob("*/session.json"):
            value = json.loads(metadata.read_text(encoding="utf-8"))
            if value.get("status") in {"recording", "processing"}:
                value["status"] = "interrupted"
                atomic_json(metadata, value)
                recovered.append(str(value["id"]))
        return recovered
