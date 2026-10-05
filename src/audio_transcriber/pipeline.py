"""Batch transcription pipeline: import, decode, chunked transcription,
durable checkpoints, explicit resume, immutable layers, Balanced cleanup."""

from __future__ import annotations

import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import acquisition
from .checkpoint import (
    Checkpoint,
    CheckpointError,
    load_checkpoint,
    save_checkpoint,
    validate_resume,
)
from .chunking import (
    DEFAULT_CHUNK_SECONDS,
    DEFAULT_OVERLAP_SECONDS,
    ChunkSpec,
    iter_source_windows,
    merge_overlap,
    read_chunk,
    restore_windows,
    validate_segment_times,
)
from .cleanup import deterministic_cleanup
from .devices import Benchmark, device_order
from .engines import SpeechEngine
from .media import FFmpegDecoder, MediaDecoder, MediaError, PcmWavDecoder, resolve_ffmpeg
from .models import InferenceProvenance, Segment, Session, Transcript
from .storage import SessionStore

RESUMABLE_STATUSES = {"interrupted", "processing", "failed"}


@dataclass(frozen=True)
class BatchOptions:
    model_id: str = "mock"
    requested_device: str = "auto"
    chunk_seconds: float = DEFAULT_CHUNK_SECONDS
    overlap_seconds: float = DEFAULT_OVERLAP_SECONDS
    ffmpeg_path: str | None = None
    chunk_strategy: str = "fixed"


EngineProvider = Callable[[str], Any]


class PipelineError(Exception):
    pass


def error_category(error: BaseException) -> str:
    text = str(error).lower()
    if "unavailable" in text or "enumerate" in text:
        return "device-unavailable"
    if isinstance(error, MediaError):
        return "decode-failure"
    if "timeout" in text:
        return "inference-timeout"
    return "inference-failure"


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def select_decoder(suffix: str, ffmpeg_path: str | None) -> MediaDecoder:
    if suffix.casefold() == ".wav":
        return PcmWavDecoder()
    executable = resolve_ffmpeg(ffmpeg_path)
    if not executable:
        raise MediaError(
            f"decoding '{suffix}' media requires FFmpeg; install it on PATH "
            "or select its executable with --ffmpeg"
        )
    return FFmpegDecoder(executable)


def start_transcription(
    store: SessionStore,
    source: Path,
    options: BatchOptions,
) -> tuple[Session, str]:
    """Create a session, preserve the source, and return it ready to run."""
    session_id = new_session_id()
    session = Session(session_id, source.name, "recording", source.name)
    copy_path, fingerprint = store.create_imported_session(session, source)
    decoder = select_decoder(copy_path.suffix, options.ffmpeg_path)
    session.status = "processing"
    session.diagnostics.update(
        {
            "model_id": options.model_id,
            "requested_device": options.requested_device,
            "decoder_identity": decoder.identity,
            "chunk_spec_identity": _spec_identity(options),
            "chunk_seconds": options.chunk_seconds,
            "overlap_seconds": options.overlap_seconds,
            "chunk_strategy": options.chunk_strategy,
        }
    )
    store.save_session(session)
    return session, fingerprint


def _spec_identity(options: BatchOptions) -> str:
    return ChunkSpec(
        options.chunk_seconds, options.overlap_seconds, strategy=options.chunk_strategy
    ).identity


def _normalized_audio(store: SessionStore, session: Session, options: BatchOptions) -> Any:
    copy_path = store.source_copy(session.id)
    decoder = select_decoder(copy_path.suffix, options.ffmpeg_path)
    audio = decoder.decode(copy_path)
    if decoder.identity != PcmWavDecoder.identity:
        # Move the staged result into session workspace and clean the staging dir.
        destination = store.work_dir(session.id) / "normalized.wav"
        shutil.move(str(audio.path), destination)
        from .media import adopt_normalized

        adopt_normalized(audio)
        from .media import NormalizedAudio

        audio = NormalizedAudio(
            destination, audio.sample_rate, audio.channels, audio.frames, audio.decoder_identity
        )
    return audio


