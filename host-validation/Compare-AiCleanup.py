"""Compare local cleanup outputs and warmed latency on matched cases/devices.

Case sources may be private. Results contain source text and generated text;
keep them outside Git until reviewed. This never downloads model assets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from npu_scribe.acquisition import get_spec, verify_installed
from npu_scribe.ai_cleanup import (
    DEFAULT_MODEL,
    PROMPT_VERSION,
    LocalCleanupModel,
    check_candidate,
    split_text,
)
from npu_scribe.storage import atomic_json


def failures(case: dict, text: str, category: str) -> list[str]:
    result = []
    for pattern in case.get(category + "_required", []):
        if not re.search(pattern, text, re.I | re.S | re.M):
            result.append("missing: " + pattern)
    for pattern in case.get(category + "_forbidden", []):
        if re.search(pattern, text, re.I | re.S | re.M):
            result.append("unexpected: " + pattern)
    return result


def worker(args: argparse.Namespace, cases: list[dict]) -> None:
    import openvino as ov
    import openvino_genai as genai

    model = LocalCleanupModel(
        args.model_root / DEFAULT_MODEL, args.device, args.cache_root / args.device
    )
    report = dict(
        device=args.device,
        pass_number=args.pass_number,
        model=DEFAULT_MODEL,
        model_revision=get_spec(DEFAULT_MODEL).revision,
        prompt_version=PROMPT_VERSION,
        runtime=dict(openvino=ov.__version__, genai=genai.__version__),
        cases_sha256=hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        cache_policy="reuse existing compilation cache; no claim of cold startup",
        rows=[],
    )
    started = time.perf_counter()
    warmup = model.generate(
        "Um, the measured voltage is 2 volts, and we do not infer causation.", "lecture", "light"
    )
    report.update(
        load_seconds=model.load_seconds,
        startup_and_warmup_seconds=time.perf_counter() - started,
        warmup_output=warmup,
    )
    atomic_json(args.output, report)
    ordered = cases if args.pass_number == 1 else list(reversed(cases))
    for case in ordered:
        started = time.perf_counter()
        cpu_started = time.process_time()
        row = dict(
            id=case["id"],
            mode=case["mode"],
            style=case["style"],
            source=case["source"],
            candidates=[],
            final_blocks=[],
            warnings=[],
        )
        try:
            for block in split_text(case["source"]):
                candidate = model.generate(block, case["mode"], case["style"])
                warnings = check_candidate(block, candidate, case["mode"])
                row["candidates"].append(candidate)
                row["final_blocks"].append(block if warnings else candidate)
                row["warnings"].append(warnings)
            raw = "\n\n".join(row.pop("candidates"))
            final = "\n\n".join(row.pop("final_blocks"))
            row.update(
                candidate=raw,
                final=final,
                candidate_content_failures=failures(case, raw, "content"),
                final_content_failures=failures(case, final, "content"),
                candidate_formatting_failures=failures(case, raw, "formatting"),
                final_formatting_failures=failures(case, final, "formatting"),
            )
        except Exception as error:
            row["error"] = str(error)
        row.update(
            seconds=time.perf_counter() - started,
            process_cpu_seconds=time.process_time() - cpu_started,
        )
        report["rows"].append(row)
        atomic_json(args.output, report)
        print(
            json.dumps(
                dict(
                    device=args.device,
                    pass_number=args.pass_number,
                    id=case["id"],
                    seconds=round(row["seconds"], 3),
                    content_failures=len(row.get("final_content_failures", [])),
                    formatting_failures=len(row.get("final_formatting_failures", [])),
                    used_source=any(row["warnings"]),
                    error=row.get("error"),
                )
            ),
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("CPU", "GPU", "NPU"))
    parser.add_argument("--pass-number", type=int, default=1)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if args.device:
        worker(args, cases)
        return
    if verify_installed(args.model_root, get_spec(DEFAULT_MODEL)) is None:
        raise RuntimeError("The pinned cleanup model must already be installed")
    args.output.mkdir(parents=True, exist_ok=True)
    # Fresh worker per device/pass frees device memory and model state.
    for number, devices in ((1, ("CPU", "GPU", "NPU")), (2, ("NPU", "GPU", "CPU"))):
        for device in devices:
            destination = args.output / f"run-{number:02}-{device}.json"
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--cases",
                str(args.cases.resolve()),
                "--model-root",
                str(args.model_root.resolve()),
                "--cache-root",
                str(args.cache_root.resolve()),
                "--output",
                str(destination.resolve()),
                "--device",
                device,
                "--pass-number",
                str(number),
            ]
            print(f"Starting matched pass {number}: {device}", flush=True)
            result = subprocess.run(  # noqa: S603 - this script and explicit local arguments
                command, check=False, env=os.environ.copy(), timeout=1800
            )
            if result.returncode:
                raise RuntimeError(f"{device} pass {number} failed: {result.returncode}")
    print("All matched runs complete.", flush=True)


if __name__ == "__main__":
    main()
