"""Compare chunk overlaps or fixed/pause boundaries through BatchRunner.

Each model is warmed once and reused on explicit CPU. Paired conditions run
in reverse order on alternate repeats. Public output contains numeric results;
raw chunk text and session output go only under the supplied local data root.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from npu_scribe.acquisition import get_spec, verify_installed
from npu_scribe.chunking import ChunkSpec, iter_source_windows, plan_chunks, read_chunk
from npu_scribe.engines import OpenVINOWhisperEngine
from npu_scribe.media import PcmWavDecoder
from npu_scribe.metrics import _distance
from npu_scribe.pipeline import BatchOptions, BatchRunner
from npu_scribe.storage import SessionStore, atomic_json, sha256_file

MODELS = ("whisper-tiny.en-int4-ov", "whisper-base.en-int4-ov")
TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)*")


def words(text: str) -> list[str]:
    return TOKEN.findall(text.casefold())


class RecordChunks:
    def __init__(self, engine, windows):
        self.engine = engine
        self.windows = windows
        self.chunks = []

    def transcribe_samples(self, samples, device):
        window = self.windows[len(self.chunks)]
        result = self.engine.transcribe_samples(samples, device)
        self.chunks.append(
            {
                "index": window.index,
                "start": window.start_seconds,
                "end": window.end_seconds,
                "segments": [
                    {
                        "start": s.start + window.start_seconds,
                        "end": s.end + window.start_seconds,
                        "text": s.text,
                    }
                    for s in result.segments
                ],
            }
        )
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("model_root", type=Path)
    parser.add_argument("data_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--comparison", choices=("overlap", "pause"), default="overlap")
    parser.add_argument("--strategies", nargs="+", choices=("fixed", "pause-v1", "pause-v2"))
    parser.add_argument("--models", nargs="+", choices=MODELS)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    index_path = args.data_root / "run-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else []
    rows = []
    if args.output.is_file():
        rows = json.loads(args.output.read_text(encoding="utf-8"))["rows"]
    store = SessionStore(args.data_root)
    for model_id in args.models or MODELS:
        spec = get_spec(model_id)
        model_dir = verify_installed(args.model_root, spec)
        if model_dir is None:
            raise ValueError(f"Pinned model is not verified: {model_id}")
        engine = OpenVINOWhisperEngine(model_dir, model_id)
        warmed = False
        for case in manifest["cases"]:
            parsed = urlparse(case["audio_url"])
            if parsed.scheme != "file":
                raise ValueError("This offline comparison requires local WAVs")
            audio = Path(url2pathname(parsed.path))
            if sha256_file(audio) != case["audio_sha256"]:
                raise ValueError(f"Audio hash mismatch: {case['id']}")
            frames = round(case["audio_seconds"] * 16000)
            if not warmed:
                first = plan_chunks(frames, ChunkSpec())[0]
                engine.transcribe_samples(read_chunk(audio, first), "CPU")
                warmed = True
            for repeat in range(1, args.rounds + 1):
                conditions = (
                    [(0.0, "fixed"), (1.0, "fixed")]
                    if args.comparison == "overlap"
                    else [(0.0, "fixed"), (0.0, "pause-v1")]
                )
                if args.strategies:
                    conditions = [(0.0, strategy) for strategy in args.strategies]
                if repeat % 2 == 0:
                    conditions.reverse()
                for overlap, strategy in conditions:
                    key = (model_id, case["id"], repeat, overlap, strategy)
                    if any(
                        (
                            r["model_id"],
                            r["case_id"],
                            r["repeat"],
                            r["overlap_seconds"],
                            r.get("chunk_strategy", "fixed"),
                        )
                        == key
                        for r in rows
                    ):
                        continue
                    windows = list(
                        iter_source_windows(
                            PcmWavDecoder().decode(audio),
                            ChunkSpec(overlap_seconds=overlap, strategy=strategy),
                        )
                    )
                    recording = RecordChunks(engine, windows)
                    runner = BatchRunner(
                        store,
                        lambda device, recorded_engine=recording: recorded_engine,
                        [],
                        BatchOptions(
                            model_id=model_id,
                            requested_device="CPU",
                            overlap_seconds=overlap,
                            chunk_strategy=strategy,
                        ),
                    )
                    started = time.perf_counter()
                    cpu_started = time.process_time()
                    session = runner.run_new(audio)
                    wall = time.perf_counter() - started
                    cpu = time.process_time() - cpu_started
                    transcript = store.load_transcript(session.id, "raw")
                    reference = words(case["reference_text"])
                    hypothesis = words(transcript.text)
                    errors = _distance(reference, hypothesis)
                    diagnostics = session.diagnostics
                    row = {
                        "model_id": model_id,
                        "case_id": case["id"],
                        "repeat": repeat,
                        "overlap_seconds": overlap,
                        "chunk_strategy": strategy,
                        "audio_seconds": case["audio_seconds"],
                        "audio_sha256": case["audio_sha256"],
                        "reference_words": len(reference),
                        "hypothesis_words": len(hypothesis),
                        "word_errors": errors,
                        "normalized_wer": round(errors / len(reference), 6),
                        "inference_seconds": diagnostics["inference_seconds"],
                        "batch_wall_seconds": round(wall, 4),
                        "batch_cpu_seconds": round(cpu, 4),
                        "actual_device": diagnostics["actual_device"],
                        "fallback_events": diagnostics["fallback_events"],
                        "chunks": len(diagnostics["chunk_records"]),
                        "dropped_segments": sum(
                            r["dropped_duplicates"] for r in diagnostics["chunk_records"]
                        ),
                    }
                    local = {**row, "session_id": session.id}
                    atomic_json(
                        store.session_dir(session.id) / "chunk-input-output.json", recording.chunks
                    )
                    index.append(local)
                    rows.append(row)
                    atomic_json(index_path, index)
                    atomic_json(
                        args.output,
                        {
                            "manifest": manifest["name"],
                            "normalization": (
                                "Casefold; ASCII words with internal apostrophes; "
                                "punctuation ignored"
                            ),
                            "timing": (
                                f"Warmed CPU pipeline; {args.comparison} paired comparison; "
                                "reverse order on repeat 2; "
                                "batch wall includes import and checkpoints"
                            ),
                            "rows": rows,
                        },
                    )
                    print(
                        model_id,
                        case["id"],
                        "repeat",
                        repeat,
                        "strategy",
                        strategy,
                        "overlap",
                        overlap,
                        "WER",
                        row["normalized_wer"],
                        "inference",
                        row["inference_seconds"],
                        "wall",
                        row["batch_wall_seconds"],
                        flush=True,
                    )


if __name__ == "__main__":
    main()
