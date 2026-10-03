from __future__ import annotations

import json

import pytest

from npu_scribe.cli import main
from npu_scribe.editing import (
    EditError,
    current_revision,
    edit_lock,
    load_revision,
    revision_history,
    save_segment_edit,
)
from npu_scribe.export import write_export
from npu_scribe.models import InferenceProvenance, Segment, Session, Transcript
from npu_scribe.storage import SessionStore, sha256_file


@pytest.fixture
def store(tmp_path):
    result = SessionStore(tmp_path)
    result.create(Session("example", "Example", "ready", "original.wav"))
    provenance = InferenceProvenance("test", "mock", "CPU", "CPU")
    result.save_transcript(
        "example",
        "raw",
        Transcript(
            (Segment(0, 1, "raw words", 0.4, True), Segment(1, 2, "do not change 5 volts")),
            provenance,
        ),
    )
    result.save_transcript(
        "example",
        "balanced",
        Transcript(
            (Segment(0, 1, "Raw words.", 0.4, True), Segment(1, 2, "Do not change 5 volts.")),
            provenance,
        ),
    )
    return result


def save(store, index=0, text="Corrected words.", expected=None):
    return save_segment_edit(
        store, "example", index, text, False, base_layer="balanced", expected_revision=expected
    )


def test_revision_chain_retains_sources_timestamps_and_previous_edits(store):
    paths = [
        store.session_dir("example") / f"{layer}-transcript.json" for layer in ("raw", "balanced")
    ]
    hashes = [sha256_file(path) for path in paths]
    first = save(store)
    second = save(store, 1, "The corrected value is 7 volts.", first.revision)
    assert second.parent == first.revision
    assert current_revision(store, "example") == second.revision
    assert [r.revision for r in revision_history(store, "example")] == [
        second.revision,
        first.revision,
    ]
    transcript = store.load_transcript("example", "edited")
    assert transcript.segments[0].text == "Corrected words."
    assert transcript.segments[1].text == "The corrected value is 7 volts."
    assert [(s.start, s.end) for s in transcript.segments] == [(0, 1), (1, 2)]
    assert transcript.segments[0].confidence is None
    assert not transcript.segments[0].uncertain
    assert [sha256_file(path) for path in paths] == hashes
    assert (
        load_revision(store, "example", first.revision).transcript.segments[1].text
        == "Do not change 5 volts."
    )


def test_stale_editor_cannot_overwrite_published_revision(store):
    first = save(store)
    before = list((store.session_dir("example") / "edits").glob("*.json"))
    with pytest.raises(EditError, match="changed"):
        save(store, text="A stale draft", expected=None)
    assert current_revision(store, "example") == first.revision
    assert list((store.session_dir("example") / "edits").glob("*.json")) == before


def test_pointer_publication_failure_retains_last_version_and_ignores_orphan(store, monkeypatch):
    first = save(store)
    original = store.save_session

    def denied(session):
        raise PermissionError("synthetic publication failure")

    monkeypatch.setattr(store, "save_session", denied)
    with pytest.raises(PermissionError):
        save(store, text="Unpublished draft", expected=first.revision)
    assert current_revision(store, "example") == first.revision
    assert len(revision_history(store, "example")) == 1
    monkeypatch.setattr(store, "save_session", original)
    second = save(store, text="Published retry", expected=first.revision)
    assert [r.revision for r in revision_history(store, "example")] == [
        second.revision,
        first.revision,
    ]


def test_base_change_and_timestamp_tampering_are_refused(store):
    first = save(store)
    path = store.session_dir("example") / f"edits/{first.revision}.json"
    value = json.loads(path.read_text())
    value["segments"][0]["start"] = 0.1
    path.write_text(json.dumps(value))
    with pytest.raises(EditError, match="timestamps"):
        load_revision(store, "example")
    base = store.session_dir("example") / "balanced-transcript.json"
    base.write_text(base.read_text() + " ")
    with pytest.raises(EditError, match="original transcript changed"):
        load_revision(store, "example")


def test_os_lock_prevents_concurrent_save_and_releases_on_exit(store):
    folder = store.session_dir("example") / "edits"
    with edit_lock(folder), pytest.raises(EditError, match="Another process"):
        save(store)
    assert save(store).revision


def test_empty_edit_and_all_exports_identify_edited_layer(store):
    first = save(store, text="")
    assert first.transcript.segments[0].text == ""
    for fmt in ("text", "markdown", "srt", "json"):
        path = write_export(store, "example", "edited", fmt)
        assert path.stat().st_size > 0
        if fmt == "json":
            payload = json.loads(path.read_text())
            assert payload["layer"] == "edited"
            assert payload["edit_provenance"]["revision"] == first.revision
            assert payload["edit_provenance"]["author"] == "user"
    assert (
        main(
            [
                "--data-dir",
                str(store.data_dir),
                "export",
                "example",
                "--layer",
                "edited",
                "--format",
                "json",
                "--overwrite",
            ]
        )
        == 0
    )


def test_invalid_pointer_and_wrong_source_layer_are_refused(store):
    first = save(store)
    with pytest.raises(EditError, match="different source"):
        save_segment_edit(
            store,
            "example",
            0,
            "Wrong layer",
            False,
            base_layer="raw",
            expected_revision=first.revision,
        )
    session = store.load_session("example")
    session.edited_transcript = "../../secret.json"
    store.save_session(session)
    with pytest.raises(EditError, match="Invalid edited transcript pointer"):
        current_revision(store, "example")
