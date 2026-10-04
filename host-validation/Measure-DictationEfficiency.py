"""Measure reusable speech/cleanup workers without downloading models.

Inputs JSON: [{"id": "clip-a", "audio": "...wav"}]. Optional "text" supplies
fixed raw text for cleanup-only runs. Private output contains speech; keep it
outside Git. The report contains timings, resource measurements, and hashes.
Requires psutil and, for faster-whisper, its optional comparison dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
import threading
import time
from pathlib import Path


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def versions() -> dict[str, str]:
    found = {}
    for name in (
        "openvino",
        "openvino-genai",
        "faster-whisper",
        "ctranslate2",
        "psutil",
        "numpy",
        "av",
    ):
        try:
            found[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--speech-model", type=Path)
    parser.add_argument("--cleanup-model", type=Path)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--device", choices=("CPU", "GPU", "NPU"), default="GPU")
    parser.add_argument("--engine", choices=("openvino", "faster-whisper"), default="openvino")
    parser.add_argument("--mode", choices=("speech", "cleanup", "combined"), default="combined")
    parser.add_argument("--order", required=True, help="Comma-separated input IDs")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--beam", type=int, default=1)
    parser.add_argument("--deps", type=Path)
    args = parser.parse_args()
    if args.report.resolve() == args.private_output.resolve():
        parser.error("Report and private output must be different files")
    if args.threads < 1 or args.beam < 1:
        parser.error("Threads and beam must be positive")
    if args.mode != "cleanup" and not args.speech_model:
        parser.error("This mode requires --speech-model")
    if args.mode != "speech" and not args.cleanup_model:
        parser.error("This mode requires --cleanup-model")
    if args.deps:
        sys.path.insert(0, str(args.deps.resolve()))
    import psutil

    from npu_scribe.ai_cleanup import LocalCleanupModel, check_candidate, split_text
    from npu_scribe.engines import OpenVINOWhisperEngine

    cases = {c["id"]: c for c in json.loads(args.inputs.read_text(encoding="utf-8-sig"))}
    process = psutil.Process()
    samples: list[dict] = []
    stopping = threading.Event()
    logical = psutil.cpu_count() or 1

    def sample() -> None:
        while not stopping.is_set():
            cpu = process.cpu_times()
            mem = process.memory_info()
            samples.append(
                dict(
                    t=time.perf_counter(),
                    cpu=cpu.user + cpu.system,
                    rss=mem.rss,
                    private=getattr(mem, "private", mem.vms),
                )
            )
            stopping.wait(0.1)

    observer = threading.Thread(target=sample, daemon=True)
    observer.start()
    speech = None
    cleanup = None
    report = dict(
        mode=args.mode,
        engine=args.engine,
        cleanup_device=args.device,
        versions=versions(),
        speech_model=args.speech_model.name if args.speech_model else None,
        cleanup_model=args.cleanup_model.name
        if args.cleanup_model and args.mode != "speech"
        else None,
        threads=args.threads if args.engine == "faster-whisper" else None,
        beam=args.beam if args.engine == "faster-whisper" else None,
        logical_cpus=logical,
        total_ram_bytes=psutil.virtual_memory().total,
        sample_interval_seconds=0.1,
        rows=[],
        scope="Worker RSS/private memory; CPU normalized across all logical CPUs. "
        "Driver/GPU allocations and app GUI are not fully captured. "
        "Existing compilation and filesystem caches may be reused.",
    )
    private = []
    process_started = time.perf_counter()
    try:
        for call, case_id in enumerate(args.order.split(",")):
            case = cases[case_id]
            started = time.perf_counter()
            wall_started = time.time()
            cpu0 = time.process_time()
            load = 0.0
            raw = case.get("text", "")
            if args.mode != "cleanup":
                if speech is None:
                    init = time.perf_counter()
                    if args.engine == "openvino":
                        speech = OpenVINOWhisperEngine(args.speech_model)
                    else:
                        from faster_whisper import WhisperModel

                        speech = WhisperModel(
                            str(args.speech_model),
                            device="cpu",
                            compute_type="int8",
                            cpu_threads=args.threads,
                            num_workers=1,
                            local_files_only=True,
                        )
                    load += time.perf_counter() - init
                speech_started = time.perf_counter()
                if args.engine == "openvino":
                    result = speech.transcribe(Path(case["audio"]), "CPU")
                    raw = " ".join(s.text for s in result.segments)
                else:
                    import numpy as np

                    audio_samples = np.asarray(
                        OpenVINOWhisperEngine._read_samples(Path(case["audio"])), dtype=np.float32
                    )
                    segments, _ = speech.transcribe(
                        audio_samples,
                        beam_size=args.beam,
                        language="en",
                        vad_filter=False,
                        condition_on_previous_text=False,
                    )
                    raw = " ".join(s.text.strip() for s in segments)
                speech_seconds = time.perf_counter() - speech_started
            else:
                speech_seconds = 0.0
            final = raw
            candidates = []
            warnings = []
            cleanup_started = time.perf_counter()
            if args.mode != "speech":
                if cleanup is None:
                    cleanup = LocalCleanupModel(args.cleanup_model, args.device, args.cache)
                old_load = cleanup.load_seconds
                blocks = []
                for block in split_text(raw):
                    candidate = cleanup.generate(block, "dictation", "light")
                    reasons = check_candidate(block, candidate, "dictation")
                    candidates.append(candidate)
                    warnings.append(reasons)
                    blocks.append(block if reasons else candidate)
                final = "\n\n".join(blocks)
                load += cleanup.load_seconds - old_load
            cleanup_seconds = time.perf_counter() - cleanup_started
            elapsed = time.perf_counter() - started
            selected = [s for s in samples if s["t"] >= started]
            memory = process.memory_info()
            row = dict(
                call=call,
                id=case_id,
                wall_started=wall_started,
                wall_finished=time.time(),
                seconds=elapsed,
                speech_seconds=speech_seconds,
                cleanup_seconds=cleanup_seconds,
                model_init_seconds=load,
                cpu_percent=100 * (time.process_time() - cpu0) / elapsed / logical,
                peak_rss_bytes=max([s["rss"] for s in selected] + [memory.rss]),
                peak_private_bytes=max(
                    [s["private"] for s in selected] + [getattr(memory, "private", memory.vms)]
                ),
                held_rss_bytes=memory.rss,
                raw_words=len(raw.split()),
                final_words=len(final.split()),
                raw_sha256=digest(raw),
                final_sha256=digest(final),
                warnings=warnings,
            )
            report["rows"].append(row)
            private.append(
                dict(
                    call=call,
                    id=case_id,
                    raw=raw,
                    final=final,
                    candidates=candidates,
                    warnings=warnings,
                )
            )
            save(args.report, report)
            save(args.private_output, private)
            print(
                json.dumps(
                    dict(
                        call=call,
                        id=case_id,
                        seconds=round(elapsed, 3),
                        cpu_percent=round(row["cpu_percent"], 1),
                        rss_gib=round(memory.rss / 1024**3, 2),
                    )
                ),
                flush=True,
            )
        idle_started = time.perf_counter()
        idle_cpu = time.process_time()
        stopping.wait(2)
        report["idle"] = dict(
            wall_started=time.time() - (time.perf_counter() - idle_started),
            wall_finished=time.time(),
            seconds=time.perf_counter() - idle_started,
            cpu_percent=100
            * (time.process_time() - idle_cpu)
            / (time.perf_counter() - idle_started)
            / logical,
            held_rss_bytes=process.memory_info().rss,
        )
        report["worker_seconds"] = time.perf_counter() - process_started
    finally:
        stopping.set()
        observer.join(timeout=2)
        save(args.report, report)
        save(args.private_output, private)


if __name__ == "__main__":
    main()
