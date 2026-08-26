"""Speech engines.

`MockSpeechEngine` keeps orchestration deterministic in offline tests.
`OpenVINOWhisperEngine` is a lazy adapter over the pinned OpenVINO GenAI runtime.

Verified against openvino-genai 2026.3.0.0 (installed package introspection and a
live CPU run): `WhisperPipeline.generate(samples, return_timestamps=True)` returns
a `WhisperDecodedResults` with `.texts`, `.chunks` (each with `start_ts`, `end_ts`,
`text`, `token_ids`, seconds relative to the input audio), `.language`, `.words`
(only when word timestamps are enabled at construction), `.scores`, and
`.perf_metrics`. English-only checkpoints reject explicit `language`/`task`
arguments; multilingual checkpoints accept them and are forced to English here.
"""

from __future__ import annotations

import time
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .media import TARGET_RATE, inspect_pcm_wav
from .models import InferenceProvenance, Segment, Transcript


class SpeechEngine(Protocol):
    def transcribe(self, audio: Path, device: str = "CPU") -> Transcript: ...


class ChunkTranscriber(Protocol):
    def transcribe_samples(self, samples: list[float], device: str = "CPU") -> Transcript: ...


class RewriteEngine(Protocol):
    def rewrite(self, text: str, mode: str) -> str: ...


@dataclass(frozen=True)
class AudioInfo:
    sample_rate: int
    channels: int
    frames: int

    @property
    def duration(self) -> float:
        return self.frames / self.sample_rate


def inspect_audio(path: Path) -> AudioInfo:
    rate, channels, frames = inspect_pcm_wav(path)
    return AudioInfo(rate, channels, frames)


class MockSpeechEngine:
    """Deterministic engine for contract, orchestration, and offline tests."""

    def __init__(self, segments: Sequence[Segment] | None = None):
        self.segments = tuple(segments or (Segment(0, 1, "synthetic transcript"),))

    def transcribe(self, audio: Path, device: str = "CPU") -> Transcript:
        inspect_audio(audio)
        return Transcript(
            self.segments,
            InferenceProvenance("mock", "deterministic-v1", device, "MOCK"),
        )

    def transcribe_samples(self, samples: list[float], device: str = "CPU") -> Transcript:
        duration = max(len(samples) / TARGET_RATE, 1e-6)
        segments = []
        for segment in self.segments:
            end = min(segment.end, duration)
            if segment.start < duration:
                segments.append(Segment(segment.start, end, segment.text))
        return Transcript(
            tuple(segments),
            InferenceProvenance("mock", "deterministic-v1", device, "MOCK"),
        )


class OpenVINOWhisperEngine:
    """Lazy OpenVINO GenAI adapter; model acquisition is always a separate action."""

    engine_name = "openvino-genai"

    def __init__(
        self,
        model_dir: Path,
        model_id: str | None = None,
        multilingual: bool = False,
    ):
        if not model_dir.is_dir():
            raise FileNotFoundError(model_dir)
        self.model_dir = model_dir
        self.model_id = model_id or model_dir.name
        self.multilingual = multilingual
        self._pipelines: dict[str, tuple[Any, float]] = {}

    def _pipeline(self, device: str) -> tuple[Any, float]:
        requested = device.upper()
        if requested not in self._pipelines:
            import openvino as ov  # type: ignore[import-untyped]
            import openvino_genai  # type: ignore[import-untyped]

            available = tuple(ov.Core().available_devices)
            if requested not in available:
                raise RuntimeError(
                    f"requested device {requested} is unavailable; enumerated: {available}"
                )
            started = time.perf_counter()
            pipeline = openvino_genai.WhisperPipeline(str(self.model_dir), requested)
            loaded = time.perf_counter() - started
            self._pipelines[requested] = (pipeline, loaded)
        return self._pipelines[requested]

    @staticmethod
    def _read_samples(audio: Path) -> list[float]:
        import array

        with wave.open(str(audio), "rb") as source:
            frames = source.readframes(source.getnframes())
        return [sample / 32768.0 for sample in array.array("h", frames)]

    def transcribe_samples(self, samples: list[float], device: str = "CPU") -> Transcript:
        """Transcribe one bounded chunk; timestamps are relative to the chunk start."""
        pipeline, loaded = self._pipeline(device.upper())
        if self.multilingual:
            result = pipeline.generate(
                samples, language="en", task="transcribe", return_timestamps=True
            )
        else:
            result = pipeline.generate(samples, return_timestamps=True)
        duration = len(samples) / TARGET_RATE
        chunks = list(getattr(result, "chunks", []) or [])
        segments: list[Segment] = []
        for chunk in chunks:
            text = str(chunk.text).strip()
            if not text:
                continue
            start = float(chunk.start_ts)
            end = min(float(chunk.end_ts), duration)
            if end < start:
                end = start
            segments.append(Segment(start, end, text))
        if not segments:
            texts = [str(t).strip() for t in result.texts]
            joined = " ".join(t for t in texts if t)
            if joined:
                # The runtime returned no timestamp chunks; do not fabricate precision,
                # so the fallback spans the whole chunk with a documented caveat.
                segments.append(Segment(0.0, duration, joined, uncertain=True))
        actual_device = device.upper()
        provenance = InferenceProvenance(
            self.engine_name,
            self.model_id,
            actual_device,
            actual_device,
            load_seconds=loaded,
        )
        return Transcript(tuple(segments), provenance)

    def transcribe(self, audio: Path, device: str = "CPU") -> Transcript:
        """Whole-file convenience path for short inputs."""
        info = inspect_audio(audio)
        if info.sample_rate != TARGET_RATE or info.channels != 1:
            raise ValueError("OpenVINO input must be normalized mono 16 kHz PCM WAV")
        started = time.perf_counter()
        transcript = self.transcribe_samples(self._read_samples(audio), device)
        elapsed = time.perf_counter() - started
        provenance = InferenceProvenance(
            transcript.provenance.engine,
            transcript.provenance.model,
            transcript.provenance.requested_device,
            transcript.provenance.actual_device,
            transcript.provenance.fallback_reason,
            transcript.provenance.load_seconds,
            elapsed,
        )
        offset_segments = tuple(transcript.segments)
        return Transcript(offset_segments, provenance, transcript.created_at)
