from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from audio_transcriber.cleanup import deterministic_cleanup, process_text, spoken_formatting
from audio_transcriber.config import propose_windows_data_location
from audio_transcriber.devices import Benchmark, choose_device
from audio_transcriber.dictionary import DictionaryEntry, PersonalDictionary
from audio_transcriber.engines import MockSpeechEngine, OpenVINOWhisperEngine, inspect_audio
from audio_transcriber.export import markdown, plain_text, srt, structured_json
from audio_transcriber.insertion import FocusTarget, SafeInserter
from audio_transcriber.metrics import cer, wer
from audio_transcriber.models import InferenceProvenance, Segment, Transcript


def test_cleanup_and_literal_commands() -> None:
    assert deterministic_cleanup("um I I mean actually use NPU") == "I mean actually use NPU."
    assert spoken_formatting("literal comma comma new paragraph") == "comma, \n\n"


def test_aggressive_rewrite_rejects_number_change() -> None:
    class Bad:
        def rewrite(self, text: str, mode: str) -> str:
            return "Ship 6 units."

    result = process_text("ship 5 units", "aggressive", Bad())
    assert result.rewritten == "Ship 5 units."
    assert result.warnings


def test_dictionary_round_trip(tmp_path: Path) -> None:
    dictionary = PersonalDictionary([DictionaryEntry("open vino", "OpenVINO")])
    assert dictionary.apply("use open vino")[0] == "use OpenVINO"
    path = tmp_path / "dictionary.json"
    dictionary.export(path)
    assert PersonalDictionary.load(path).entries == dictionary.entries


def test_device_selection_requires_actual_device() -> None:
    results = [
        Benchmark("NPU", "speech", 0.2, "CPU"),
        Benchmark("CPU", "speech", 0.5, "CPU"),
    ]
    assert choose_device(results, "fastest") == "CPU"
    with pytest.raises(ValueError):
        choose_device(results, "manual", "NPU")


def test_exports_and_metrics() -> None:
    transcript = Transcript(
        (Segment(0, 1.25, "hello world", uncertain=True),),
        InferenceProvenance("mock", "v1", "CPU", "MOCK"),
    )
    assert plain_text(transcript) == "hello world\n"
    assert "[00:00:00]" in markdown(transcript, "Test")
    assert "00:00:00,000 --> 00:00:01,250" in srt(transcript)
    assert json.loads(structured_json(transcript, "raw"))["layer"] == "raw"
    assert wer("hello world", "hello there") == 0.5
    assert cer("abc", "adc") == pytest.approx(1 / 3)


def test_mock_engine_inspects_audio(silent_wav: Path) -> None:
    assert inspect_audio(silent_wav).duration == 1
    assert MockSpeechEngine().transcribe(silent_wav).provenance.actual_device == "MOCK"


def test_openvino_adapter_drops_zero_length_and_out_of_bounds_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = OpenVINOWhisperEngine(tmp_path)
    result = SimpleNamespace(
        chunks=[
            SimpleNamespace(start_ts=0.1, end_ts=0.5, text="spoken words"),
            SimpleNamespace(start_ts=1.0, end_ts=1.0, text="hallucinated repetition"),
            SimpleNamespace(start_ts=1.1, end_ts=1.3, text="past the audio"),
        ],
        texts=[],
    )
    pipeline = SimpleNamespace(generate=lambda samples, **kwargs: result)
    monkeypatch.setattr(engine, "_pipeline", lambda device: (pipeline, 0.0))
    transcript = engine.transcribe_samples([0.0] * 16_000)
    assert [(s.start, s.end, s.text) for s in transcript.segments] == [(0.1, 0.5, "spoken words")]


def test_openvino_adapter_does_not_restore_invalid_timestamped_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = OpenVINOWhisperEngine(tmp_path)
    result = SimpleNamespace(
        chunks=[SimpleNamespace(start_ts=1.0, end_ts=1.0, text="hallucinated")],
        texts=["hallucinated"],
    )
    pipeline = SimpleNamespace(generate=lambda samples, **kwargs: result)
    monkeypatch.setattr(engine, "_pipeline", lambda device: (pipeline, 0.0))
    assert engine.transcribe_samples([0.0] * 16_000).segments == ()


@pytest.mark.parametrize("second_start", [0.5 - 2e-6, 0.4])
def test_openvino_adapter_preserves_text_with_overlapping_timestamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, second_start: float
) -> None:
    engine = OpenVINOWhisperEngine(tmp_path)
    result = SimpleNamespace(
        chunks=[
            SimpleNamespace(start_ts=0.0, end_ts=0.5, text="first phrase"),
            SimpleNamespace(start_ts=second_start, end_ts=0.9, text="second phrase"),
        ]
    )
    pipeline = SimpleNamespace(generate=lambda samples, **kwargs: result)
    monkeypatch.setattr(engine, "_pipeline", lambda device: (pipeline, 0.0))
    transcript = engine.transcribe_samples([0.0] * 16000)
    assert transcript.text == "first phrase second phrase"
    if second_start > 0.49:
        assert len(transcript.segments) == 2
        assert transcript.segments[1].start == 0.5
    else:
        assert len(transcript.segments) == 1
        assert transcript.segments[0].uncertain
        assert transcript.segments[0].end == 1.0


def test_openvino_adapter_refreshes_npu_pipeline_between_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: list[str] = []

    class FakePipeline:
        def __init__(self, model_dir: str, device: str):
            created.append(device)

    core = SimpleNamespace(available_devices=("CPU", "NPU"))
    monkeypatch.setitem(sys.modules, "openvino", SimpleNamespace(Core=lambda: core))
    monkeypatch.setitem(
        sys.modules, "openvino_genai", SimpleNamespace(WhisperPipeline=FakePipeline)
    )
    engine = OpenVINOWhisperEngine(tmp_path)
    engine._pipeline("CPU")
    engine._pipeline("CPU")
    engine._pipeline("NPU")
    engine._pipeline("NPU")
    assert created == ["CPU", "NPU", "NPU"]


def test_onedrive_location_detection() -> None:
    value = propose_windows_data_location(
        Path("X:/Synthetic/OneDrive"), {"OneDrive": "X:/Synthetic/OneDrive"}
    )
    assert value.likely_synced
    assert "AppData" in str(value.local_fallback)


def test_insertion_restores_clipboard_and_rejects_focus_change() -> None:
    target = FocusTarget(1, 2, "Word", True)

    class Clip:
        value: object = {"html": "old"}
        restored = False

        def snapshot(self) -> object:
            return self.value

        def set_text(self, text: str) -> None:
            self.value = text

        def restore(self, snapshot: object) -> None:
            self.value, self.restored = snapshot, True

    class Focus:
        def current(self) -> FocusTarget:
            return target

    class Sender:
        def paste(self, target: FocusTarget) -> bool:
            return True

    clip = Clip()
    result = SafeInserter(clip, Focus(), Sender()).insert("kept", target)
    assert result.inserted and result.fallback_text == "kept"
    assert clip.value == {"html": "old"} and clip.restored

    class Changed:
        def current(self) -> FocusTarget:
            return FocusTarget(9, 2, "Word", True)

    assert not SafeInserter(clip, Changed(), Sender()).insert("kept", target).inserted