def _initial_checkpoint(
    store: SessionStore,
    session: Session,
    fingerprint: str,
    audio_info: dict[str, Any],
    options: BatchOptions,
    total_chunks: int,
) -> Checkpoint:
    spec = acquisition.MANIFEST.get(options.model_id)
    return Checkpoint(
        session_id=session.id,
        source_fingerprint=fingerprint,
        source_copy_name=session.source_audio,
        source_duration_seconds=float(audio_info.get("duration", 0.0)),
        normalized_properties=dict(audio_info),
        model_id=options.model_id,
        model_revision=spec.revision if spec else "n/a",
        model_integrity=spec.integrity if spec else "n/a",
        requested_device=options.requested_device,
        decoder_identity=str(session.diagnostics["decoder_identity"]),
        chunk_spec_identity=_spec_identity(options),
        chunk_seconds=options.chunk_seconds,
        overlap_seconds=options.overlap_seconds,
        chunk_strategy=options.chunk_strategy,
        total_chunks=total_chunks,
    )


class BatchRunner:
    """Runs (or resumes) one batch session with verified device fallback."""

    def __init__(
        self,
        store: SessionStore,
        engine_provider: EngineProvider,
        benchmarks: list[Benchmark],
        options: BatchOptions,
        dictionary: Any | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ):
        self.store = store
        self.engine_provider = engine_provider
        self.benchmarks = benchmarks
        self.options = options
        self.dictionary = dictionary
        self.cancel_requested = cancel_requested

    # -- public API -----------------------------------------------------------------

    def run_new(self, source: Path) -> Session:
        session, fingerprint = start_transcription(self.store, source, self.options)
        try:
            audio = _normalized_audio(self.store, session, self.options)
            info = {
                "duration": audio.duration,
                "sample_rate": audio.sample_rate,
                "channels": audio.channels,
                "frames": audio.frames,
            }
            spec = ChunkSpec(
                self.options.chunk_seconds,
                self.options.overlap_seconds,
                strategy=self.options.chunk_strategy,
            )
            windows = list(iter_source_windows(audio, spec))
            checkpoint = _initial_checkpoint(
                self.store, session, fingerprint, info, self.options, len(windows)
            )
            checkpoint.chunk_plan = [asdict(window) for window in windows]
            save_checkpoint(self.store.checkpoint_path(session.id), checkpoint)
        except Exception as error:
            self._fail(session, "prepare-source", error)
            raise
        session.diagnostics["source_duration_seconds"] = info["duration"]
        self.store.save_session(session)
        return self._run(session, checkpoint, windows)

    def resume(self, session_id: str) -> Session:
        session = self.store.load_session(session_id)
        if session.status not in RESUMABLE_STATUSES:
            raise PipelineError(
                f"session {session_id} is '{session.status}' and cannot be resumed; "
                "start a new session instead"
            )
        recorded = self.store.recorded_fingerprint(session_id)
        current = self.store.source_copy(session_id)
        from .storage import sha256_file

        if sha256_file(current) != recorded:
            raise CheckpointError(
                "resume refused; preserved source no longer matches its fingerprint"
            )
        diag = session.diagnostics
        expected_model = diag.get("model_id")
        if expected_model != self.options.model_id:
            raise CheckpointError(
                f"resume refused; model mismatch ({expected_model} != {self.options.model_id})"
            )
        spec = acquisition.MANIFEST.get(str(expected_model))
        expected_decoder = diag.get("decoder_identity")
        expected_chunking = diag.get("chunk_spec_identity")

        path = self.store.checkpoint_path(session_id)
        if path.is_file():
            checkpoint = load_checkpoint(path)
        else:
            # Interrupted before the first checkpoint: rebuild from session metadata.
            checkpoint = Checkpoint(
                session_id=session_id,
                source_fingerprint=recorded,
                source_copy_name=session.source_audio,
                model_id=str(expected_model),
                model_revision=spec.revision if spec else "recovered",
                model_integrity=spec.integrity if spec else "recovered",
                requested_device=str(diag.get("requested_device", "auto")),
                decoder_identity=str(expected_decoder),
                chunk_spec_identity=str(expected_chunking),
                chunk_seconds=float(diag.get("chunk_seconds", DEFAULT_CHUNK_SECONDS)),
                overlap_seconds=float(diag.get("overlap_seconds", DEFAULT_OVERLAP_SECONDS)),
                chunk_strategy=str(diag.get("chunk_strategy", "fixed")),
            )
        validate_resume(
            checkpoint,
            session_id=session_id,
            source_fingerprint=recorded,
            model_id=str(expected_model or ""),
            model_revision=spec.revision if spec else checkpoint.model_revision,
            model_integrity=spec.integrity if spec else checkpoint.model_integrity,
            decoder_identity=str(expected_decoder or checkpoint.decoder_identity),
            chunk_spec_identity=str(expected_chunking or checkpoint.chunk_spec_identity),
        )
        audio_info = _normalized_audio(self.store, session, self.options)
        if not checkpoint.normalized_properties:
            checkpoint.normalized_properties = {
                "duration": audio_info.duration,
                "sample_rate": audio_info.sample_rate,
                "channels": audio_info.channels,
                "frames": audio_info.frames,
            }
            checkpoint.source_duration_seconds = audio_info.duration
        spec_chunk = ChunkSpec(
            checkpoint.chunk_seconds, checkpoint.overlap_seconds, strategy=checkpoint.chunk_strategy
        )
        if checkpoint.chunk_plan:
            try:
                windows = restore_windows(checkpoint.chunk_plan, audio_info.frames, spec_chunk)
            except (TypeError, ValueError) as error:
                raise CheckpointError(f"resume refused; {error}") from error
        else:
            if checkpoint.chunk_strategy != "fixed" and checkpoint.completed_chunks:
                raise CheckpointError("resume refused; pause chunk plan is missing")
            windows = list(iter_source_windows(audio_info, spec_chunk))
            checkpoint.chunk_plan = [asdict(window) for window in windows]
        if spec_chunk.identity != checkpoint.chunk_spec_identity:
            raise CheckpointError("resume refused; chunk strategy identity mismatch")
        save_checkpoint(self.store.checkpoint_path(session.id), checkpoint)
        if any(i < 0 or i >= len(windows) for i in checkpoint.completed_chunks):
            raise CheckpointError("resume refused; completed chunks exceed the planned chunk count")
        session.status = "processing"
        self.store.save_session(session)
        return self._run(session, checkpoint, windows)

    # -- internals --------------------------------------------------------------------

    def _ordered_devices(self) -> list[str]:
        if self.options.requested_device not in ("auto", "", None):
            return [self.options.requested_device.upper()]
        order = device_order(self.benchmarks)
        return order or ["CPU"]

    def _run(self, session: Session, checkpoint: Checkpoint, windows: list[Any]) -> Session:
        checkpoint.total_chunks = len(windows)
        devices = self._ordered_devices()
        device_index = 0
        duration = float(checkpoint.normalized_properties.get("duration", 0.0)) or None
        accumulated = list(checkpoint.segments)
        pending = [w for w in windows if w.index not in set(checkpoint.completed_chunks)]
        engines: dict[str, Any] = {}
        for window in pending:
            if self.cancel_requested is not None and self.cancel_requested():
                session.status = "interrupted"
                save_checkpoint(self.store.checkpoint_path(session.id), checkpoint)
                self.store.save_session(session)
                return session
            samples = read_chunk(_audio_path(self.store, session), window)
            engine = None
            while True:
                device = devices[device_index]
                started = time.perf_counter()
                try:
                    if device not in engines:
                        engines[device] = self.engine_provider(device)
                    engine = engines[device]
                    chunk_transcript = engine.transcribe_samples(samples, device)
                    break
                except Exception as error:
                    category = error_category(error)
                    checkpoint.fallback_events.append(
                        {
                            "requested_device": devices[device_index],
                            "failed_stage": f"chunk-{window.index}",
                            "error_category": category,
                            "fallback_reason": category,
                        }
                    )
                    if device_index + 1 >= len(devices):
                        self._fail(session, f"chunk-{window.index}", error)
                        raise PipelineError(
                            f"all verified devices failed at chunk {window.index}: {category}"
                        ) from error
                    device_index += 1
            elapsed = time.perf_counter() - started
            incoming = [
                {
                    "start": float(s.start) + window.start_seconds,
                    "end": float(s.end) + window.start_seconds,
                    "text": s.text,
                    "confidence": s.confidence,
                    "uncertain": s.uncertain,
                }
                for s in chunk_transcript.segments
            ]
            if duration is not None:
                validate_segment_times(incoming, window, duration)
            boundary = window.start_seconds + checkpoint.overlap_seconds
            merged, dropped = merge_overlap(accumulated, incoming, boundary)
            accumulated = merged
            checkpoint.segments = accumulated
            checkpoint.completed_chunks.append(window.index)
            checkpoint.chunk_records.append(
                {
                    "index": window.index,
                    "device_used": devices[device_index],
                    "seconds": round(elapsed, 4),
                    "dropped_duplicates": dropped,
                }
            )
            session.updated_at = checkpoint.updated_at
            save_checkpoint(self.store.checkpoint_path(session.id), checkpoint)
        self._finalize(session, checkpoint)
        return session

    def _finalize(self, session: Session, checkpoint: Checkpoint) -> None:
        devices_used = [r["device_used"] for r in checkpoint.chunk_records]
        actual = devices_used[0] if devices_used else checkpoint.requested_device
        fallback_summary = None
        if checkpoint.fallback_events:
            fallback_summary = "; ".join(
                f"{e['requested_device']}:{e['error_category']}" for e in checkpoint.fallback_events
            )
        inference_seconds = round(sum(r["seconds"] for r in checkpoint.chunk_records), 3)
        provenance = InferenceProvenance(
            "batch-v1",
            checkpoint.model_id,
            checkpoint.requested_device,
            actual,
            fallback_summary,
            None,
            inference_seconds,
        )
        raw_segments = tuple(Segment(**s) for s in checkpoint.segments)
        raw = Transcript(raw_segments, provenance)
        self.store.save_transcript(session.id, "raw", raw)

        balanced_segments = []
        for s in raw_segments:
            text = deterministic_cleanup(s.text)
            if self.dictionary is not None:
                text, _applied = self.dictionary.apply(text)
            balanced_segments.append(Segment(s.start, s.end, text, s.confidence, s.uncertain))
        self.store.save_transcript(
            session.id,
            "balanced",
            Transcript(tuple(balanced_segments), provenance),
        )

        session.raw_transcript = "raw-transcript.json"
        session.cleaned_transcript = "balanced-transcript.json"
        session.diagnostics["actual_device"] = actual
        session.diagnostics["requested_device"] = checkpoint.requested_device
        session.diagnostics["fallback_events"] = checkpoint.fallback_events
        session.diagnostics["chunk_records"] = checkpoint.chunk_records
        session.diagnostics["inference_seconds"] = inference_seconds
        session.status = "ready"
        self.store.save_session(session)

        # Terminal state: the checkpoint is no longer needed; work files are cleaned.
        self.store.checkpoint_path(session.id).unlink(missing_ok=True)
        shutil.rmtree(self.store.work_dir(session.id), ignore_errors=True)

    def _fail(self, session: Session, stage: str, error: BaseException) -> None:
        session.status = "failed"
        session.diagnostics["failure_stage"] = stage
        session.diagnostics["failure_category"] = error_category(error)
        try:
            self.store.save_session(session)
        except Exception:  # noqa: BLE001, S110 - never mask the original failure
            pass


def _audio_path(store: SessionStore, session: Session) -> Path:
    """Normalized WAV inside session workspace, or a direct-PCM source copy."""
    normalized = store.work_dir(session.id) / "normalized.wav"
    if normalized.is_file():
        return normalized
    return store.source_copy(session.id)


# Retained compatibility helper used by earlier orchestration tests.
def run_lecture(
    session: Session, store: SessionStore, engine: SpeechEngine, audio: Path
) -> Session:
    session.status = "processing"
    store.save_session(session)
    transcript = engine.transcribe(audio)
    store.save_transcript(session.id, "raw", transcript)
    balanced = Transcript(
        tuple(
            Segment(
                s.start,
                s.end,
                deterministic_cleanup(s.text),
                s.confidence,
                s.uncertain,
            )
            for s in transcript.segments
        ),
        transcript.provenance,
    )
    store.save_transcript(session.id, "balanced", balanced)
    session.raw_transcript = "raw-transcript.json"
    session.cleaned_transcript = "balanced-transcript.json"
    session.status = "ready"
    store.save_session(session)
    return session
