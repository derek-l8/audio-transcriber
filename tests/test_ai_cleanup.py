"""Cleanup validation, publication, and CLI boundaries without model/network I/O."""

from __future__ import annotations

import json

import pytest

from npu_scribe.ai_cleanup import (
    DEFAULT_MODEL,
    CleanupCancelled,
    CleanupError,
    check_candidate,
    cleanup_session,
    cleanup_text,
    source_blocks,
    split_text,
)
from npu_scribe.cleanup import deterministic_cleanup
from npu_scribe.cli import main
from npu_scribe.engines import MockSpeechEngine
from npu_scribe.models import Segment
from npu_scribe.pipeline import BatchOptions, BatchRunner
from npu_scribe.storage import SessionStore, sha256_file


class Formatter:
    def generate(self, text, mode, style):
        return text.replace("um ", "").capitalize() + "."


@pytest.fixture
def ready(tmp_path, three_second_wav):
    store = SessionStore(tmp_path / "library")
    session = BatchRunner(
        store,
        lambda device: MockSpeechEngine(),
        [],
        BatchOptions(model_id="mock", requested_device="CPU"),
    ).run_new(three_second_wav)
    return store, session


def test_rule_cleanup_keeps_context_and_technical_command_words():
    assert (
        deterministic_cleanup("I actually disagree with this period of oscillation")
        == "I actually disagree with this period of oscillation."
    )
    assert (
        deterministic_cleanup("Keep the red board. I mean the blue board.")
        == "Keep the red board. I mean the blue board."
    )


@pytest.mark.parametrize(
    "source,candidate,mode,reason",
    [
        ("Use 5 volts", "Use 50 volts", "lecture", "quantity-change"),
        ("Do not change it", "Change it", "dictation", "negation-change"),
        ("It cannot oscillate", "It can oscillate", "lecture", "negation-change"),
        ("It doesn't oscillate", "It oscillates", "lecture", "negation-change"),
        ("The result is uncertain", "", "lecture", "empty-output"),
        (
            "This is a lecture with many details that must all remain in the result",
            "A lecture",
            "lecture",
            "large-deletion",
        ),
    ],
)
def test_concrete_content_regressions_are_detected(source, candidate, mode, reason):
    assert reason in check_candidate(source, candidate, mode)


def test_dictation_allows_corrected_value_but_not_new_value():
    assert not check_candidate("meet at 2 actually 3", "Meet at 3.", "dictation")
    assert "quantity-change" in check_candidate("meet at 2 actually 3", "Meet at 4.", "dictation")
    assert not check_candidate(
        "first email Alex second call Jamie", "1. Email Alex.\n2. Call Jamie.", "dictation"
    )


def test_explicit_no_sorry_correction_is_not_factual_negation():
    assert not check_candidate("Friday no sorry Monday", "Monday.", "dictation")
    assert "negation-change" in check_candidate("do not change it", "Change it.", "dictation")


def test_guarded_block_retains_raw_text_and_warning():
    class Bad:
        def generate(self, *args):
            return "Use 50 volts."

    text, records = cleanup_text("Use 5 volts", Bad(), "lecture", "light")
    assert text == "Use 5 volts"
    assert records[0]["used_source"]
    assert records[0]["warnings"] == ["quantity-change"]


def test_long_text_blocks_cover_all_words_and_have_source_intervals():
    text = " ".join(f"word{i}" for i in range(500))
    blocks = split_text(text)
    assert " ".join(blocks) == text
    assert all(len(block) <= 1200 for block in blocks)
    groups = source_blocks((Segment(10, 30, text),))
    assert len(groups) > 1
    assert all(group.start == 10 and group.end == 30 and group.uncertain for group in groups)
    with pytest.raises(CleanupError, match="token"):
        split_text("x" * 1201)


def test_ai_versions_preserve_raw_balanced_and_prior_results(ready):
    store, session = ready
    raw = store.session_dir(session.id) / "raw-transcript.json"
    balanced = store.session_dir(session.id) / "balanced-transcript.json"
    before = [sha256_file(path) for path in (raw, balanced)]
    first = cleanup_session(store, session.id, Formatter())
    first_payload = json.loads(first.read_text())
    cleanup_session(store, session.id, Formatter(), mode="dictation", style="medium")
    history = list((store.session_dir(session.id) / "ai-cleanup-history").glob("*.json"))
    assert len(history) == 2
    assert any(json.loads(path.read_text()) == first_payload for path in history)
    assert before == [sha256_file(path) for path in (raw, balanced)]
    result = store.load_transcript(session.id, "ai")
    assert result.transformation["source_sha256"] == before[0]
    assert result.transformation["mode"] == "dictation"
    assert result.provenance.model == DEFAULT_MODEL
    assert store.load_session(session.id).status == "ready"


