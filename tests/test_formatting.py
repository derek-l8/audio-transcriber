"""Formatting must preserve source content and protect prior saved versions."""

import json

import pytest

from audio_transcriber.ai_cleanup import DEFAULT_MODEL, CleanupCancelled, CleanupError
from audio_transcriber.cli import main
from audio_transcriber.engines import MockSpeechEngine
from audio_transcriber.export import ExportError, write_export
from audio_transcriber.formatting import format_session, render_layout
from audio_transcriber.models import InferenceProvenance, Segment
from audio_transcriber.pipeline import BatchOptions, BatchRunner
from audio_transcriber.storage import SessionStore, atomic_json, sha256_file


@pytest.fixture
def ready(tmp_path, three_second_wav):
    store = SessionStore(tmp_path / "library")
    session = BatchRunner(
        store,
        lambda _: MockSpeechEngine(),
        [],
        BatchOptions(model_id="mock", requested_device="CPU"),
    ).run_new(three_second_wav)
    return store, session


def plan(indices, kind="paragraph", **extra):
    return json.dumps({"blocks": [{"kind": kind, "passages": indices, **extra}]})


@pytest.mark.parametrize("indices", [[0], [0, 0, 1], [1, 0], [0, 1, 2], [False, 1], ["0", 1]])
def test_omission_duplication_reordering_and_invalid_indices_rejected(indices):
    with pytest.raises(ValueError):
        render_layout(
            plan(indices), ["Do not change the 5 volt supply.", "Its current is unknown."]
        )


def test_heading_bullets_and_table_quote_source():
    passages = ["CPU: 2 seconds.", "GPU: 1 second.", "Power use is unknown."]
    response = json.dumps(
        {
            "blocks": [
                {"kind": "table", "passages": [0, 1]},
                {"kind": "bullets", "passages": [2], "heading": "Power use"},
            ]
        }
    )
    body, _ = render_layout(response, passages)
    assert "| CPU | 2 seconds. |" in body
    assert "| GPU | 1 second. |" in body
    assert "## Power use\n\n- Power use is unknown." in body


@pytest.mark.parametrize(
    "passages",
    [
        ["CPU: 2 seconds.", "GPU: 1 watt."],
        ["A: 2 seconds.", "A: 3 seconds."],
        ["It takes 2 seconds.", "It takes 3 seconds."],
    ],
)
def test_tables_require_explicit_comparable_source_rows(passages):
    with pytest.raises(ValueError):
        render_layout(plan([0, 1], "table"), passages)


def test_no_inferred_steps_or_new_headings():
    passages = ["Power use is unknown.", "Do not change the supply."]
    with pytest.raises(ValueError):
        render_layout(plan([0, 1], "steps"), passages)
    with pytest.raises(ValueError):
        render_layout(plan([0, 1], heading="Proven energy savings"), passages)
    body, _ = render_layout(
        plan([0, 1], "steps"), ["First, turn off the supply.", "Then, change the cable."]
    )
    assert "1. First, turn off the supply." in body


def test_prose_needs_no_model_and_keeps_history_and_source(ready):
    store, session = ready
    directory = store.session_dir(session.id)
    before = {
        layer: sha256_file(directory / f"{layer}-transcript.json") for layer in ("raw", "balanced")
    }
    format_session(store, session.id, source_layer="raw")
    format_session(store, session.id, source_layer="raw")
    output = store.load_transcript(session.id, "formatted")
    assert output.provenance.actual_device == "none"
    assert output.transformation["source_layer"] == "raw"
    assert output.text == store.load_transcript(session.id, "raw").text
    assert len(list((directory / "formatting-history").glob("*.json"))) == 2
    assert all(
        sha256_file(directory / f"{layer}-transcript.json") == digest
        for layer, digest in before.items()
    )
    for fmt in ("text", "markdown", "json"):
        assert write_export(store, session.id, "formatted", fmt).is_file()
    with pytest.raises(ExportError, match="not subtitles"):
        write_export(store, session.id, "formatted", "srt")


def test_invalid_model_layout_falls_back_to_complete_source(ready):
    store, session = ready

    class Bad:
        device = "GPU"

        def generate(self, *args):
            return plan([])

    format_session(store, session.id, "mixed", "raw", Bad(), DEFAULT_MODEL)
    output = store.load_transcript(session.id, "formatted")
    assert output.text == store.load_transcript(session.id, "raw").text
    assert output.transformation["blocks"][0]["used_source"]
    assert output.provenance.actual_device == "GPU"


