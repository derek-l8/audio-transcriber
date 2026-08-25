"""Measured device policy: benchmarking, caching, selection, and fallback order."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

Policy = Literal["fastest", "efficient", "manual"]

BENCHMARK_VERSION = "bench-v1"

PathLike = str | Path


@dataclass(frozen=True)
class Benchmark:
    device: str
    workload: str
    median_seconds: float
    actual_device: str
    runs_seconds: tuple[float, ...] = ()
    warmup_seconds: float | None = None
    succeeded: bool = True
    fallback_reason: str | None = None


def run_benchmark(
    workload: Callable[[str], float],
    device: str,
    workload_name: str = "speech",
    warmups: int = 1,
    runs: int = 3,
) -> Benchmark:
    """Compile and measure one device separately from warmup.

    `workload` must compile the model for the requested device, complete real
    inference, and return its elapsed seconds; it should raise when the device
    fails. The returned value is treated as the authoritative duration so each
    engine can measure itself consistently.
    """
    try:
        warmup_seconds: float | None = None
        if warmups:
            warmup_seconds = float(workload(device))
        measured = [float(workload(device)) for _ in range(runs)]
        median = sorted(measured)[len(measured) // 2]
        return Benchmark(
            device.upper(),
            workload_name,
            median,
            device.upper(),
            tuple(measured),
            warmup_seconds,
        )
    except Exception as error:  # noqa: BLE001 - any failure disqualifies the device
        return Benchmark(
            device.upper(),
            workload_name,
            float("inf"),
            "unverified",
            (),
            None,
            False,
            _category(error),
        )


def choose_device(results: list[Benchmark], policy: Policy, manual: str | None = None) -> str:
    valid = [r for r in results if r.succeeded and r.actual_device == r.device]
    if policy == "manual":
        if manual is None or manual not in {r.device for r in valid}:
            raise ValueError("manual device has no verified successful benchmark")
        return manual
    if not valid:
        raise RuntimeError("no verified device benchmark")
    ranked = sorted(valid, key=lambda r: r.median_seconds)
    fastest = ranked[0]
    if policy == "efficient":
        npu = next((r for r in valid if r.device == "NPU"), None)
        if npu and npu.median_seconds <= fastest.median_seconds * 1.25:
            return "NPU"
    return fastest.device


def device_order(results: Sequence[Benchmark]) -> list[str]:
    """Verified devices fastest-first; the fallback sequence during transcription."""
    verified = [r for r in results if r.succeeded and r.actual_device == r.device]
    return [r.device for r in sorted(verified, key=lambda r: r.median_seconds)]


def cache_key(model_integrity: str, runtime_version: str, device_identity: str) -> dict[str, str]:
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "model_integrity": model_integrity,
        "runtime_version": runtime_version,
        "device_identity": device_identity,
    }


def load_cached(path: PathLike, key: dict[str, str]) -> list[Benchmark] | None:
    """Return cached benchmarks only when every identity component still matches."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entry = data.get(_key_id(key))
    if not isinstance(entry, dict):
        return None
    try:
        return [
            Benchmark(
                item["device"],
                item["workload"],
                item["median_seconds"],
                item["actual_device"],
                tuple(item.get("runs_seconds", ())),
                item.get("warmup_seconds"),
                item["succeeded"],
                item.get("fallback_reason"),
            )
            for item in entry["benchmarks"]
        ]
    except (KeyError, TypeError):
        return None


def save_cached(path: PathLike, key: dict[str, str], results: Sequence[Benchmark]) -> None:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    data[_key_id(key)] = {
        "key": key,
        "benchmarks": [_benchmark_dict(b) for b in results],
    }
    from .storage import atomic_json

    atomic_json(path, data)


def _benchmark_dict(benchmark: Benchmark) -> dict[str, Any]:
    value = asdict(benchmark)
    value["runs_seconds"] = list(value["runs_seconds"])
    return value


def _key_id(key: dict[str, str]) -> str:
    import hashlib

    return hashlib.sha256("\n".join(f"{k}={key[k]}" for k in sorted(key)).encode()).hexdigest()[:16]


def _category(error: Exception) -> str:
    text = str(error).lower()
    if "unavailable" in text or "not found" in text or "enumerate" in text:
        return "device-unavailable"
    if "compile" in text:
        return "compile-failure"
    if "timeout" in text:
        return "inference-timeout"
    return "inference-failure"