def test_cancellation_or_model_error_does_not_replace_previous_version(ready):
    store, session = ready
    output = cleanup_session(store, session.id, Formatter())
    before = output.read_bytes()
    with pytest.raises(CleanupCancelled):
        cleanup_session(store, session.id, Formatter(), cancel_requested=lambda: True)

    class Failure:
        def generate(self, *args):
            raise RuntimeError("model failed")

    with pytest.raises(RuntimeError, match="model failed"):
        cleanup_session(store, session.id, Failure())
    assert output.read_bytes() == before
    assert len(list((output.parent / "ai-cleanup-history").glob("*.json"))) == 1


def test_cancel_after_generation_does_not_publish(ready):
    store, session = ready
    cancelled = False

    class Stop:
        def generate(self, text, *args):
            nonlocal cancelled
            cancelled = True
            return text

    with pytest.raises(CleanupCancelled):
        cleanup_session(store, session.id, Stop(), cancel_requested=lambda: cancelled)
    assert not (store.session_dir(session.id) / "ai-transcript.json").exists()


def test_cli_session_cleanup_exports_all_formats(ready, monkeypatch):
    store, session = ready
    monkeypatch.setattr("npu_scribe.cli.make_model", lambda *args: Formatter())
    base = ["--data-dir", str(store.data_dir)]
    assert main(base + ["cleanup", session.id]) == 0
    for fmt in ("text", "markdown", "json", "srt"):
        assert main(base + ["export", session.id, "--layer", "ai", "--format", fmt]) == 0
    exported = json.loads((store.exports_dir(session.id) / f"{session.id}.ai.json").read_text())
    assert exported["transformation"]["source_layer"] == "raw"
    assert exported["transformation"]["model_revision"]


def test_cli_text_cleanup_preserves_input_and_refuses_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr("npu_scribe.cli.make_model", lambda *args: Formatter())
    source = tmp_path / "input.txt"
    source.write_text("um keep 5 volts")
    output = tmp_path / "output.json"
    base = [
        "--data-dir",
        str(tmp_path / "library"),
        "cleanup-text",
        str(source),
        "--output",
        str(output),
        "--format",
        "json",
        "--mode",
        "dictation",
    ]
    assert main(base) == 0
    assert json.loads(output.read_text())["text"] == "Keep 5 volts."
    assert source.read_text() == "um keep 5 volts"
    assert main(base) == 1
    assert main(base + ["--overwrite"]) == 0
    assert main(["cleanup-text", str(source), "--output", str(source), "--overwrite"]) == 1


def test_cli_requires_cleanup_model_and_never_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "npu_scribe.acquisition.https_fetcher", lambda *args: pytest.fail("network")
    )
    assert main(["--data-dir", str(tmp_path), "cleanup", "unknown-session"]) == 1
    assert (
        main(["--data-dir", str(tmp_path), "transcribe", "file.wav", "--model", DEFAULT_MODEL]) == 1
    )


def test_formatted_exports_keep_paragraphs_and_lists():
    from npu_scribe.export import plain_text, render
    from npu_scribe.models import InferenceProvenance, Transcript

    transcript = Transcript(
        (Segment(0, 10, "Hello.\n\n1. First.\n2. Second."), Segment(10, 20, "Another paragraph.")),
        InferenceProvenance("cleanup", "fixture", "CPU", "CPU"),
        transformation={"mode": "dictation"},
    )
    assert plain_text(transcript) == "Hello.\n\n1. First.\n2. Second.\n\nAnother paragraph.\n"
    markdown = render(transcript, "ai", "markdown", "Test")
    assert "\n1. First.\n2. Second.\n\nAnother paragraph." in markdown
    assert "- [" not in markdown


@pytest.mark.parametrize("level", ["light", "medium"])
def test_transcribe_chains_selected_cleanup(level, tmp_path, three_second_wav, monkeypatch):
    import npu_scribe.cli as cli

    monkeypatch.setattr(cli, "make_model", lambda *args: Formatter())
    library = tmp_path / "library"
    assert (
        main(
            [
                "--data-dir",
                str(library),
                "transcribe",
                str(three_second_wav),
                "--model",
                "mock",
                "--cleanup",
                level,
            ]
        )
        == 0
    )
    store = SessionStore(library)
    session_id = next(store.lectures.iterdir()).name
    ai = store.load_transcript(session_id, "ai")
    assert ai.transformation["style"] == level
    assert store.load_session(session_id).status == "ready"
    assert store.load_transcript(session_id, "raw").text == "synthetic transcript"


