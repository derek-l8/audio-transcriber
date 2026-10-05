from __future__ import annotations

import json
import shutil
import wave
from pathlib import Path

import pytest

from audio_transcriber.checkpoint import Checkpoint, CheckpointError, save_checkpoint
from audio_transcriber.chunking import ChunkSpec, plan_chunks
from audio_transcriber.devices import Benchmark
from audio_transcriber.engines import MockSpeechEngine
from audio_transcriber.media import PcmWavDecoder
from audio_transcriber.models import Segment
from audio_transcriber.pipeline import (
    BatchOptions,
    BatchRunner,
    PipelineError,
    run_lecture,
    start_transcription,
)
from audio_transcriber.storage import SessionStore

CHUNK_OPTIONS = dict(chunk_seconds=1.0, overlap_seconds=0.25)


def make_runner(
    store: SessionStore,
    engine_factory=None,
    **options,
) -> BatchRunner:
    factory = engine_factory or (lambda device: MockSpeechEngine())
    benchmarks = [
        Benchmark("CPU", "speech-chunk", 0.5, "CPU"),
        Benchmark("GPU", "speech-chunk", 0.2, "GPU"),
    ]
    return BatchRunner(store, factory, benchmarks, BatchOptions(model_id="mock", **options))


def test_safe_pause_keeps_committed_chunks_and_resume_matches_uninterrupted(
    tmp_path: Path, three_second_wav: Path
) -> None:
    store = SessionStore(tmp_path / "paused")
    calls = 0

    def provider(device: str):
        class Counting(MockSpeechEngine):
            def transcribe_samples(self, samples, device="CPU"):
                nonlocal calls
                calls += 1
                return super().transcribe_samples(samples, device)

        return Counting([Segment(0, 0.5, "words in a chunk")])

    options = BatchOptions(model_id="mock", requested_device="CPU", **CHUNK_OPTIONS)
    runner = BatchRunner(store, provider, [], options, cancel_requested=lambda: calls == 1)
    paused = runner.run_new(three_second_wav)
    assert paused.status == "interrupted"
    checkpoint = read_json(store.checkpoint_path(paused.id))
    assert checkpoint["completed_chunks"] == [0]
    assert checkpoint["segments"]
    assert not (store.session_dir(paused.id) / "raw-transcript.json").exists()
    assert store.source_copy(paused.id).exists()

    def resumed_provider(device: str):
        assert store.load_session(paused.id).status == "processing"
        return provider(device)

    resumed = BatchRunner(store, resumed_provider, [], options).resume(paused.id)
    uninterrupted_store = SessionStore(tmp_path / "uninterrupted")
    uninterrupted = BatchRunner(uninterrupted_store, provider, [], options).run_new(
        three_second_wav
    )
    assert resumed.status == "ready"
    assert not store.checkpoint_path(resumed.id).exists()
    assert (
        store.load_transcript(resumed.id, "raw").segments
        == uninterrupted_store.load_transcript(uninterrupted.id, "raw").segments
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def raw_transcript(store: SessionStore, session_id: str) -> dict:
    return read_json(store.session_dir(session_id) / "raw-transcript.json")


def only_session_id(store: SessionStore) -> str:
    return sorted(p.name for p in store.lectures.iterdir())[0]


def failing_after(threshold: int):
    """Devices fail persistently once the call budget is exhausted, so device
    fallback cannot mask the synthetic fault."""
    state = {"calls": 0}

    def factory(device: str):  # noqa: ANN202
        class Flaky(MockSpeechEngine):
            def transcribe_samples(self, samples, device="CPU"):  # noqa: ANN001, ANN002
                state["calls"] += 1
                if state["calls"] > threshold:
                    raise RuntimeError("synthetic persistent failure")
                return super().transcribe_samples(samples, device)

        return Flaky([Segment(0.0, 0.5, "chunk speech")])

    return factory


def dead_factory():
    def factory(device: str):  # noqa: ANN202
        class Dead(MockSpeechEngine):
            def transcribe_samples(self, samples, device="CPU"):  # noqa: ANN001, ANN002
                raise RuntimeError("synthetic total failure")

        return Dead()

    return factory


def interrupted_session(tmp_path: Path, three_second_wav: Path) -> tuple[SessionStore, str]:
    """Run until every device dies, leaving a durable resumable checkpoint."""
    store = SessionStore(tmp_path / "data")
    try:
        make_runner(store, dead_factory(), **CHUNK_OPTIONS).run_new(three_second_wav)
    except PipelineError:
        pass
    return store, only_session_id(store)


def test_end_to_end_multi_chunk(tmp_path: Path, three_second_wav: Path) -> None:
    store = SessionStore(tmp_path / "data")
    session = make_runner(
        store,
        lambda d: MockSpeechEngine([Segment(0.0, 0.5, "hello"), Segment(0.5, 0.9, "world")]),
        **CHUNK_OPTIONS,
    ).run_new(three_second_wav)
    assert session.status == "ready"
    directory = store.session_dir(session.id)
    assert (directory / "source" / "original.wav").is_file()
    assert (directory / "raw-transcript.json").is_file()
    assert (directory / "balanced-transcript.json").is_file()
    assert not (directory / "checkpoint.json").exists()
    assert len(session.diagnostics["chunk_records"]) == 4


@pytest.mark.parametrize("strategy", ["pause-v1", "pause-v2"])
def test_pause_resume_uses_saved_plan(
    tmp_path: Path, three_second_wav: Path, monkeypatch, strategy: str
) -> None:
    options = dict(chunk_seconds=1.0, overlap_seconds=0.0, chunk_strategy=strategy)
    reference_store = SessionStore(tmp_path / "reference")
    reference = make_runner(reference_store, failing_after(10**9), **options).run_new(
        three_second_wav
    )
    store = SessionStore(tmp_path / "data")
    with pytest.raises(PipelineError):
        make_runner(store, failing_after(1), **options).run_new(three_second_wav)
    session_id = only_session_id(store)
    partial = read_json(store.checkpoint_path(session_id))
    assert partial["chunk_plan"]

    def forbidden(*args, **kwargs):
        raise AssertionError("resume must not select new pause boundaries")

    monkeypatch.setattr("audio_transcriber.pipeline.iter_source_windows", forbidden)
    resumed = make_runner(store, failing_after(10**9), **options).resume(session_id)
    assert resumed.status == "ready"
    assert (
        raw_transcript(store, session_id)["segments"]
        == raw_transcript(reference_store, reference.id)["segments"]
    )


@pytest.mark.parametrize("damage", ["missing", "gap"])
def test_pause_resume_refuses_damaged_plan(
    tmp_path: Path, three_second_wav: Path, damage: str
) -> None:
    options = dict(chunk_seconds=1.0, overlap_seconds=0.0, chunk_strategy="pause-v1")
    store = SessionStore(tmp_path / "data")
    with pytest.raises(PipelineError):
        make_runner(store, failing_after(1), **options).run_new(three_second_wav)
    session_id = only_session_id(store)
    checkpoint_path = store.checkpoint_path(session_id)
    checkpoint = read_json(checkpoint_path)
    assert checkpoint["completed_chunks"] == [0]
    if damage == "missing":
        checkpoint["chunk_plan"] = []
    else:
        checkpoint["chunk_plan"][1]["start_frame"] += 1
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    with pytest.raises(CheckpointError, match="plan"):
        make_runner(store, failing_after(10**9), **options).resume(session_id)


def test_segment_at_non_millisecond_audio_end_is_valid(tmp_path: Path) -> None:
    source = tmp_path / "fractional-duration.wav"
    frames = 134_734  # 8.420875 seconds at 16 kHz.
    with wave.open(str(source), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(b"\0\0" * frames)
    duration = frames / 16_000
    store = SessionStore(tmp_path / "data")

    session = make_runner(
        store,
        lambda device: MockSpeechEngine([Segment(0.0, duration, "speech through end")]),
    ).run_new(source)

    assert session.status == "ready"
    assert raw_transcript(store, session.id)["segments"][0]["end"] == duration


def test_multi_chunk_reuses_engine_within_run(tmp_path: Path, three_second_wav: Path) -> None:
    store = SessionStore(tmp_path / "data")
    created: list[str] = []

    def factory(device: str) -> MockSpeechEngine:
        created.append(device)
        return MockSpeechEngine()

    session = make_runner(store, factory, **CHUNK_OPTIONS).run_new(three_second_wav)
    assert len(session.diagnostics["chunk_records"]) == 4
    assert created == ["GPU"]


def test_source_copy_survives_original_deletion(tmp_path: Path, three_second_wav: Path) -> None:
    source = tmp_path / "movable.wav"
    shutil.copyfile(three_second_wav, source)
    store = SessionStore(tmp_path / "data")
    session = make_runner(store).run_new(source)
    source.unlink()
    assert store.source_copy(session.id).is_file()


def test_interruption_between_chunks_and_resume_equivalence(
    tmp_path: Path, three_second_wav: Path
) -> None:
    reference_store = SessionStore(tmp_path / "reference")
    reference = make_runner(
        reference_store, failing_after(threshold=10**9), **CHUNK_OPTIONS
    ).run_new(three_second_wav)
    reference_segments = raw_transcript(reference_store, reference.id)["segments"]

    store = SessionStore(tmp_path / "data")
    with pytest.raises(PipelineError):
        make_runner(store, failing_after(threshold=2), **CHUNK_OPTIONS).run_new(three_second_wav)
    interrupted_id = only_session_id(store)
    assert store.load_session(interrupted_id).status == "failed"
    partial = read_json(store.checkpoint_path(interrupted_id))
    assert 0 < len(partial["completed_chunks"]) < partial["total_chunks"]

    resumed = make_runner(store, failing_after(threshold=10**9), **CHUNK_OPTIONS).resume(
        interrupted_id
    )
    assert resumed.status == "ready"
    assert raw_transcript(store, interrupted_id)["segments"] == reference_segments


def test_resume_avoids_retranscribing_completed_chunks(
    tmp_path: Path, three_second_wav: Path
) -> None:
    store = SessionStore(tmp_path / "data")
    calls = {"n": 0}

    def counting_factory(device: str):  # noqa: ANN202
        class Counting(MockSpeechEngine):
            def transcribe_samples(self, samples, device="CPU"):  # noqa: ANN001, ANN002
                calls["n"] += 1
                return super().transcribe_samples(samples, device)

        return Counting()

    session_id = new_pretouched_session(store, three_second_wav, completed_all=True)
    result = make_runner(store, counting_factory, **CHUNK_OPTIONS).resume(session_id)
    assert result.status == "ready"
    assert calls["n"] == 0  # nothing was retranscribed; only finalization ran
    assert raw_transcript(store, session_id)["segments"][0]["text"] == "recovered segment"


def new_pretouched_session(store: SessionStore, source: Path, *, completed_all: bool) -> str:
    """Create a session with a durable checkpoint but no finalization yet."""
    options = BatchOptions(model_id="mock", **CHUNK_OPTIONS)
    session, fingerprint = start_transcription(store, source, options)
    total = len(plan_chunks(int(3 * 16_000), ChunkSpec(**CHUNK_OPTIONS)))
    completed = list(range(total)) if completed_all else []
    checkpoint = Checkpoint(
        session_id=session.id,
        source_fingerprint=fingerprint,
        model_id="mock",
        chunk_seconds=CHUNK_OPTIONS["chunk_seconds"],
        overlap_seconds=CHUNK_OPTIONS["overlap_seconds"],
        decoder_identity=PcmWavDecoder.identity,
        chunk_spec_identity=ChunkSpec(**CHUNK_OPTIONS).identity,
        completed_chunks=completed,
        total_chunks=total,
        segments=[{"start": 0.0, "end": 0.9, "text": "recovered segment"}],
        chunk_records=[{"index": i, "device_used": "CPU", "seconds": 0.01} for i in completed],
        normalized_properties={"duration": 3.0},
    )
    save_checkpoint(store.checkpoint_path(session.id), checkpoint)
    return session.id


def test_resume_refuses_finalized_session(tmp_path: Path, three_second_wav: Path) -> None:
    store = SessionStore(tmp_path / "data")
    session = make_runner(store).run_new(three_second_wav)
    with pytest.raises(PipelineError, match="cannot be resumed"):
        make_runner(store).resume(session.id)


def test_resume_refuses_model_mismatch_properly(tmp_path: Path, three_second_wav: Path) -> None:
    store, sid = interrupted_session(tmp_path, three_second_wav)
    other = BatchRunner(
        store, lambda d: MockSpeechEngine(), [], BatchOptions(model_id="other-mock")
    )
    with pytest.raises(CheckpointError, match="model"):
        other.resume(sid)


def test_resume_refuses_chunk_settings_mismatch(tmp_path: Path, three_second_wav: Path) -> None:
    store, sid = interrupted_session(tmp_path, three_second_wav)
    checkpoint_path = store.checkpoint_path(sid)
    value = read_json(checkpoint_path)
    value["chunk_spec_identity"] = "chunks=15s+overlap=1s"
    checkpoint_path.write_text(json.dumps(value))
    with pytest.raises(CheckpointError, match="chunking settings"):
        make_runner(store, **CHUNK_OPTIONS).resume(sid)


def test_resume_refuses_tampered_source(tmp_path: Path, three_second_wav: Path) -> None:
    store, sid = interrupted_session(tmp_path, three_second_wav)
    copy = store.source_copy(sid)
    copy.write_bytes(b"\x00\x01" * 64)
    with pytest.raises(CheckpointError, match="fingerprint"):
        make_runner(store, **CHUNK_OPTIONS).resume(sid)


def test_interruption_before_first_checkpoint_recovers(
    tmp_path: Path, three_second_wav: Path
) -> None:
    store = SessionStore(tmp_path / "data")
    import audio_transcriber.pipeline as pipeline_module

    def refusing_save(path, checkpoint):  # noqa: ANN001, ANN202
        raise KeyboardInterrupt("interrupted before first checkpoint")

    original_save = pipeline_module.save_checkpoint
    pipeline_module.save_checkpoint = refusing_save
    try:
        with pytest.raises(KeyboardInterrupt):
            make_runner(store).run_new(three_second_wav)
    finally:
        pipeline_module.save_checkpoint = original_save
    sid = only_session_id(store)
    assert not store.checkpoint_path(sid).exists()
    recovered = make_runner(store).resume(sid)
    assert recovered.status == "ready"


def test_interruption_during_checkpoint_write_keeps_last_durable_state(
    tmp_path: Path, three_second_wav: Path
) -> None:
    store = SessionStore(tmp_path / "data")
    import audio_transcriber.pipeline as pipeline_module

    real_save = pipeline_module.save_checkpoint
    state = {"writes": 0}

    def flaky_save(path, checkpoint):  # noqa: ANN001, ANN202
        state["writes"] += 1
        if state["writes"] == 2:
            raise OSError("simulated crash during checkpoint write")
        real_save(path, checkpoint)

    pipeline_module.save_checkpoint = flaky_save
    try:
        with pytest.raises(OSError):
            make_runner(store, **CHUNK_OPTIONS).run_new(three_second_wav)
    finally:
        pipeline_module.save_checkpoint = real_save
    sid = only_session_id(store)
    partial = read_json(store.checkpoint_path(sid))
    assert isinstance(partial["completed_chunks"], list)
    resumed = make_runner(store, **CHUNK_OPTIONS).resume(sid)
    assert resumed.status == "ready"


def test_device_fallback_records_provenance(tmp_path: Path, three_second_wav: Path) -> None:
    store = SessionStore(tmp_path / "data")

    def factory(device: str):  # noqa: ANN202
        class NpuFails(MockSpeechEngine):
            def transcribe_samples(self, samples, device="CPU"):  # noqa: ANN001, ANN002
                if device == "NPU":
                    raise RuntimeError("requested device NPU is unavailable")
                return super().transcribe_samples(samples, device)

        return NpuFails()

    benchmarks = [
        Benchmark("NPU", "speech-chunk", 0.1, "NPU"),
        Benchmark("CPU", "speech-chunk", 0.4, "CPU"),
    ]
    runner = BatchRunner(
        store,
        factory,
        benchmarks,
        BatchOptions(model_id="mock", requested_device="auto"),
    )
    session = runner.run_new(three_second_wav)
    assert session.status == "ready"
    assert session.diagnostics["actual_device"] == "CPU"
    assert any(e["requested_device"] == "NPU" for e in session.diagnostics["fallback_events"])
    assert all(r["device_used"] == "CPU" for r in session.diagnostics["chunk_records"])
    assert raw_transcript(store, session.id)["provenance"]["fallback_reason"]


def test_balanced_layer_deterministic_and_raw_immutable(
    tmp_path: Path, three_second_wav: Path
) -> None:
    store = SessionStore(tmp_path / "data")
    session = make_runner(
        store, lambda d: MockSpeechEngine([Segment(0.0, 0.9, "um so the the value is five volts")])
    ).run_new(three_second_wav)
    directory = store.session_dir(session.id)
    raw_before = (directory / "raw-transcript.json").read_bytes()
    balanced_before = (directory / "balanced-transcript.json").read_bytes()

    with pytest.raises(FileExistsError):
        run_lecture(
            store.load_session(session.id),
            store,
            MockSpeechEngine([Segment(0.0, 0.9, "different")]),
            three_second_wav,
        )
    assert (directory / "raw-transcript.json").read_bytes() == raw_before
    assert (directory / "balanced-transcript.json").read_bytes() == balanced_before
    balanced = read_json(directory / "balanced-transcript.json")
    assert balanced["segments"][0]["text"].startswith("So the value")


def test_unsupported_media_requires_ffmpeg(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "data")
    source = tmp_path / "clip.m4a"
    source.write_bytes(b"payload")
    with pytest.raises(Exception, match="--ffmpeg"):  # noqa: B017 - MediaError
        make_runner(store).run_new(source)


def test_ffmpeg_decoded_source_flows_through_pipeline(tmp_path: Path, stub_media: str) -> None:
    store = SessionStore(tmp_path / "data")
    source = tmp_path / "clip.mp3"
    source.write_bytes(b"payload")
    session = make_runner(store, ffmpeg_path=stub_media).run_new(source)
    assert session.status == "ready"