def test_cancellation_failure_and_source_change_do_not_publish(ready):
    store, session = ready
    target = format_session(store, session.id, source_layer="raw")
    before = sha256_file(target)
    with pytest.raises(CleanupCancelled):
        format_session(store, session.id, source_layer="raw", cancel_requested=lambda: True)

    class Broken:
        def generate(self, *args):
            raise RuntimeError("device failed")

    with pytest.raises(RuntimeError):
        format_session(store, session.id, "mixed", "raw", Broken(), DEFAULT_MODEL)

    class ChangesSource:
        def generate(self, *args):
            source = store.session_dir(session.id) / "raw-transcript.json"
            source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            return plan([0])

    with pytest.raises(CleanupError, match="source changed"):
        format_session(store, session.id, "mixed", "raw", ChangesSource(), DEFAULT_MODEL)
    assert sha256_file(target) == before
    assert len(list((target.parent / "formatting-history").glob("*.json"))) == 1


def test_format_reads_ai_not_raw_and_records_source_hash(ready):
    store, session = ready
    directory = store.session_dir(session.id)
    source = {
        "provenance": InferenceProvenance("fixture", "fixture", "CPU", "CPU").__dict__,
        "segments": [Segment(0, 3, "Do not change the 5 volt supply.").__dict__],
    }
    atomic_json(directory / "ai-transcript.json", source)

    class Layout:
        device = "CPU"

        def generate(self, text, mode, style):
            assert "5 volt" in text and mode == "format" and style == "structured"
            return plan([0], "bullets")

    format_session(store, session.id, "structured", "ai", Layout(), DEFAULT_MODEL)
    output = store.load_transcript(session.id, "formatted")
    assert output.text == "- Do not change the 5 volt supply."
    assert output.transformation["source_sha256"] == sha256_file(directory / "ai-transcript.json")


def test_cli_raw_format_without_model_and_cleanup_model_reuse(ready, monkeypatch):
    store, session = ready
    common = ["--data-dir", str(store.data_dir)]
    assert main(common + ["format", session.id, "--source", "raw"]) == 0
    calls = []

    class Shared:
        device = "GPU"

        def generate(self, text, mode, style):
            calls.append(mode)
            if mode == "format":
                indices = [int(line.split("]")[0][1:]) for line in text.splitlines()]
                return plan(indices, "bullets")
            return text

    made = []

    def factory(*args):
        made.append(1)
        return Shared()

    monkeypatch.setattr("audio_transcriber.cli.make_model", factory)
    assert main(common + ["cleanup", session.id, "--formatting", "structured"]) == 0
    assert made == [1] and calls == ["lecture", "format"]
    assert store.load_transcript(session.id, "formatted").transformation["source_layer"] == "ai"


def test_transcribe_off_cleanup_can_format_without_text_model(
    tmp_path, three_second_wav, monkeypatch
):
    def forbidden(*args):
        raise AssertionError("prose must not load a text model")

    monkeypatch.setattr("audio_transcriber.cli.make_model", forbidden)
    data = tmp_path / "library"
    assert (
        main(
            [
                "--data-dir",
                str(data),
                "transcribe",
                "--cleanup",
                "off",
                str(three_second_wav),
                "--model",
                "mock",
                "--formatting",
                "prose",
            ]
        )
        == 0
    )
    store = SessionStore(data)
    session = next(store.lectures.iterdir()).name
    assert store.load_transcript(session, "formatted").transformation["source_layer"] == "raw"


def test_long_source_requests_are_bounded_and_cover_every_passage(ready):
    store, session = ready
    text = " ".join(f"Passage {i} must remain." for i in range(25))
    path = store.session_dir(session.id) / "ai-transcript.json"
    atomic_json(
        path,
        {
            "provenance": InferenceProvenance("fixture", "fixture", "CPU", "CPU").__dict__,
            "segments": [Segment(0, 3, text).__dict__],
        },
    )

    class Bounded:
        def generate(self, request, mode, style):
            count = len(request.splitlines())
            assert count <= 8
            return plan(list(range(count)), "bullets")

    format_session(store, session.id, "mixed", "ai", Bounded(), DEFAULT_MODEL)
    output = store.load_transcript(session.id, "formatted")
    assert len(output.segments) == 4
    assert sum(len(record["passages"]) for record in output.transformation["blocks"]) == 25
    for i in range(25):
        assert output.text.count(f"Passage {i} must remain.") == 1
