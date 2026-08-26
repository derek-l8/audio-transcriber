"""Bounded-memory chunk iteration and overlap merging for PCM sources.

The decoded recording is never loaded fully into memory: each step reads only
chunk_duration (+ shared overlap) seconds of frames from the WAV stream.
Absolute source timestamps are preserved by offsetting engine-relative times.
"""

from __future__ import annotations

import re
import wave
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .media import NormalizedAudio, inspect_pcm_wav

DEFAULT_CHUNK_SECONDS = 30.0
DEFAULT_OVERLAP_SECONDS = 1.0
_EPSILON = 1e-6


@dataclass(frozen=True)
class ChunkSpec:
    chunk_seconds: float = DEFAULT_CHUNK_SECONDS
    overlap_seconds: float = DEFAULT_OVERLAP_SECONDS
    sample_rate: int = 16_000

    def __post_init__(self) -> None:
        if self.chunk_seconds <= 0 or self.overlap_seconds < 0:
            raise ValueError("chunk duration must be positive and overlap non-negative")
        if self.overlap_seconds >= self.chunk_seconds:
            raise ValueError("overlap must be smaller than the chunk duration")

    @property
    def identity(self) -> str:
        return f"chunks={self.chunk_seconds:g}s+overlap={self.overlap_seconds:g}s"


@dataclass(frozen=True)
class ChunkWindow:
    index: int
    start_frame: int
    end_frame: int
    start_seconds: float
    end_seconds: float
    is_final: bool


def plan_chunks(total_frames: int, spec: ChunkSpec) -> list[ChunkWindow]:
    """Deterministic windows; consecutive chunks share exactly `overlap` seconds."""
    if total_frames <= 0:
        raise ValueError("source has no audio frames")
    if spec.sample_rate <= 0:
        raise ValueError("sample rate must be positive")
    chunk_frames = round(spec.chunk_seconds * spec.sample_rate)
    overlap_frames = round(spec.overlap_seconds * spec.sample_rate)
    stride = max(1, chunk_frames - overlap_frames)
    windows: list[ChunkWindow] = []
    start = 0
    index = 0
    while True:
        end = min(start + chunk_frames, total_frames)
        windows.append(
            ChunkWindow(
                index,
                start,
                end,
                start / spec.sample_rate,
                end / spec.sample_rate,
                end >= total_frames,
            )
        )
        if end >= total_frames:
            return windows
        start += stride
        index += 1


def read_chunk(path: Path, window: ChunkWindow) -> list[float]:
    """Read one window as normalized floats; memory stays bounded per chunk."""
    _, channels, _ = inspect_pcm_wav(path)
    with wave.open(str(path), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getframerate() != 16_000:
            raise ValueError("chunk reader requires normalized mono 16 kHz PCM WAV")
        width = handle.getsampwidth()
        if width not in (1, 2, 4):
            raise ValueError("unsupported PCM sample width")
        handle.setpos(window.start_frame)
        raw = handle.readframes(window.end_frame - window.start_frame)
    count = len(raw) // (width * channels)
    return [_sample_to_float(raw[i * width : (i + 1) * width], width) for i in range(count)]


def _sample_to_float(raw: bytes, width: int) -> float:
    value = int.from_bytes(raw, byteorder="little", signed=width > 1)
    if width == 1:
        return (value - 128) / 128.0
    return value / float(1 << (8 * width - 1))


def validate_segment_times(
    segments: list[dict[str, Any]], window: ChunkWindow, duration: float
) -> None:
    """Reject invalid or non-monotonic segment timestamps before accumulation."""
    previous_end = -_EPSILON
    for segment in segments:
        start = float(segment["start"])
        end = float(segment["end"])
        if (
            start < window.start_seconds - _EPSILON
            or end > min(window.end_seconds, duration) + _EPSILON
        ):
            raise ValueError(f"segment outside its chunk window: {start:.3f}-{end:.3f}")
        if end < start - _EPSILON:
            raise ValueError("segment end precedes start")
        if start < previous_end - _EPSILON:
            raise ValueError("segments are not monotonic within the chunk")
        previous_end = end


def normalize_for_dedup(text: str) -> str:
    stripped = re.sub(r"[^a-z0-9\s]", "", text.casefold())
    return re.sub(r"\s+", " ", stripped).strip()


def merge_overlap(
    accumulated: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    boundary: float,
) -> tuple[list[dict[str, Any]], int]:
    """Append incoming segments without duplicating phrases inside the shared overlap.

    `boundary` is the absolute time where the previous chunk ended (the current
    chunk started `overlap` earlier). An incoming segment is dropped only when it
    begins before that boundary — inside the temporal overlap — AND repeats text
    already present at the accumulated tail. Legitimate repeated lecture content
    spoken later than the overlap region is always preserved.
    """
    if not accumulated:
        return list(incoming), 0
    tail_texts = {normalize_for_dedup(str(s["text"])) for s in accumulated[-4:]}
    kept: list[dict[str, Any]] = []
    dropped = 0
    for segment in incoming:
        inside_overlap = float(segment["start"]) < boundary + _EPSILON
        repeats_tail = normalize_for_dedup(str(segment["text"])) in tail_texts
        if inside_overlap and repeats_tail:
            dropped += 1
            continue
        kept.append(segment)
    return accumulated + kept, dropped


def iter_source_windows(audio: NormalizedAudio, spec: ChunkSpec) -> Iterator[ChunkWindow]:
    yield from plan_chunks(audio.frames, spec)
