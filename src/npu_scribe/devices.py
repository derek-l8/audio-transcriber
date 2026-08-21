from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Policy = Literal["fastest", "efficient", "manual"]


@dataclass(frozen=True)
class Benchmark:
    device: str
    workload: str
    median_seconds: float
    actual_device: str
    succeeded: bool = True
    fallback_reason: str | None = None


def choose_device(results: list[Benchmark], policy: Policy, manual: str | None = None) -> str:
    valid = [r for r in results if r.succeeded and r.actual_device == r.device]
    if policy == "manual":
        if manual is None or manual not in {r.device for r in valid}:
            raise ValueError("manual device has no verified successful benchmark")
        return manual
    if not valid:
        raise RuntimeError("no verified device benchmark")
    fastest = min(valid, key=lambda r: r.median_seconds)
    if policy == "efficient":
        npu = next((r for r in valid if r.device == "NPU"), None)
        if npu and npu.median_seconds <= fastest.median_seconds * 1.25:
            return "NPU"
    return fastest.device
