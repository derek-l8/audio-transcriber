from __future__ import annotations

import json

import pytest

from audio_transcriber.export import (
    ExportError,
    markdown,
    plain_text,
    render,
    srt,
    structured_json,
    validate_srt,
)
from audio_transcriber.models import InferenceProvenance, Segment, Transcript


def sample() -> Transcript:
    provenance = InferenceProvenance(
        "batch-v1", "whisper-tiny.en-int4-ov", "auto", "CPU", None, 0.5, 2.0
    )
    return Transcript(
        (
            Segment(0.0, 1.25, "hello world"),
            Segment(1.5, 3.75, "uncertain claim", uncertain=True),
        ),
        provenance,
    )


def test_plain_markdown_json_exports() -> None:
    transcript = sample()
    assert plain_text(transcript) == "hello world uncertain claim\n"
    md = markdown(transcript, "Test")
    assert "[00:00:00]" in md and "[00:00:01]" in md
    payload = json.loads(structured_json(transcript, "balanced"))
    assert payload["layer"] == "balanced"
    assert payload["provenance"]["actual_device"] == "CPU"


def test_render_identifies_layer_and_provenance() -> None:
    header = render(sample(), "raw", "markdown", "Lecture")
    assert "layer: raw" in header
    assert "model: whisper-tiny.en-int4-ov" in header
    assert "actual device: CPU" in header
    assert "(uncertain)" in header


def test_srt_format_and_validation() -> None:
    content = srt(sample())
    assert "1\n00:00:00,000 --> 00:00:01,250\nhello world" in content
    validate_srt(content)
    with pytest.raises(ExportError):
        validate_srt("0\n00:00:00,000 --> 00:00:01,000\nx")  # numbering must start at 1
    with pytest.raises(ExportError):
        validate_srt("1\n00:00:00 --> 00:00:01,000\nx")  # malformed stamp
    with pytest.raises(ExportError):
        validate_srt("1\n00:00:05,000 --> 00:00:01,000\nx")  # end before start
    with pytest.raises(ExportError):
        validate_srt(
            "1\n00:00:05,000 --> 00:00:06,000\nx\n\n1\n00:00:00,000 --> 00:00:01,000\ny"
        )  # non-monotonic


def test_srt_rounding_carries_across_second_minute_and_hour() -> None:
    transcript = Transcript(
        (
            Segment(0.9998, 1.25, "first"),
            Segment(59.9998, 60.25, "minute"),
            Segment(3599.9998, 3600.25, "hour"),
        ),
        sample().provenance,
    )
    content = render(transcript, "raw", "srt", "Rounding boundaries")
    assert "00:00:01,000 --> 00:00:01,250" in content
    assert "00:01:00,000 --> 00:01:00,250" in content
    assert "01:00:00,000 --> 01:00:00,250" in content
    assert ",1000" not in content


def test_render_rejects_unknown_layer_and_format() -> None:
    with pytest.raises(ExportError, match="layer"):
        render(sample(), "aggressive", "text", "T")
    with pytest.raises(ExportError, match="format"):
        render(sample(), "raw", "docx", "T")


def test_srt_blank_lines_in_segment_do_not_create_extra_cues() -> None:
    transcript = Transcript(
        (
            Segment(0, 2, "First line.\n\nSecond line."),
            Segment(2, 2.5, " \n "),
            Segment(2.5, 3, "Next cue."),
        ),
        sample().provenance,
    )
    content = render(transcript, "raw", "srt", "Multiline speech")
    assert "First line.\nSecond line." in content
    assert len(content.strip().split("\n\n")) == 2
