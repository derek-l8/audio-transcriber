from __future__ import annotations

import hashlib
import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from npu_scribe import cli
from npu_scribe.engines import MockSpeechEngine
from npu_scribe.evaluate import (
    CaseResult,
    EvaluationError,
    EvaluationReport,
    evaluate_case,
    fetch_case_audio,
    load_manifest,
    select_model,
    write_report,
)


def valid_case(tmp_path: Path, audio: Path) -> dict:
    return {
        "id": "case-1",
        "audio_url": audio.as_uri(),
        "audio_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
        "expected_size_bytes": audio.stat().st_size,
        "license": "CC-BY",
        "official_source": "https://example.com/lecture",
        "reference_text": "the integral of x is x squared over two",
        "reference_provenance": "official lecture transcript",
        "preparation": "decode to mono 16 kHz",
        "audio_seconds": 10.0,
        "model_id": "mock",
    }


def manifest_file(tmp_path: Path, case: dict) -> Path:
    path = tmp_path / "eval-manifest.json"
    path.write_text(
        json.dumps({"schema_version": 1, "name": "synthetic", "cases": [case]}),
        encoding="utf-8",
    )
    return path


def test_manifest_validation(tmp_path: Path, silent_wav: Path) -> None:
    load_manifest(manifest_file(tmp_path, valid_case(tmp_path, silent_wav)))
    bad = {"schema_version": 1, "name": "x", "cases": [{"id": "incomplete"}]}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(EvaluationError, match="missing fields"):
        load_manifest(path)
    path.write_text(json.dumps({"schema_version": 9, "cases": []}))
    with pytest.raises(EvaluationError, match="schema version"):
        load_manifest(path)


def test_fetch_verifies_checksum_and_size(tmp_path: Path, silent_wav: Path) -> None:
    case = valid_case(tmp_path, silent_wav)
    fetched = fetch_case_audio(case, tmp_path / "media")
    assert fetched.is_file()
    # Cached second fetch skips the network entirely.
    again = fetch_case_audio(case, tmp_path / "media")
    assert again == fetched
    tampered = dict(case)
    tampered["expected_size_bytes"] = 999
    with pytest.raises(EvaluationError, match="size mismatch"):
        fetch_case_audio(tampered, tmp_path / "media2")
    wrong_hash = dict(case)
    wrong_hash["audio_sha256"] = "0" * 64
    with pytest.raises(EvaluationError, match="SHA-256"):
        fetch_case_audio(wrong_hash, tmp_path / "media3")


def test_evaluate_case_measures_accuracy_and_speed(tmp_path: Path, silent_wav: Path) -> None:
    case = valid_case(tmp_path, silent_wav)
    case["reference_text"] = "hello world"

    def transcribe(path: Path):
        return ("hello world", 2.0, 0.5, "CPU", "test-runtime")

    result = evaluate_case(case, silent_wav, transcribe)
    assert result.status == "measured"
    assert result.wer == 0.0
    assert result.rtf == pytest.approx(0.2)
    assert result.actual_device == "CPU"
    assert result.runtime_version == "test-runtime"
    if sys.platform == "win32":
        assert result.peak_memory_mb is None
    else:
        assert result.peak_memory_mb and result.peak_memory_mb > 0


def test_selection_policy_rejects_real_time_or_slower() -> None:
    results = [
        CaseResult("a", "slow-model", "CPU", "CPU", wer=0.05, rtf=1.2),
        CaseResult("b", "slow-model", "CPU", "CPU", wer=0.02, rtf=0.4),
        CaseResult("a", "mid-model", "CPU", "CPU", wer=0.08, rtf=0.7),
        CaseResult("b", "mid-model", "CPU", "CPU", wer=0.08, rtf=0.7),
        CaseResult("a", "good-model", "CPU", "CPU", wer=0.12, rtf=0.4),
        CaseResult("b", "good-model", "CPU", "CPU", wer=0.12, rtf=0.4),
        CaseResult("a", "better-wer", "CPU", "CPU", wer=0.03, rtf=0.45),
        CaseResult("b", "better-wer", "CPU", "CPU", wer=0.13, rtf=0.45),
    ]
    selection = select_model(results)
    assert selection["rejected_real_time_or_slower"] == ["slow-model"]
    assert selection["preferred_rtf_le_05"] is True
    # Among complete preferred models, lowest mean WER wins.
    assert selection["selected_model_id"] == "better-wer"


def test_selection_without_representative_results_declares_nothing() -> None:
    empty = select_model([])
    assert empty["selected_model_id"] is None
    assert "at least two models" in empty["note"]
    only_slow = select_model([CaseResult("a", "m", "auto", "CPU", wer=0.1, rtf=2.0)])
    assert only_slow["eligible_ids"] == []
    only_fast = select_model([CaseResult("a", "m", "CPU", "CPU", wer=0.1, rtf=0.2)])
    assert only_fast["selected_model_id"] is None


def test_selection_requires_matched_cases() -> None:
    results = [
        CaseResult("a", "tiny", "CPU", "CPU", wer=0.1, rtf=0.3),
        CaseResult("a", "base", "CPU", "CPU", wer=0.05, rtf=0.4),
        CaseResult("b", "base", "CPU", "CPU", wer=0.05, rtf=0.4),
    ]
    assert select_model(results)["selected_model_id"] is None


def test_report_write_is_atomic_json(tmp_path: Path) -> None:
    report = EvaluationReport(manifest_name="demo", results=[], selection={})
    destination = tmp_path / "report.json"
    write_report(report, destination)
    value = json.loads(destination.read_text())
    assert value["manifest"] == "demo"


def test_failed_evaluation_writes_report_and_returns_failure(
    tmp_path: Path, silent_wav: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingEngine(MockSpeechEngine):
        def transcribe_samples(self, samples: list[float], device: str = "CPU"):
            raise RuntimeError("synthetic inference failure")

    monkeypatch.setattr(
        cli,
        "make_engine_provider",
        lambda model_id, data_dir, model_root=None: lambda device: FailingEngine(),
    )
    monkeypatch.setattr(cli, "resolve_device", lambda *args: ("CPU", []))
    manifest = manifest_file(tmp_path, valid_case(tmp_path, silent_wav))
    result = cli.run_evaluate(
        Namespace(manifest=manifest, model="mock", device="CPU"), tmp_path / "data"
    )
    report = json.loads(
        (tmp_path / "data" / "evaluation" / "reports" / "eval-manifest.report.json").read_text()
    )
    assert result == 1
    assert report["results"][0]["status"] == "failed"
    assert report["selection"]["selected_model_id"] is None