def test_off_never_loads_cleanup_and_failure_keeps_transcript(
    tmp_path, three_second_wav, monkeypatch, capsys
):
    import npu_scribe.cli as cli

    def unavailable(*args):
        raise CleanupError("model missing")

    monkeypatch.setattr(cli, "make_model", unavailable)
    library = tmp_path / "library"
    command = ["--data-dir", str(library), "transcribe", str(three_second_wav), "--model", "mock"]
    assert main([*command, "--cleanup", "off"]) == 0
    assert main([*command, "--cleanup", "light"]) == 1
    assert "Transcription is ready and can be exported" in capsys.readouterr().err
    store = SessionStore(library)
    for directory in store.lectures.iterdir():
        assert store.load_session(directory.name).status == "ready"
        assert store.load_transcript(directory.name, "raw").text
        assert not (directory / "ai-transcript.json").exists()


def test_summary_is_separate_formatted_notes_and_not_subtitles(ready, monkeypatch):
    import npu_scribe.cli as cli
    from npu_scribe.export import ExportError, write_export

    store, session = ready
    cleanup_session(store, session.id, Formatter())
    raw_hash = sha256_file(store.session_dir(session.id) / "raw-transcript.json")
    ai_hash = sha256_file(store.session_dir(session.id) / "ai-transcript.json")

    class Notes:
        device = "GPU"

        def generate(self, text, mode, style):
            assert mode == "summary"
            return '{"sections":[{"heading":"Synthetic transcript","sentences":[0]}]}'

    monkeypatch.setattr(cli, "make_model", lambda *args: Notes())
    assert main(["--data-dir", str(store.data_dir), "summarize", session.id]) == 0
    notes = store.load_transcript(session.id, "summary")
    assert notes.text.startswith("## Synthetic transcript")
    assert notes.provenance.actual_device == "GPU"
    assert notes.transformation["prompt_version"] == "summary-v2"
    assert len(list((store.session_dir(session.id) / "summary-history").glob("*.json"))) == 1
    assert sha256_file(store.session_dir(session.id) / "raw-transcript.json") == raw_hash
    assert sha256_file(store.session_dir(session.id) / "ai-transcript.json") == ai_hash
    assert (
        "## Synthetic transcript"
        in write_export(store, session.id, "summary", "markdown").read_text()
    )
    with pytest.raises(ExportError, match="not subtitles"):
        write_export(store, session.id, "summary", "srt")
    assert check_candidate("There are 5 steps", "There are 50 steps", "summary") == [
        "quantity-change"
    ]
    assert (
        check_candidate("There are 5 steps and many other details", "Five steps", "summary") == []
    )


def fake_runtime(monkeypatch, devices, load_failure=False, generate_failure=False, cancelled=None):
    import sys
    from types import SimpleNamespace

    from npu_scribe.ai_cleanup import LocalCleanupModel

    loads = []

    class Pipeline:
        def __init__(self, folder, device, config):
            loads.append(device)
            self.device = device
            if device == "GPU" and load_failure:
                raise RuntimeError("driver failure")

        def generate(self, *args, **kwargs):
            if self.device == "GPU" and generate_failure:
                raise RuntimeError("generation failure")
            return SimpleNamespace(
                texts=["The result."],
                perf_metrics=SimpleNamespace(get_num_generated_tokens=lambda: 4),
            )

    monkeypatch.setitem(
        sys.modules,
        "openvino",
        SimpleNamespace(Core=lambda: SimpleNamespace(available_devices=devices)),
    )
    monkeypatch.setitem(
        sys.modules,
        "openvino_genai",
        SimpleNamespace(
            LLMPipeline=Pipeline,
            ChatHistory=list,
            StreamingStatus=SimpleNamespace(STOP=1, RUNNING=0),
        ),
    )
    return LocalCleanupModel(
        __import__("pathlib").Path("fixture"), cancel_requested=cancelled
    ), loads


@pytest.mark.parametrize("devices,expected", [(["CPU"], "CPU"), (["CPU", "GPU.0", "NPU"], "GPU")])
def test_cleanup_auto_uses_gpu_or_cpu(monkeypatch, devices, expected):
    model, loads = fake_runtime(monkeypatch, devices)
    assert model.generate("the result", "lecture", "light") == "The result."
    assert model.device == expected
    assert loads == [expected]
    assert model.fallback_reason is None


