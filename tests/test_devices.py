from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio_transcriber.devices import (
    Benchmark,
    cache_key,
    choose_device,
    device_order,
    load_cached,
    run_benchmark,
    save_cached,
)


def test_run_benchmark_separates_warmup_and_records_runs() -> None:
    calls = {"n": 0}

    def workload(device: str) -> float:
        calls["n"] += 1
        return 0.1 * calls["n"]

    result = run_benchmark(workload, "cpu", warmups=1, runs=3)
    assert calls["n"] == 4
    assert result.warmup_seconds == pytest.approx(0.1)
    assert result.runs_seconds == pytest.approx((0.2, 0.3, 0.4))
    assert result.median_seconds == pytest.approx(0.3)
    assert result.actual_device == "CPU"


def test_run_benchmark_failure_records_category() -> None:
    def workload(device: str) -> float:
        raise RuntimeError(f"requested device {device} is unavailable: []")

    result = run_benchmark(workload, "NPU", runs=1)
    assert not result.succeeded
    assert result.actual_device == "unverified"
    assert result.fallback_reason == "device-unavailable"


def test_device_order_excludes_unverified() -> None:
    results = [
        Benchmark("NPU", "speech-chunk", float("inf"), "unverified", succeeded=False),
        Benchmark("GPU", "speech-chunk", 0.3, "GPU"),
        Benchmark("CPU", "speech-chunk", 0.6, "CPU"),
    ]
    assert device_order(results) == ["GPU", "CPU"]
    with pytest.raises(ValueError):
        choose_device(results, "manual", "NPU")


def test_benchmark_cache_invalidates_on_identity_change(tmp_path: Path) -> None:
    key_a = cache_key("model-a", "2026.3.0", "cpu-x")
    results = [Benchmark("CPU", "speech-chunk", 0.4, "CPU")]
    path = tmp_path / "cache.json"
    save_cached(path, key_a, results)
    assert load_cached(path, key_a) == results
    # Any identity change (new model, runtime, or driver/device) invalidates.
    key_b = cache_key("model-b", "2026.3.0", "cpu-x")
    key_c = cache_key("model-a", "2026.5.0", "cpu-x")
    key_d = cache_key("model-a", "2026.3.0", "npu-1")
    for stale in (key_b, key_c, key_d):
        assert load_cached(path, stale) is None
    data = json.loads(path.read_text())
    assert list(data.values())[0]["key"] == key_a


def test_choose_device_policies() -> None:
    results = [
        Benchmark("NPU", "speech", 0.25, "NPU"),
        Benchmark("CPU", "speech", 0.5, "CPU"),
    ]
    assert choose_device(results, "fastest") == "NPU"
    assert choose_device(results, "efficient") == "NPU"
    slow_npu = [
        Benchmark("NPU", "speech", 1.4, "NPU"),
        Benchmark("CPU", "speech", 0.5, "CPU"),
    ]
    assert choose_device(slow_npu, "fastest") == "CPU"
