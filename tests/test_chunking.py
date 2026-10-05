from __future__ import annotations

import wave
from array import array
from dataclasses import asdict
from pathlib import Path

import pytest

from audio_transcriber.chunking import (
    ChunkSpec,
    iter_source_windows,
    merge_overlap,
    normalize_for_dedup,
    plan_chunks,
    read_chunk,
    restore_windows,
    validate_segment_times,
)
from audio_transcriber.media import PcmWavDecoder


def test_pause_cut_covers_audio_and_avoids_speech(tmp_path: Path) -> None:
    path = tmp_path / "speech-and-pause.wav"
    samples = array("h", [8000] * (61 * 16000))
    samples[28 * 16000 : 29 * 16000] = array("h", [0] * 16000)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(samples.tobytes())
    spec = ChunkSpec(strategy="pause-v1")
    windows = list(iter_source_windows(PcmWavDecoder().decode(path), spec))
    assert windows[0].end_seconds == 28.5
    assert windows[1].end_seconds == 58.5  # No quiet interval: fixed fallback.
    assert windows[-1].end_seconds == 61
    assert sum(w.end_frame - w.start_frame for w in windows) == len(samples)
    assert all(w.end_frame - w.start_frame <= 480000 for w in windows)
    assert restore_windows([asdict(w) for w in windows], len(samples), spec) == windows
    broken = [asdict(w) for w in windows]
    broken[1]["start_frame"] += 1
    with pytest.raises(ValueError, match="invalid saved"):
        restore_windows(broken, len(samples), spec)


def test_pause_strategy_rejects_overlap() -> None:
    with pytest.raises(ValueError, match="zero overlap"):
        ChunkSpec(strategy="pause-v1", overlap_seconds=1)


@pytest.mark.parametrize(
    "quiet_value,quiet_seconds,expected", [(0, 1.0, 28.12), (300, 1.0, 30.0), (0, 0.18, 30.0)]
)
def test_pause_v2_requires_deeper_longer_quiet_run(
    tmp_path: Path, quiet_value: int, quiet_seconds: float, expected: float
) -> None:
    path = tmp_path / "quiet.wav"
    samples = array("h", [8000] * (61 * 16000))
    count = round(quiet_seconds * 16000)
    samples[28 * 16000 : 28 * 16000 + count] = array("h", [quiet_value] * count)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(samples.tobytes())
    audio = PcmWavDecoder().decode(path)
    windows = list(iter_source_windows(audio, ChunkSpec(strategy="pause-v2")))
    assert windows[0].end_seconds == expected
    assert sum(w.end_frame - w.start_frame for w in windows) == len(samples)


def make_wav(path: Path, seconds: float, rate: int = 16_000) -> Path:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\0\0" * int(seconds * rate))
    return path


def test_plan_chunks_bounds_and_overlap() -> None:
    spec = ChunkSpec(chunk_seconds=30.0, overlap_seconds=1.0)
    windows = plan_chunks(int(90.5 * 16_000), spec)
    assert windows[0].start_seconds == 0
    assert windows[-1].is_final
    for previous, current in zip(windows, windows[1:], strict=False):
        shared = previous.end_seconds - current.start_seconds
        assert shared == pytest.approx(1.0)
        assert current.index == previous.index + 1
    assert windows[-1].end_seconds == pytest.approx(90.5)


def test_default_chunks_do_not_repeat_audio() -> None:
    spec = ChunkSpec()
    assert spec.overlap_seconds == 0
    windows = plan_chunks(60 * spec.sample_rate, spec)
    assert [window.start_seconds for window in windows] == [0, 30]
    assert windows[0].end_frame == windows[1].start_frame


def test_plan_chunks_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        plan_chunks(0, ChunkSpec())
    with pytest.raises(ValueError):
        ChunkSpec(chunk_seconds=1.0, overlap_seconds=2.0)
    with pytest.raises(ValueError):
        ChunkSpec(chunk_seconds=0.0)


def test_read_chunk_returns_bounded_samples(tmp_path: Path) -> None:
    path = make_wav(tmp_path / "a.wav", 3)
    spec = ChunkSpec(chunk_seconds=1.0, overlap_seconds=0.25)
    windows = plan_chunks(48_000, spec)
    assert len(windows) == 4
    first = read_chunk(path, windows[0])
    assert len(first) == 16_000
    assert all(-1.0 <= s <= 1.0 for s in first[:100])
    last = read_chunk(path, windows[-1])
    assert len(last) == windows[-1].end_frame - windows[-1].start_frame


def test_validate_segment_times_rejects_non_monotonic() -> None:
    spec = ChunkSpec(chunk_seconds=30.0, overlap_seconds=0.0)
    window = plan_chunks(480_000, spec)[0]
    good = [{"start": 0.0, "end": 1.0}, {"start": 1.0, "end": 2.5}]
    validate_segment_times(good, window, 30.0)
    with pytest.raises(ValueError, match="monotonic"):
        validate_segment_times(
            [{"start": 2.0, "end": 2.5}, {"start": 1.0, "end": 1.5}], window, 30.0
        )
    with pytest.raises(ValueError, match="outside its chunk window"):
        validate_segment_times([{"start": 29.9, "end": 31.0}], window, 30.0)
    with pytest.raises(ValueError, match="precedes"):
        validate_segment_times([{"start": 5.0, "end": 4.0}], window, 30.0)


def test_merge_overlap_drops_only_overlap_duplicates() -> None:
    accumulated = [
        {"start": 0.0, "end": 29.5, "text": "Ohm's law states V equals I R."},
    ]
    # The re-spoken phrase lands inside the temporal overlap of the next chunk.
    incoming_overlap_dup = {"start": 29.6, "end": 30.8, "text": "Ohm's law states V equals I R."}
    merged, dropped = merge_overlap(
        accumulated,
        [incoming_overlap_dup, {"start": 31.0, "end": 32.0, "text": "Next topic."}],
        boundary=30.0,
    )
    assert dropped == 1
    assert len(merged) == 2


def test_legitimate_repetition_outside_overlap_is_preserved() -> None:
    accumulated = [
        {"start": 0.0, "end": 1.0, "text": "V equals I R"},
        {"start": 1.0, "end": 2.0, "text": "Say it again: V equals I R"},
    ]
    repeated_later = {
        "start": 35.0,
        "end": 36.0,
        "text": "Remember, V equals I R",
    }
    _, dropped = merge_overlap(accumulated, [repeated_later], boundary=30.0)
    assert dropped == 0


def test_repeated_text_at_zero_overlap_boundary_is_preserved() -> None:
    accumulated = [{"start": 28.0, "end": 30.0, "text": "Repeat that."}]
    incoming = [{"start": 30.0, "end": 32.0, "text": "Repeat that."}]
    merged, dropped = merge_overlap(accumulated, incoming, boundary=30.0)
    assert dropped == 0
    assert merged == accumulated + incoming


def test_normalize_for_dedup_is_conservative() -> None:
    assert normalize_for_dedup("  The   THE! end. ") == normalize_for_dedup("the the end")