@pytest.mark.parametrize("load_failure,generate_failure", [(True, False), (False, True)])
def test_auto_retries_original_on_cpu_and_records_fallback(
    monkeypatch, load_failure, generate_failure, ready
):
    model, loads = fake_runtime(monkeypatch, ["CPU", "GPU"], load_failure, generate_failure)
    store, session = ready
    cleanup_session(store, session.id, model, device="AUTO")
    ai = store.load_transcript(session.id, "ai")
    assert loads == ["GPU", "CPU"]
    assert ai.provenance.requested_device == "AUTO"
    assert ai.provenance.actual_device == "CPU"
    assert "GPU failed" in ai.transformation["device_fallback"]
    assert ai.transformation["blocks"][0]["actual_device"] == "CPU"
    model.generate("again", "lecture", "light")
    assert loads == ["GPU", "CPU"]


def test_explicit_device_failure_and_cancellation_do_not_fall_back(monkeypatch):
    model, loads = fake_runtime(monkeypatch, ["CPU", "GPU"], load_failure=True)
    model.device = model.requested_device = "GPU"
    with pytest.raises(RuntimeError, match="driver failure"):
        model.generate("source", "lecture", "light")
    assert loads == ["GPU"]
    model, loads = fake_runtime(monkeypatch, ["CPU", "GPU"], cancelled=lambda: True)
    with pytest.raises(CleanupCancelled):
        model.generate("source", "lecture", "light")
    assert loads == []


def test_resume_chains_cleanup_only_after_ready(tmp_path, three_second_wav, monkeypatch):
    import npu_scribe.cli as cli

    calls = []

    def fixture(*args):
        calls.append(args[2])
        return Formatter()

    monkeypatch.setattr(cli, "make_model", fixture)
    library = tmp_path / "library"
    stop = tmp_path / "pause"
    stop.touch()
    common = ["--data-dir", str(library)]
    assert (
        main(
            [
                *common,
                "transcribe",
                str(three_second_wav),
                "--model",
                "mock",
                "--cleanup",
                "light",
                "--stop-file",
                str(stop),
            ]
        )
        == 130
    )
    assert calls == []
    session_id = next((library / "lectures").iterdir()).name
    stop.unlink()
    assert (
        main(
            [
                *common,
                "resume",
                session_id,
                "--model",
                "mock",
                "--cleanup",
                "light",
                "--stop-file",
                str(stop),
            ]
        )
        == 0
    )
    assert calls == ["AUTO"]
    assert SessionStore(library).load_transcript(session_id, "ai").text


def test_summary_cancellation_retains_previous_notes(ready):
    store, session = ready
    target = cleanup_session(store, session.id, Formatter(), mode="summary")
    previous = target.read_bytes()

    class Cancel:
        def generate(self, *args):
            raise CleanupCancelled("stopped")

    with pytest.raises(CleanupCancelled):
        cleanup_session(store, session.id, Cancel(), mode="summary")
    assert target.read_bytes() == previous


def test_summary_renders_only_selected_source_and_rejects_invalid_indices():
    from npu_scribe.ai_cleanup import render_summary, summary_input

    source = "um the pump moved five liters per minute. Power use is not known. Any questions?"
    passages, request = summary_input(source)
    assert "[0]" in request and "[2]" in request
    result = render_summary(
        '{"sections":[{"heading":"Pump","sentences":[0,1]}, '
        '{"heading":"Invented claim","sentences":[1]}]}',
        passages,
        source,
    )
    assert "five liters per minute" in result
    assert "not known" in result
    assert "Any questions" not in result
    assert "Invented claim" not in result
    assert result.count("Power use") == 1
    with pytest.raises(ValueError, match="invalid passage"):
        render_summary('{"sections":[{"heading":"Pump","sentences":[99]}]}', passages, source)


def test_invalid_summary_selection_retains_source(ready):
    store, session = ready

    class Invalid:
        def generate(self, *args):
            return '{"sections":[{"heading":"New fact","sentences":[100]}]}'

    cleanup_session(store, session.id, Invalid(), mode="summary")
    notes = store.load_transcript(session.id, "summary")
    assert notes.text == store.load_transcript(session.id, "raw").text
    assert notes.transformation["blocks"][0]["warnings"] == ["invalid-summary-selection"]
