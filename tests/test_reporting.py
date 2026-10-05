"""Deterministic tests for machine-readable requested/actual device reporting."""

from __future__ import annotations

from types import SimpleNamespace

from audio_transcriber.cli import report_session


def make_session(
    *,
    actual: str = "CPU",
    requested: str = "auto",
    chunks: int = 4,
    fallbacks: int = 0,
    status: str = "ready",
):
    return SimpleNamespace(
        id="abc123def456",
        status=status,
        diagnostics={
            "actual_device": actual,
            "requested_device": requested,
            "chunk_records": [
                {"index": i, "device_used": actual, "seconds": 0.1} for i in range(chunks)
            ],
            "fallback_events": [
                {
                    "requested_device": "NPU",
                    "failed_stage": "chunk-0",
                    "error_category": "device-unavailable",
                }
                for _ in range(fallbacks)
            ],
            "inference_seconds": 1.5,
            "source_duration_seconds": 95.0,
        },
    )


def test_stable_report_includes_requested_and_actual(capsys) -> None:
    report_session(make_session(actual="CPU", requested="auto"))
    out = capsys.readouterr().out
    assert "actual_device: CPU" in out
    assert "requested_device: auto" in out
    assert "chunks_completed: 4" in out
    assert "fallback_events: 0" in out
    assert "inference_seconds: 1.5" in out
    assert "source_duration_seconds: 95.0" in out


def test_fallback_provenance_visible_in_report(capsys) -> None:
    report_session(make_session(actual="CPU", requested="NPU", fallbacks=2))
    out = capsys.readouterr().out
    assert "fallback_events: 2" in out
    # Never silently relabelled: requested NPU, actual CPU are both present.
    assert "actual_device: CPU" in out
    assert "requested_device: NPU" in out


def test_unknown_provenance_never_claims_a_device(capsys) -> None:
    partial = make_session()
    partial.diagnostics = {}
    report_session(partial)
    out = capsys.readouterr().out
    assert "actual_device: unknown" in out
    assert "NPU success" not in out
