from __future__ import annotations

import json
from pathlib import Path

import pytest

from npu_scribe.cleanup import deterministic_cleanup, process_text, spoken_formatting
from npu_scribe.config import propose_windows_data_location
from npu_scribe.devices import Benchmark, choose_device
from npu_scribe.dictionary import DictionaryEntry, PersonalDictionary
from npu_scribe.engines import MockSpeechEngine, inspect_audio
from npu_scribe.export import markdown, plain_text, srt, structured_json
from npu_scribe.insertion import FocusTarget, SafeInserter
from npu_scribe.metrics import cer, wer
from npu_scribe.models import InferenceProvenance, Segment, Transcript


def test_cleanup_and_literal_commands() -> None:
    assert deterministic_cleanup("um I I mean actually use NPU") == "Use NPU."
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
