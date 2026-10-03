from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from .models import SCHEMA_VERSION, Session, Transcript

SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")
IMMUTABLE_LAYERS = {"raw", "balanced"}
CHUNK_SIZE = 1024 * 1024


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except OSError as error:
                # Antivirus/sync readers can briefly deny an atomic replacement
                # on Windows. Retry only those OS codes; persistent denial fails.
                if getattr(error, "winerror", None) not in (5, 32, 33) or attempt == 5:
                    raise
                time.sleep(0.02 * 2**attempt)
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


class SessionStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir.resolve()
        self.lectures = self.data_dir / "lectures"

    # -- ordinary session metadata -----------------------------------------------

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

    def load_session(self, session_id: str) -> Session:
        metadata = safe_child(self.lectures, session_id) / "session.json"
        if not metadata.is_file():
            raise FileNotFoundError(session_id)
        value = json.loads(metadata.read_text(encoding="utf-8"))
        known = set(Session.__dataclass_fields__)
        return Session(**{k: v for k, v in value.items() if k in known})

    def session_dir(self, session_id: str) -> Path:
        directory = safe_child(self.lectures, session_id)
        if not directory.is_dir():
            raise FileNotFoundError(session_id)
        return directory

    # -- imported source preservation ------------------------------------------------

    def create_imported_session(self, session: Session, source: Path) -> tuple[Path, str]:
        """Copy the original media into durable storage so moving or deleting the
        original can never break the session. Returns (copy path, sha-256)."""
        resolved = source.resolve()
        if not resolved.is_file():
            raise MediaMissing(resolved.name)
        directory = safe_child(self.lectures, session.id)
        directory.mkdir(parents=True, exist_ok=False)
        source_dir = directory / "source"
        source_dir.mkdir()
        copy_name = f"original{resolved.suffix.casefold()}"
        destination = source_dir / copy_name
        temporary = directory / f".import-{copy_name}"
        try:
            with resolved.open("rb") as reader, temporary.open("wb") as writer:
                while chunk := reader.read(CHUNK_SIZE):
                    writer.write(chunk)
                writer.flush()
                os.fsync(writer.fileno())
            os.replace(temporary, destination)
        except BaseException:
            temporary.unlink(missing_ok=True)
            shutil.rmtree(directory, ignore_errors=True)
            raise
        digest = sha256_file(destination)
        atomic_json(
            source_dir / "source.json",
            {
                "schema_version": SCHEMA_VERSION,
                "copy_name": copy_name,
                "size_bytes": destination.stat().st_size,
                "sha256": digest,
            },
        )
        atomic_json(directory / "session.json", session.to_dict())
        return destination, digest

    def source_copy(self, session_id: str) -> Path:
        copies = list((self.session_dir(session_id) / "source").glob("original.*"))
        if len(copies) != 1:
            raise FileNotFoundError(f"expected one preserved source copy for {session_id}")
        return copies[0]

    def recorded_fingerprint(self, session_id: str) -> str:
        record = json.loads(
            (self.session_dir(session_id) / "source" / "source.json").read_text(encoding="utf-8")
        )
        return str(record["sha256"])

    def work_dir(self, session_id: str) -> Path:
        directory = self.session_dir(session_id) / "work"
        directory.mkdir(exist_ok=True)
        return directory

    # -- immutable transcripts ----------------------------------------------------

    def save_transcript(self, session_id: str, layer: str, transcript: Transcript) -> Path:
        if layer not in IMMUTABLE_LAYERS:
            raise ValueError("immutable transcript layer must be raw or balanced")
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

    def load_transcript(self, session_id: str, layer: str) -> Transcript:
        from .models import InferenceProvenance, Segment

        if layer == "edited":
            from .editing import load_revision

            return load_revision(self, session_id).transcript
        if layer not in IMMUTABLE_LAYERS | {"ai", "summary"}:
            raise ValueError("unknown transcript layer")
        path = safe_child(self.lectures, session_id) / f"{layer}-transcript.json"
        if not path.is_file():
            raise FileNotFoundError(f"no {layer} transcript for {session_id}")
        value = json.loads(path.read_text(encoding="utf-8"))
        provenance = InferenceProvenance(**value["provenance"])
        segments = tuple(Segment(**s) for s in value["segments"])
        return Transcript(
            segments, provenance, str(value.get("created_at", "")), value.get("transformation")
        )

    # -- checkpoints and exports ---------------------------------------------------

    def checkpoint_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / CHECKPOINT_FILE

    def exports_dir(self, session_id: str) -> Path:
        directory = self.session_dir(session_id) / "exports"
        directory.mkdir(exist_ok=True)
        return directory

    # -- recovery ------------------------------------------------------------------

    def recover_interrupted(self) -> list[str]:
        recovered: list[str] = []
        if not self.lectures.exists():
            return recovered
        for metadata in sorted(self.lectures.glob("*/session.json")):
            value = json.loads(metadata.read_text(encoding="utf-8"))
            if value.get("status") in {"recording", "processing"}:
                value["status"] = "interrupted"
                atomic_json(metadata, value)
                recovered.append(str(value["id"]))
        return recovered


class MediaMissing(FileNotFoundError):
    pass


CHECKPOINT_FILE = "checkpoint.json"
