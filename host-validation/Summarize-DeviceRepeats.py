"""Compare one repeated lecture clip with the earlier full device evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MODELS = ("tiny", "base")
DEVICES = ("cpu", "gpu", "npu")
CASE_ID = "lec08-op-amps"


def result(path: Path) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    matches = [row for row in report["results"] if row["case_id"] == CASE_ID]
    if len(matches) != 1 or matches[0]["status"] != "measured":
        raise ValueError(f"Expected one measured {CASE_ID} result in {path}")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prior_reports", type=Path)
    parser.add_argument("repeat_reports", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rows = []
    for model in MODELS:
        for device in DEVICES:
            prior_name = f"{model}-{device}"
            if prior_name == "tiny-npu":
                prior_name = "tiny-npu-fixed"
            first = result(args.prior_reports / f"{prior_name}.report.json")
            repeat = result(args.repeat_reports / f"{model}-{device}.report.json")
            for run, item in (("initial", first), ("repeat", repeat)):
                if (
                    item["requested_device"] != device.upper()
                    or item["actual_device"] != device.upper()
                ):
                    raise ValueError(f"Device mismatch: {model} {device} {run}")
                rows.append(
                    {
                        "model": model,
                        "device": device.upper(),
                        "run": run,
                        "audio_seconds": item["audio_seconds"],
                        "inference_seconds": item["inference_seconds"],
                        "rtf": item["rtf"],
                        "status": item["status"],
                    }
                )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"case_id": CASE_ID, "rows": rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    for model in MODELS:
        for device in DEVICES:
            pair = [r for r in rows if r["model"] == model and r["device"] == device.upper()]
            print(model, device, "RTF", *(r["rtf"] for r in pair))


if __name__ == "__main__":
    main()
