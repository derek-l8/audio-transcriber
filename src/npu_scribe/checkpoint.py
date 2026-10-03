"""Durable per-chunk checkpoints for batch transcription sessions."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .models import SCHEMA_VERSION, utc_now

CHECKPOINT_SCHEMA_VERSION = 2
CHECKPOINT_NAME = "checkpoint.json"


class CheckpointError(Exception):
    """Raised when a checkpoint is missing, malformed, or fails validation."""


@dataclass
class ChunkRecord:
    index: int
    device_used: str
    seconds: float


@dataclass
class Checkpoint:
    schema_version: int = CHECKPOINT_SCHEMA_VERSION
    session_id: str = ""
    source_fingerprint: str = ""
    source_copy_name: str = ""
    source_duration_seconds: float = 0.0
    normalized_properties: dict[str, Any] = field(default_factory=dict)
    model_id: str = ""
    model_revision: str = ""
    model_integrity: str = ""
    requested_device: str = "auto"
    decoder_identity: str = ""
    chunk_spec_identity: str = ""
    chunk_seconds: float = 0.0
    overlap_seconds: float = 0.0
    chunk_strategy: str = "fixed"
    chunk_plan: list[dict[str, Any]] = field(default_factory=list)
    completed_chunks: list[int] = field(default_factory=list)
    total_chunks: int = 0
    segments: list[dict[str, Any]] = field(default_factory=list)
    chunk_records: list[dict[str, Any]] = field(default_factory=list)
    fallback_events: list[dict[str, Any]] = field(default_factory=list)
    updated_at: str = field(default_factory=utc_now)
    transcript_schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Checkpoint:
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in value.items() if k in known})


def save_checkpoint(path: Path, checkpoint: Checkpoint) -> None:
    """Atomic write-then-rename; a torn write never corrupts a durable checkpoint."""
    from .storage import atomic_json

    checkpoint.schema_version = CHECKPOINT_SCHEMA_VERSION
    checkpoint.updated_at = utc_now()
    atomic_json(path, checkpoint.to_dict())


def load_checkpoint(path: Path) -> Checkpoint:
    if not path.is_file():
        raise CheckpointError("no durable checkpoint exists for this session")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CheckpointError(f"checkpoint is unreadable: {error}") from error
    if not isinstance(value, dict):
        raise CheckpointError("checkpoint has an unexpected structure")
    if value.get("schema_version") not in (1, CHECKPOINT_SCHEMA_VERSION):
        raise CheckpointError(
            f"unsupported checkpoint schema version: {value.get('schema_version')!r}"
        )
    checkpoint = Checkpoint.from_dict(value)
    if not checkpoint.session_id:
        raise CheckpointError("checkpoint is missing its session identifier")
    return checkpoint


def validate_resume(
    checkpoint: Checkpoint,
    *,
    session_id: str,
    source_fingerprint: str,
    model_id: str,
    model_revision: str,
    model_integrity: str,
    decoder_identity: str,
    chunk_spec_identity: str,
) -> None:
    """Refuse any mismatch that would corrupt or silently restart the session."""
    mismatches: list[str] = []
    if checkpoint.session_id != session_id:
        mismatches.append("session id")
    if checkpoint.source_fingerprint != source_fingerprint:
        mismatches.append("source fingerprint")
    if checkpoint.model_id != model_id:
        mismatches.append(f"model id ({checkpoint.model_id} != {model_id})")
    if checkpoint.model_revision != model_revision:
        mismatches.append("model revision")
    if checkpoint.model_integrity != model_integrity:
        mismatches.append("model integrity identity")
    if checkpoint.decoder_identity != decoder_identity:
        mismatches.append("decoder identity")
    if checkpoint.chunk_spec_identity != chunk_spec_identity:
        mismatches.append(
            f"chunking settings ({checkpoint.chunk_spec_identity} != {chunk_spec_identity})"
        )
    if checkpoint.completed_chunks and len(checkpoint.segments) == 0 and checkpoint.total_chunks:
        mismatches.append("completed chunks recorded without accumulated segments")
    if mismatches:
        raise CheckpointError("resume refused; mismatched: " + "; ".join(mismatches))
