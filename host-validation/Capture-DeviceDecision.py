"""Record sanitized OpenVINO device identity and cached auto selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from npu_scribe.cli import make_engine_provider, resolve_device

MODELS = ("whisper-tiny.en-int4-ov", "whisper-base.en-int4-ov")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    import openvino as ov
    import openvino_genai

    core = ov.Core()
    available = list(core.available_devices)
    npu = {}
    if "NPU" in available:
        for key in (
            "FULL_DEVICE_NAME",
            "DEVICE_ARCHITECTURE",
            "NPU_DRIVER_VERSION",
            "NPU_COMPILER_TYPE",
            "NPU_COMPILER_VERSION",
        ):
            npu[key] = str(core.get_property("NPU", key))
    decisions = {}
    for model in MODELS:
        chosen, benchmarks = resolve_device(
            "auto", make_engine_provider(model, args.data_dir), model, args.data_dir
        )
        decisions[model] = {
            "auto_device": chosen,
            "benchmarks": [
                {
                    "device": item.device,
                    "workload": item.workload,
                    "median_seconds": item.median_seconds,
                    "succeeded": item.succeeded,
                }
                for item in benchmarks
            ],
        }
    report = {
        "openvino": str(ov.__version__),
        "openvino_genai": str(getattr(openvino_genai, "__version__", "unavailable")),
        "available_devices": available,
        "npu": npu,
        "decisions": decisions,
        "limitation": (
            "Automatic selection uses the application's one-second silence "
            "benchmark. It is not a sustained lecture performance benchmark."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for model, decision in decisions.items():
        print(model, decision["auto_device"])


if __name__ == "__main__":
    main()
