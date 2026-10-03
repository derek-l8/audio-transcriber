"""Versioned human edits with an atomic session pointer and immutable history."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .models import InferenceProvenance, Segment, Transcript, utc_now
from .storage import SessionStore, atomic_json, sha256_file

POINTER = re.compile(r"edits/([a-f0-9]{32})\.json")


class EditError(ValueError):
    pass


@dataclass(frozen=True)
class EditRevision:
    revision: str
    parent: str | None
    base_layer: str
    base_sha256: str
    changed_segment: int
    transcript: Transcript


@contextmanager
def edit_lock(folder: Path) -> Iterator[None]:
    """OS lock releases on process exit; the harmless lock file may remain."""
    folder.mkdir(exist_ok=True)
    lock_path = folder / "write.lock"
    if lock_path.is_symlink():
        raise EditError("Edit lock links are not supported")
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                # Windows typing stubs omit these Unix-only names.
                portable_lock: Any = fcntl
                portable_lock.flock(handle.fileno(), portable_lock.LOCK_EX | portable_lock.LOCK_NB)
        except OSError as error:
            raise EditError(
                "Another process is saving an edit; retry after it finishes."
            ) from error
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                portable_lock.flock(handle.fileno(), portable_lock.LOCK_UN)


def current_revision(store: SessionStore, session_id: str) -> str | None:
    pointer = store.load_session(session_id).edited_transcript
    if pointer is None:
        return None
    match = POINTER.fullmatch(pointer) if isinstance(pointer, str) else None
    if match is None:
        raise EditError("Invalid edited transcript pointer; no files were changed.")
    return match.group(1)


def load_revision(
    store: SessionStore, session_id: str, revision: str | None = None
) -> EditRevision:
    revision = revision or current_revision(store, session_id)
    if revision is None:
        raise FileNotFoundError("No Edited version exists; edit a Raw or Balanced segment first.")
    if re.fullmatch(r"[a-f0-9]{32}", revision) is None:
        raise EditError("Invalid edit revision")
    folder = store.session_dir(session_id) / "edits"
    path = folder / f"{revision}.json"
    if path.is_symlink() or folder.is_symlink():
        raise EditError("Edited transcript links are not supported")
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value["schema_version"] != 1
        or value["session_id"] != session_id
        or value["revision"] != revision
    ):
        raise EditError("Edit revision metadata does not match this session")
    layer = value["base_layer"]
    if layer not in ("raw", "balanced"):
        raise EditError("Invalid edit source layer")
    base_path = store.session_dir(session_id) / f"{layer}-transcript.json"
    if sha256_file(base_path) != value["base_sha256"]:
        raise EditError("The original transcript changed; edited version cannot be verified")
    transcript = Transcript(
        tuple(Segment(**segment) for segment in value["segments"]),
        InferenceProvenance(**value["provenance"]),
        value["created_at"],
    )
    base = store.load_transcript(session_id, layer)
    if not isinstance(transcript.created_at, str) or any(
        not isinstance(s.text, str) or not isinstance(s.uncertain, bool)
        for s in transcript.segments
    ):
        raise EditError("Invalid edited transcript fields")
    if transcript.provenance != base.provenance:
        raise EditError("Edited inference provenance does not match the original transcript")
    if [(s.start, s.end) for s in transcript.segments] != [(s.start, s.end) for s in base.segments]:
        raise EditError("Edited timestamps do not match the original transcript")
    return EditRevision(
        revision,
        value["parent"],
        layer,
        value["base_sha256"],
        int(value["changed_segment"]),
        transcript,
    )


def revision_history(store: SessionStore, session_id: str) -> list[EditRevision]:
    """Return the published revision chain; ignore uncommitted orphan files."""
    result = []
    revision = current_revision(store, session_id)
    seen: set[str] = set()
    while revision is not None:
        if revision in seen:
            raise EditError("Edit revision history contains a cycle")
        seen.add(revision)
        record = load_revision(store, session_id, revision)
        result.append(record)
        revision = record.parent
    return result


def save_segment_edit(
    store: SessionStore,
    session_id: str,
    segment_index: int,
    text: str,
    uncertain: bool,
    *,
    base_layer: str,
    expected_revision: str | None,
) -> EditRevision:
    if base_layer not in ("raw", "balanced"):
        raise EditError("Start an Edited version from Raw or Balanced")
    folder = store.session_dir(session_id) / "edits"
    if folder.is_symlink():
        raise EditError("Edited transcript links are not supported")
    with edit_lock(folder):
        session = store.load_session(session_id)
        if session.status != "ready":
            raise EditError("Only completed transcripts can be edited")
        revision = current_revision(store, session_id)
        if revision != expected_revision:
            raise EditError("The Edited version changed; reopen it before saving this edit.")
        if revision is None:
            transcript = store.load_transcript(session_id, base_layer)
            base_hash = sha256_file(store.session_dir(session_id) / f"{base_layer}-transcript.json")
        else:
            previous = load_revision(store, session_id, revision)
            if base_layer != previous.base_layer:
                raise EditError("An Edited version already exists with a different source layer")
            transcript = previous.transcript
            base_hash = previous.base_sha256
        if not 0 <= segment_index < len(transcript.segments):
            raise EditError("Select a valid transcript segment")
        old = transcript.segments[segment_index]
        text = text.strip()
        if text == old.text and uncertain == old.uncertain:
            raise EditError("No text or uncertainty change to save")
        segments = list(transcript.segments)
        segments[segment_index] = Segment(old.start, old.end, text, None, uncertain)
        edited = Transcript(tuple(segments), transcript.provenance, utc_now())
        new_revision = uuid.uuid4().hex
        if (folder / f"{new_revision}.json").exists():
            raise FileExistsError("Edit revision already exists; retry saving")
        record = EditRevision(new_revision, revision, base_layer, base_hash, segment_index, edited)
        atomic_json(
            folder / f"{new_revision}.json",
            {
                "schema_version": 1,
                "session_id": session_id,
                "revision": new_revision,
                "parent": revision,
                "base_layer": base_layer,
                "base_sha256": base_hash,
                "changed_segment": segment_index,
                "created_at": edited.created_at,
                "provenance": asdict(edited.provenance),
                "segments": [asdict(segment) for segment in edited.segments],
                "author": "user",
                "operation": "manual-segment-edit",
            },
        )
        # Publish only after the full immutable revision exists. If this write
        # fails, the prior pointer/history remain valid; the new file is an orphan.
        session.edited_transcript = f"edits/{new_revision}.json"
        session.updated_at = edited.created_at
        store.save_session(session)
        return record
