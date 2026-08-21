from __future__ import annotations

import time
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .models import InferenceProvenance, Segment, Transcript


class SpeechEngine(Protocol):
    def transcribe(self, audio: Path, device: str = "CPU") -> Transcript: ...


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


def inspect_pcm_wav(path: Path) -> AudioInfo:
    if path.suffix.casefold() != ".wav":
        raise ValueError(
            "core decoder accepts PCM WAV only; use the FFmpeg adapter for other media"
        )
    with wave.open(str(path), "rb") as source:
        if source.getcomptype() != "NONE":
            raise ValueError("compressed WAV is unsupported")
        return AudioInfo(source.getframerate(), source.getnchannels(), source.getnframes())


class MockSpeechEngine:
    """Deterministic engine for contract, orchestration, and offline tests."""

    def __init__(self, segments: Sequence[Segment] | None = None):
        self.segments = tuple(segments or (Segment(0, 1, "synthetic transcript"),))

    def transcribe(self, audio: Path, device: str = "CPU") -> Transcript:
        inspect_pcm_wav(audio)
        return Transcript(
            self.segments,
            InferenceProvenance("mock", "deterministic-v1", device, "MOCK"),
        )


class OpenVINOWhisperEngine:
    """Lazy OpenVINO GenAI adapter; model acquisition is always a separate action."""

    def __init__(self, model_dir: Path):
        if not model_dir.is_dir():
            raise FileNotFoundError(model_dir)
        self.model_dir = model_dir

    def transcribe(self, audio: Path, device: str = "CPU") -> Transcript:
        info = inspect_pcm_wav(audio)
        if info.sample_rate != 16_000 or info.channels != 1:
            raise ValueError("OpenVINO input must be normalized mono 16 kHz PCM WAV")
        import openvino as ov  # type: ignore[import-untyped]
        import openvino_genai  # type: ignore[import-untyped]

        available = tuple(ov.Core().available_devices)
        requested = device.upper()
        if requested not in available:
            raise RuntimeError(f"requested device {requested} is unavailable: {available}")
        started = time.perf_counter()
        pipeline = openvino_genai.WhisperPipeline(str(self.model_dir), requested)
        loaded = time.perf_counter() - started
        with wave.open(str(audio), "rb") as source:
            frames = source.readframes(source.getnframes())
        import array

        samples = array.array("h", frames)
        normalized = [sample / 32768.0 for sample in samples]
        infer_started = time.perf_counter()
        # English-only checkpoints reject an explicit language token; multilingual
        # checkpoints already carry their configured language/task defaults.
        result = pipeline.generate(normalized, return_timestamps=True)
        elapsed = time.perf_counter() - infer_started
        text = str(result).strip()
        # Runtime availability plus explicit compilation is recorded; actual NPU execution
        # remains host-unverified until the Windows harness observes a successful run.
        provenance = InferenceProvenance(
            "openvino-genai", self.model_dir.name, requested, requested, None, loaded, elapsed
        )
        return Transcript((Segment(0, info.duration, text),), provenance)
