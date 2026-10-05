"""The publication gate must reject private/generated data and archive path escapes."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "check_distributions", Path(__file__).resolve().parents[1] / "scripts/check_distributions.py"
)
assert spec is not None and spec.loader is not None
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


@pytest.mark.parametrize(
    "name",
    [
        "lectures/private-session/raw-transcript.json",
        "recording.m4a",
        ".scratch/results.json",
        "tests/.stubs/generated.py",
        "../secret.txt",
        "/absolute.txt",
        ".agent/STATUS.md",
        ".agents/skills/process-audio/SKILL.md",
        ".codex/config.toml",
        "AGENTS.md",
        "models/weights.bin",
    ],
)
def test_rejects_runtime_data_and_unsafe_members(name):
    with pytest.raises(ValueError):
        checker.check_names({"audio_transcriber/cli.py", name}, {"audio_transcriber/cli.py"})


def test_required_module_cannot_be_missing():
    with pytest.raises(ValueError, match="missing"):
        checker.check_names({"README.md"}, {"audio_transcriber/cli.py"})


def test_sanitized_evidence_and_source_are_allowed():
    checker.check_names(
        {"src/audio_transcriber/cli.py", "host-validation/evidence/2026-10-02/results.json"},
        {"src/audio_transcriber/cli.py"},
    )
