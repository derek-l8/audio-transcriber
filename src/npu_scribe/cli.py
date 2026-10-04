"""Command-line interface for Milestone 1 batch transcription.

Exit codes: 0 success, 1 operational failure, 2 argument errors, 130 safe pause.
Ordinary transcription never performs network activity; network is used only by
the explicit `models download` and `evaluate` commands.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeAlias

from .acquisition import MANIFEST, AcquisitionError, download_model, get_spec, verify_installed
from .ai_cleanup import (
    DEFAULT_MODEL,
    CleanupCancelled,
    cleanup_session,
    cleanup_text,
    make_model,
    text_sha256,
)
from .checkpoint import CheckpointError
from .chunking import DEFAULT_OVERLAP_SECONDS
from .config import PROCESSING_DEFAULTS
from .devices import Benchmark, cache_key, choose_device, load_cached, run_benchmark, save_cached
from .engines import MockSpeechEngine, OpenVINOWhisperEngine
from .export import ExportError, write_export
from .formatting import STYLES as FORMAT_STYLES
from .formatting import format_session
from .media import MediaError
from .pipeline import BatchOptions, BatchRunner, PipelineError
from .storage import SessionStore


def default_data_dir() -> Path:
    import os

    override = os.environ.get("NPUSCRIBE_DATA_DIR")
    if override:
        return Path(override)
    try:
        import platformdirs

        return Path(platformdirs.user_data_path("npu-scribe", appauthor=False))
    except Exception:  # noqa: BLE001 - fall back beside the platform default
        return Path.home() / ".local" / "share" / "npu-scribe"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="npu-scribe")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--model-root", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    models = subparsers.add_parser("models", help="list or download approved models")
    models_sub = models.add_subparsers(dest="models_command", required=True)
    models_sub.add_parser("list")
    models_download = models_sub.add_parser("download")
    models_download.add_argument("model_id")

    subparsers.add_parser("devices", help="enumerate devices and cached benchmarks")

    transcribe = subparsers.add_parser("transcribe")
    transcribe.add_argument("input", type=Path)
    add_run_arguments(transcribe)

    resume = subparsers.add_parser("resume")
    resume.add_argument("session_id")
    add_run_arguments(resume)

    export_cmd = subparsers.add_parser("export")
    export_cmd.add_argument("session_id")
    export_cmd.add_argument("--format", required=True, choices=["json", "markdown", "text", "srt"])
    export_cmd.add_argument(
        "--layer",
        default="raw",
        choices=["raw", "balanced", "edited", "ai", "summary", "formatted"],
    )
    export_cmd.add_argument("--overwrite", action="store_true")

    cleanup = subparsers.add_parser("cleanup", help="create a separate AI-cleaned session version")
    cleanup.add_argument("session_id")
    add_cleanup_arguments(cleanup)
    cleanup.add_argument("--stop-file", type=Path, default=None)
    cleanup.add_argument("--formatting", choices=("off", *FORMAT_STYLES), default="off")

    formatting = subparsers.add_parser(
        "format", help="save a complete transcript with a separate layout"
    )
    formatting.add_argument("session_id")
    formatting.add_argument("--source", choices=("raw", "balanced", "ai"), default="ai")
    formatting.add_argument("--style", choices=FORMAT_STYLES, default="prose")
    formatting.add_argument("--model", default=DEFAULT_MODEL)
    formatting.add_argument("--device", choices=("AUTO", "CPU", "GPU", "NPU"), default="AUTO")
    formatting.add_argument("--stop-file", type=Path, default=None)

    summary = subparsers.add_parser("summarize", help="save separate study notes from a session")
    summary.add_argument("session_id")
    summary.add_argument("--model", default=DEFAULT_MODEL)
    summary.add_argument("--device", choices=("AUTO", "CPU", "GPU", "NPU"), default="AUTO")
    summary.add_argument("--stop-file", type=Path, default=None)
    summary.set_defaults(mode="summary", style="light")

    text_cleanup = subparsers.add_parser(
        "cleanup-text", help="clean a local UTF-8 text file with a local model"
    )
    text_cleanup.add_argument("input", type=Path)
    text_cleanup.add_argument("--output", type=Path, required=True)
    text_cleanup.add_argument("--format", choices=("text", "json"), default="text")
    text_cleanup.add_argument("--overwrite", action="store_true")
    add_cleanup_arguments(text_cleanup)

    evaluation = subparsers.add_parser("evaluate")
    evaluation.add_argument("manifest", type=Path)
    evaluation.add_argument("--model", default=None)
    evaluation.add_argument("--device", default="auto")
    evaluation.add_argument("--overlap-seconds", type=float, default=DEFAULT_OVERLAP_SECONDS)
    evaluation.add_argument(
        "--chunk-strategy", choices=("fixed", "pause-v1", "pause-v2"), default="fixed"
    )
    return parser


def add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--model",
        default="whisper-tiny.en-int4-ov",
        help="installed speech model (mock is an explicit synthetic test fixture)",
    )
    parser.add_argument("--device", default="CPU")
    parser.add_argument("--chunk-seconds", type=float, default=30.0)
    parser.add_argument("--overlap-seconds", type=float, default=DEFAULT_OVERLAP_SECONDS)
    parser.add_argument(
        "--chunk-strategy", choices=("fixed", "pause-v1", "pause-v2"), default="fixed"
    )
    parser.add_argument("--ffmpeg", default=None)
    parser.add_argument(
        "--cleanup",
        choices=("off", "light", "medium"),
        default=None,
        help="cleanup level (default: light for lectures, medium for dictation)",
    )
    parser.add_argument(
        "--formatting",
        choices=("off", *FORMAT_STYLES),
        default=None,
        help="layout (default: structured for lectures, prose for dictation; off with cleanup off)",
    )
    parser.add_argument("--formatting", choices=("off", *FORMAT_STYLES), default="off")
    parser.add_argument("--cleanup-model", default=DEFAULT_MODEL)
    parser.add_argument("--cleanup-device", choices=("AUTO", "CPU", "GPU", "NPU"), default="AUTO")
    parser.add_argument("--cleanup-mode", choices=("lecture", "dictation"), default="lecture")
    parser.add_argument(
        "--stop-file",
        type=Path,
        default=None,
        help="pause safely between chunks when this file exists",
    )


def add_cleanup_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--device", choices=("AUTO", "CPU", "GPU", "NPU"), default="AUTO")
    parser.add_argument("--mode", choices=("lecture", "dictation"), default="lecture")
    parser.add_argument("--style", choices=("light", "medium"), default="light")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in ("transcribe", "resume"):
        cleanup_default, formatting_default = PROCESSING_DEFAULTS[args.cleanup_mode]
        if args.cleanup is None:
            args.cleanup = cleanup_default
        if args.formatting is None:
            args.formatting = "off" if args.cleanup == "off" else formatting_default
    data_dir = (args.data_dir or default_data_dir()).expanduser()
    store = SessionStore(data_dir)
    try:
        return dispatch(args, store, data_dir)
    except CleanupCancelled as error:
        print(str(error), file=sys.stderr)
        return 130
    except (
        AcquisitionError,
        CheckpointError,
        ExportError,
        MediaError,
        PipelineError,
        FileNotFoundError,
        NotADirectoryError,
        PermissionError,
        ValueError,
        RuntimeError,
        OSError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def dispatch(args: argparse.Namespace, store: SessionStore, data_dir: Path) -> int:
    if args.command == "models":
        return run_models(args, data_dir)
    if args.command == "devices":
        return run_devices(args, store, data_dir)
    if args.command == "transcribe":
        return run_transcribe(args, store, data_dir)
    if args.command == "resume":
        return run_resume(args, store, data_dir)
    if args.command in ("cleanup", "cleanup-text", "summarize"):
        return run_cleanup(args, store, data_dir)
    if args.command == "format":
        return run_format(args, store, data_dir)
    if args.command == "export":
        path = write_export(store, args.session_id, args.layer, args.format, args.overwrite)
        print(f"exported {args.session_id} {args.layer} layer to {path.name}")
        return 0
    if args.command == "evaluate":
        return run_evaluate(args, data_dir)
    raise PipelineError(f"unknown command {args.command}")


def run_models(args: argparse.Namespace, data_dir: Path) -> int:
    if args.models_command == "list":
        for spec in MANIFEST.values():
            print(
                f"{spec.id}  {spec.role}  {spec.download_bytes / 1e6:.1f} MB  "
                f"{spec.task}  {spec.language}  {spec.license}"
            )
        return 0
    spec = get_spec(args.model_id)
    model_root = getattr(args, "model_root", None) or data_dir / "models"
    target = download_model(spec.id, model_root)
    verified = verify_installed(model_root, spec)
    print(f"model ready: {target.name}" if verified else f"model staged at {target.name}")
    return 0


def run_devices(args: argparse.Namespace, store: SessionStore, data_dir: Path) -> int:
    devices: list[str] = []
    runtime_version = "openvino-not-installed"
    try:
        import openvino as ov  # type: ignore[import-untyped]

        core = ov.Core()
        devices = list(core.available_devices)
        runtime_version = str(ov.__version__)
    except ImportError:
        pass
    print(f"runtime: {runtime_version}")
    for device in devices:
        print(f"device: {device}")
    cache_path = data_dir / "device-benchmarks.json"
    key = cache_key("any", runtime_version, ",".join(devices))
    cached = load_cached(cache_path, key)
    if cached:
        for bench in cached:
            state = "ok" if bench.succeeded else f"failed ({bench.fallback_reason})"
            print(f"cached benchmark {bench.device}: {bench.median_seconds:.3f}s [{state}]")
    return 0


EngineFactory: TypeAlias = Callable[[str], Any]


def make_engine_provider(
    model_id: str, data_dir: Path, model_root: Path | None = None
) -> EngineFactory:
    if model_id in MANIFEST:
        spec = get_spec(model_id)
        if spec.task != "speech":
            raise AcquisitionError("a cleanup model cannot be used for speech transcription")
        install = verify_installed(model_root or data_dir / "models", spec)
        if install is None:
            raise AcquisitionError(
                f"model '{model_id}' is not installed; run 'npu-scribe models download {model_id}'"
            )

        def provider(device: str) -> Any:
            return OpenVINOWhisperEngine(install, spec.id, multilingual=spec.multilingual)

        return provider
    if model_id == "mock":

        def provider(device: str) -> Any:
            return MockSpeechEngine()

        return provider
    raise AcquisitionError(
        f"model '{model_id}' is not manifest-approved; run 'npu-scribe models list'"
    )


def benchmark_devices(
    provider: EngineFactory, model_id: str, data_dir: Path, model_root: Path | None = None
) -> list[Benchmark]:
    """Same representative workload per device; warmup kept separate from runs."""
    try:
        import openvino as ov

        runtime_version = str(ov.__version__)
        devices = [d for d in ov.Core().available_devices]
    except ImportError:
        return []
    cache_path = data_dir / "device-benchmarks.json"
    key = cache_key(
        _model_identity(model_id, data_dir, model_root), runtime_version, ",".join(devices)
    )
    cached = load_cached(cache_path, key)
    if cached:
        return cached
    samples = [0.0] * 16_000

    def workload(device: str) -> float:
        import time

        started = time.perf_counter()
        provider(device).transcribe_samples(samples, device)
        return time.perf_counter() - started

    results = [
        run_benchmark(workload, device, "speech-chunk") for device in devices if device != "AUTO"
    ]
    save_cached(cache_path, key, results)
    return results


def _model_identity(model_id: str, data_dir: Path, model_root: Path | None = None) -> str:
    from .storage import sha256_file

    install = (model_root or data_dir / "models") / model_id
    if install.is_dir():
        parts = sorted(p.name for p in install.iterdir())
        return sha256_file(install / parts[0]) if parts else model_id
    return model_id


def resolve_device(
    requested: str,
    provider: EngineFactory,
    model_id: str,
    data_dir: Path,
    model_root: Path | None = None,
) -> tuple[str, list[Benchmark]]:
    is_manual = requested.upper() not in ("AUTO", "")
    if is_manual:
        return requested.upper(), []
    benchmarks = benchmark_devices(provider, model_id, data_dir, model_root)
    if benchmarks:
        # Reject an entirely failed benchmark set before creating a session.
        choose_device(benchmarks, "fastest")
    # Keep the user's policy: BatchRunner ranks and falls back among verified devices.
    return "auto", benchmarks


def run_transcribe(args: argparse.Namespace, store: SessionStore, data_dir: Path) -> int:
    model_root = getattr(args, "model_root", None)
    provider = make_engine_provider(args.model, data_dir, model_root)
    requested, benchmarks = resolve_device(args.device, provider, args.model, data_dir, model_root)
    options = BatchOptions(
        model_id=args.model,
        requested_device=requested,
        chunk_seconds=args.chunk_seconds,
        overlap_seconds=args.overlap_seconds,
        ffmpeg_path=args.ffmpeg,
        chunk_strategy=getattr(args, "chunk_strategy", "fixed"),
    )
    stop_file = getattr(args, "stop_file", None)
    runner = BatchRunner(
        store,
        provider,
        benchmarks,
        options,
        cancel_requested=stop_file.exists if stop_file else None,
    )
    session = runner.run_new(args.input)
    report_session(session)
    return finish_transcription(args, store, data_dir, session)


def run_resume(args: argparse.Namespace, store: SessionStore, data_dir: Path) -> int:
    model_root = getattr(args, "model_root", None)
    provider = make_engine_provider(args.model, data_dir, model_root)
    requested, benchmarks = resolve_device(args.device, provider, args.model, data_dir, model_root)
    options = BatchOptions(
        model_id=args.model,
        requested_device=requested,
        chunk_seconds=args.chunk_seconds,
        overlap_seconds=args.overlap_seconds,
        ffmpeg_path=args.ffmpeg,
        chunk_strategy=getattr(args, "chunk_strategy", "fixed"),
    )
    stop_file = getattr(args, "stop_file", None)
    runner = BatchRunner(
        store,
        provider,
        benchmarks,
        options,
        cancel_requested=stop_file.exists if stop_file else None,
    )
    session = runner.resume(args.session_id)
    report_session(session)
    return finish_transcription(args, store, data_dir, session)


def finish_transcription(
    args: argparse.Namespace, store: SessionStore, data_dir: Path, session: Any
) -> int:
    if session.status != "ready":
        return 130
    level = getattr(args, "cleanup", "off")
    if level == "off":
        if getattr(args, "formatting", "off") == "off":
            return 0
        return run_format(
            argparse.Namespace(
                session_id=session.id,
                source="raw",
                style=args.formatting,
                model=args.cleanup_model,
                model_root=args.model_root,
                device=args.cleanup_device,
                stop_file=getattr(args, "stop_file", None),
            ),
            store,
            data_dir,
        )
    cleanup_args = argparse.Namespace(
        command="cleanup",
        session_id=session.id,
        model=getattr(args, "cleanup_model", DEFAULT_MODEL),
        model_root=getattr(args, "model_root", None),
        device=getattr(args, "cleanup_device", "AUTO"),
        mode=getattr(args, "cleanup_mode", "lecture"),
        style=level,
        formatting=getattr(args, "formatting", "off"),
        stop_file=getattr(args, "stop_file", None),
    )
    try:
        return run_cleanup(cleanup_args, store, data_dir)
    except CleanupCancelled:
        raise
    except (RuntimeError, OSError, ValueError) as error:
        print(
            f"Transcription is ready and can be exported. Cleanup or formatting failed: {error}",
            file=sys.stderr,
        )
        return 1


def report_session(session: Any) -> None:
    """Stable machine-readable lines; the Windows harness parses the prefixes."""
    diagnostics = session.diagnostics or {}
    chunk_records = diagnostics.get("chunk_records", [])
    fallback_events = diagnostics.get("fallback_events", [])
    print(f"session: {session.id}")
    print(f"status: {session.status}")
    print(f"actual_device: {diagnostics.get('actual_device', 'unknown')}")
    print(f"requested_device: {diagnostics.get('requested_device', 'unknown')}")
    print(f"chunks_completed: {len(chunk_records)}")
    print(f"fallback_events: {len(fallback_events)}")
    inference = diagnostics.get("inference_seconds")
    if inference is not None:
        print(f"inference_seconds: {inference}")
    duration = diagnostics.get("source_duration_seconds")
    if duration is not None:
        print(f"source_duration_seconds: {duration}")
    print(f"location: lectures/{session.id}/ under the application data directory")


def run_cleanup(args: argparse.Namespace, store: SessionStore, data_dir: Path) -> int:
    stop = getattr(args, "stop_file", None)
    cancelled = stop.exists if stop else None
    model = make_model(
        args.model,
        args.model_root or data_dir / "models",
        args.device,
        data_dir / "cache" / "cleanup",
        cancelled,
    )
    if args.command in ("cleanup", "summarize"):
        path = cleanup_session(
            store,
            args.session_id,
            model,
            args.model,
            args.device,
            args.mode,
            args.style,
            cancelled,
            lambda done, total: print(f"cleanup_blocks: {done}/{total}", flush=True),
        )
        print(f"{'Summary' if args.command == 'summarize' else 'AI cleanup'} ready: {path}")
        print(f"cleanup_device: {getattr(model, 'device', args.device)}")
        if getattr(model, "fallback_reason", None):
            print(f"cleanup_fallback: {model.fallback_reason}")
        transcript = store.load_transcript(
            args.session_id, "summary" if args.command == "summarize" else "ai"
        )
        records = (transcript.transformation or {}).get("blocks", [])
        if any(record["used_source"] for record in records):
            print("Some blocks retained source text after validation warnings; review the result.")
        if args.command == "cleanup" and getattr(args, "formatting", "off") != "off":
            format_args = argparse.Namespace(
                session_id=args.session_id,
                source="ai",
                style=args.formatting,
                model=args.model,
                model_root=args.model_root,
                device=args.device,
                stop_file=stop,
            )
            return run_format(format_args, store, data_dir, model)
        return 0
    source, output = args.input.expanduser().resolve(), args.output.expanduser().resolve()
    if source == output:
        raise ValueError("cleanup output must differ from its source")
    if output.exists() and not args.overwrite:
        raise FileExistsError("cleanup output already exists; use --overwrite to replace it")
    if source.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("cleanup text input exceeds 2 MB")
    text = source.read_text(encoding="utf-8")
    cleaned, records = cleanup_text(text, model, args.mode, args.style)
    if args.format == "json":
        import json

        spec = get_spec(args.model)
        content = (
            json.dumps(
                {
                    "text": cleaned,
                    "source_sha256": text_sha256(text),
                    "mode": args.mode,
                    "style": args.style,
                    "model": args.model,
                    "model_revision": spec.revision,
                    "requested_device": args.device,
                    "actual_device": getattr(model, "device", args.device),
                    "device_fallback": getattr(model, "fallback_reason", None),
                    "blocks": records,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
    else:
        content = cleaned + "\n"
    atomic_text(output, content)
    print(f"AI cleanup ready: {output}")
    if any(record["used_source"] for record in records):
        print("Some blocks retained source text after validation warnings; review the result.")
    return 0


def run_format(
    args: argparse.Namespace, store: SessionStore, data_dir: Path, model: Any = None
) -> int:
    stop = getattr(args, "stop_file", None)
    cancelled = stop.exists if stop else None
    if args.style != "prose" and model is None:
        model = make_model(
            args.model,
            args.model_root or data_dir / "models",
            args.device,
            data_dir / "cache" / "cleanup",
            cancelled,
        )
    path = format_session(
        store,
        args.session_id,
        args.style,
        args.source,
        model,
        args.model,
        args.device,
        cancelled,
        lambda done, total: print(f"format_blocks: {done}/{total}", flush=True),
    )
    print(f"Formatted transcript ready: {path}")
    transcript = store.load_transcript(args.session_id, "formatted")
    print(f"format_device: {transcript.provenance.actual_device}")
    if any(record["used_source"] for record in (transcript.transformation or {}).get("blocks", [])):
        print("Some layouts were rejected; those blocks use complete source text in prose.")
    return 0


def run_evaluate(args: argparse.Namespace, data_dir: Path) -> int:
    from .evaluate import (
        EvaluationReport,
        evaluate_case,
        fetch_case_audio,
        load_manifest,
        select_model,
        write_report,
    )

    manifest = load_manifest(args.manifest)
    model_id = args.model or str(manifest.get("model_id", ""))
    model_root = getattr(args, "model_root", None)
    provider = make_engine_provider(model_id, data_dir, model_root)
    requested, _benchmarks = resolve_device(args.device, provider, model_id, data_dir, model_root)
    report = EvaluationReport(manifest_name=str(manifest.get("name", args.manifest.stem)))
    eval_media = data_dir / "evaluation" / "media"
    eval_store = SessionStore(data_dir)
    runner = BatchRunner(
        eval_store,
        provider,
        _benchmarks,
        BatchOptions(
            model_id=model_id,
            requested_device=requested,
            overlap_seconds=getattr(args, "overlap_seconds", DEFAULT_OVERLAP_SECONDS),
            chunk_strategy=getattr(args, "chunk_strategy", "fixed"),
        ),
    )

    for source_case in manifest["cases"]:
        case = {**source_case, "model_id": model_id, "device": requested}

        def transcribe(
            path: Path, _case: dict[str, Any] = case
        ) -> tuple[str, float, None, str, str]:
            session = runner.run_new(path)
            transcript = eval_store.load_transcript(session.id, "raw")
            inference = float(session.diagnostics["inference_seconds"])
            runtime = "unavailable"
            try:
                import openvino as ov

                runtime = str(ov.__version__)
            except ImportError:
                pass
            actual = str(session.diagnostics["actual_device"])
            return transcript.text, inference, None, actual, runtime

        audio_path = fetch_case_audio(case, eval_media)
        result = evaluate_case(case, audio_path, transcribe)
        report.results.append(result)
    report.selection = select_model(report.results)

    reports_dir = data_dir / "evaluation" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / f"{args.manifest.stem}.report.json"
    write_report(report, json_path)
    md_path = reports_dir / f"{args.manifest.stem}.report.md"
    lines = [f"# Evaluation: {report.manifest_name}", ""]
    for r in report.results:
        lines.append(
            f"- {r.case_id}: WER={r.wer} CER={r.cer} RTF={r.rtf} "
            f"device={r.actual_device} status={r.status}"
        )
    lines.append(f"- selection: {report.selection.get('selected_model_id')}")
    atomic_text(md_path, "\n".join(lines) + "\n")
    print(f"report written: {json_path.name}")
    return 1 if any(result.status != "measured" for result in report.results) else 0


def atomic_text(path: Path, content: str) -> None:
    from .storage import atomic_write

    atomic_write(path, content.encode("utf-8"))


if __name__ == "__main__":
    sys.exit(main())
