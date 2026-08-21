from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

SCHEMA_VERSION = 1
Mode = Literal["raw", "balanced", "aggressive"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str
    confidence: float | None = None
    uncertain: bool = False

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError("invalid segment timestamps")


@dataclass(frozen=True)
class InferenceProvenance:
    engine: str
    model: str
    requested_device: str
    actual_device: str
    fallback_reason: str | None = None
    load_seconds: float | None = None
    inference_seconds: float | None = None


@dataclass(frozen=True)
class Transcript:
    segments: tuple[Segment, ...]
    provenance: InferenceProvenance
    created_at: str = field(default_factory=utc_now)

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments if s.text.strip())


@dataclass
class Session:
    id: str
    title: str
    status: Literal["recording", "processing", "ready", "interrupted", "failed"]
    source_audio: str
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    raw_transcript: str | None = None
    cleaned_transcript: str | None = None
    edited_transcript: str | None = None
    outline: str | None = None
    summary: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
