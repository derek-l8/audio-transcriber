from __future__ import annotations

import json
from pathlib import Path

import pytest

from npu_scribe.checkpoint import (
    CHECKPOINT_SCHEMA_VERSION,
    Checkpoint,
    CheckpointError,
    load_checkpoint,
    save_checkpoint,
    validate_resume,
)


def sample_checkpoint() -> Checkpoint:
    return Checkpoint(
        session_id="abc123",
        source_fingerprint="f" * 64,
        model_id="whisper-tiny.en-int4-ov",
        chunk_seconds=30.0,
        overlap_seconds=1.0,
        total_chunks=4,
        completed_chunks=[0, 1],
        segments=[{"start": 0.0, "end": 1.0, "text": "hello"}],
    )


def test_checkpoint_round_trip_atomic(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    checkpoint = sample_checkpoint()
    save_checkpoint(path, checkpoint)
    loaded = load_checkpoint(path)
    assert loaded.session_id == "abc123"
    assert loaded.completed_chunks == [0, 1]
    # Atomic replacement leaves no temporary residue.
    assert [p.name for p in tmp_path.iterdir()] == ["checkpoint.json"]


def test_checkpoint_rejects_corrupt_and_unknown_schema(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CheckpointError, match="unreadable"):
        load_checkpoint(path)
    path.write_text(json.dumps({"schema_version": 999}), encoding="utf-8")
    with pytest.raises(CheckpointError, match="schema version"):
        load_checkpoint(path)
    (tmp_path / "missing.json").unlink(missing_ok=True)
    with pytest.raises(CheckpointError, match="no durable checkpoint"):
        load_checkpoint(tmp_path / "missing.json")


def test_validate_resume_mismatch_refusals() -> None:
    base = dict(
        session_id="abc123",
        source_fingerprint="f" * 64,
        model_id="m1",
        model_revision="r1",
        model_integrity="i1",
        decoder_identity="d1",
        chunk_spec_identity="chunks=30s+overlap=1s",
    )
    validate_resume(Checkpoint(**base), **base)
    for field in (
        "session_id",
        "source_fingerprint",
        "model_id",
        "model_revision",
        "model_integrity",
        "decoder_identity",
        "chunk_spec_identity",
    ):
        changed = dict(base)
        changed[field] = "different"
        if field == "chunk_spec_identity":
            with pytest.raises(CheckpointError, match="chunking"):
                validate_resume(Checkpoint(**base), **changed)
        else:
            label = {
                "model_id": "model id",
                "source_fingerprint": "source fingerprint",
                "decoder_identity": "decoder identity",
                "model_revision": "model revision",
                "model_integrity": "model integrity",
                "session_id": "session id",
            }.get(field, field)
            with pytest.raises(CheckpointError, match=label):
                validate_resume(Checkpoint(**base), **changed)


def test_schema_version_is_recorded() -> None:
    assert sample_checkpoint().schema_version == CHECKPOINT_SCHEMA_VERSION
