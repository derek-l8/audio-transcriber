"""Bounded-memory chunk iteration and overlap merging for PCM sources.

The decoded recording is never loaded fully into memory: each step reads only
chunk_duration (+ shared overlap) seconds of frames from the WAV stream.
Absolute source timestamps are preserved by offsetting engine-relative times.
"""

from __future__ import annotations

import math
import re
import wave
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .media import NormalizedAudio, inspect_pcm_wav

DEFAULT_CHUNK_SECONDS = 30.0
DEFAULT_OVERLAP_SECONDS = 0.0
_EPSILON = 1e-6


@dataclass(frozen=True)
class ChunkSpec:
    chunk_seconds: float = DEFAULT_CHUNK_SECONDS
    overlap_seconds: float = DEFAULT_OVERLAP_SECONDS
    sample_rate: int = 16_000
    strategy: str = "fixed"

    def __post_init__(self) -> None:
        if (
            self.sample_rate <= 0
            or not math.isfinite(self.chunk_seconds)
            or not math.isfinite(self.overlap_seconds)
        ):
            raise ValueError("chunk settings must be finite with a positive sample rate")
        if round(self.chunk_seconds * self.sample_rate) < 1:
            raise ValueError("chunk duration must contain at least one frame")
        if self.strategy not in ("fixed", "pause-v1", "pause-v2"):
            raise ValueError("unknown chunk strategy")
        if self.strategy != "fixed" and self.overlap_seconds:
            raise ValueError("pause chunking requires zero overlap")
        if self.chunk_seconds <= 0 or self.overlap_seconds < 0:
            raise ValueError("chunk duration must be positive and overlap non-negative")
        if self.overlap_seconds >= self.chunk_seconds:
            raise ValueError("overlap must be smaller than the chunk duration")

    @property
    def identity(self) -> str:
        base = f"chunks={self.chunk_seconds:g}s+overlap={self.overlap_seconds:g}s"
        return base if self.strategy == "fixed" else f"{base}+strategy={self.strategy}"


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
    if spec.strategy != "fixed":
        raise ValueError("pause chunking requires source audio; use iter_source_windows")
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
        inside_overlap = float(segment["start"]) < boundary - _EPSILON
        repeats_tail = normalize_for_dedup(str(segment["text"])) in tail_texts
        if inside_overlap and repeats_tail:
            dropped += 1
            continue
        kept.append(segment)
    return accumulated + kept, dropped


def iter_source_windows(audio: NormalizedAudio, spec: ChunkSpec) -> Iterator[ChunkWindow]:
    if audio.frames <= 0 or spec.sample_rate != audio.sample_rate:
        raise ValueError("chunk settings do not match source audio")
    if spec.strategy == "fixed":
        yield from plan_chunks(audio.frames, spec)
        return
    # Search only the final three seconds before each maximum-length cut.
    # A pause is >=160 ms at <=20% of this search region's peak RMS, capped
    # at -35 dBFS. Cut at the midpoint of the latest qualifying quiet run.
    maximum = round(spec.chunk_seconds * spec.sample_rate)
    search = max(1, min(round(3 * spec.sample_rate), maximum // 2))
    block = max(1, round(0.02 * spec.sample_rate))
    start = 0
    index = 0
    while start < audio.frames:
        end = min(start + maximum, audio.frames)
        if end < audio.frames:
            probe_start = end - search
            probe_end = (
                min(audio.frames, end + round(0.3 * spec.sample_rate))
                if spec.strategy == "pause-v2"
                else end
            )
            probe = ChunkWindow(0, probe_start, probe_end, 0, 0, False)
            samples = read_chunk(audio.path, probe)
            rms = [
                math.sqrt(sum(x * x for x in samples[i : i + block]) / len(samples[i : i + block]))
                for i in range(0, len(samples), block)
            ]
            threshold = min(10 ** (-35 / 20), max(rms, default=0) * 0.2)
            if spec.strategy == "pause-v2":
                # Require a deeper, longer pause and leave only 120 ms of
                # quiet audio at the chunk tail. Lookahead confirms that the
                # remaining 120 ms is quiet without extending the input limit.
                threshold = min(10 ** (-45 / 20), max(rms, default=0) * 0.1)
            quiet_start = None
            candidates = []
            for i, energy in enumerate([*rms, float("inf")]):
                if energy <= threshold:
                    if quiet_start is None:
                        quiet_start = i
                elif quiet_start is not None:
                    if spec.strategy == "pause-v2":
                        cut = probe_start + quiet_start * block + round(0.12 * spec.sample_rate)
                        if (
                            quiet_start > 0
                            and (i - quiet_start) * block >= round(0.24 * spec.sample_rate)
                            and cut <= end
                        ):
                            candidates.append(cut)
                    elif (i - quiet_start) * block >= round(0.16 * spec.sample_rate):
                        candidates.append(probe_start + (quiet_start + i) * block // 2)
                    quiet_start = None
            if candidates:
                end = min(end, candidates[-1])
        yield ChunkWindow(
            index, start, end, start / spec.sample_rate, end / spec.sample_rate, end == audio.frames
        )
        start = end
        index += 1


def restore_windows(plan: list[dict[str, Any]], frames: int, spec: ChunkSpec) -> list[ChunkWindow]:
    """Validate saved windows before using them to resume inference."""
    windows = [ChunkWindow(**entry) for entry in plan]
    expected = 0
    for index, window in enumerate(windows):
        if (
            type(window.index) is not int
            or type(window.start_frame) is not int
            or type(window.end_frame) is not int
            or window.index != index
            or window.start_frame != expected
            or not window.start_frame < window.end_frame <= frames
            or window.end_frame - window.start_frame > round(spec.chunk_seconds * spec.sample_rate)
            or window.start_seconds != window.start_frame / spec.sample_rate
            or window.end_seconds != window.end_frame / spec.sample_rate
            or window.is_final != (window.end_frame == frames)
        ):
            raise ValueError("invalid saved chunk plan")
        expected = window.end_frame - round(spec.overlap_seconds * spec.sample_rate)
    if not windows or windows[-1].end_frame != frames:
        raise ValueError("saved chunk plan does not cover source")
    return windows
