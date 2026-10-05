"""Score local evaluation sessions against supplied references, ignoring punctuation.

This is a validation analysis, not the application's current strict WER metric.
Numbers and contractions are retained as words; no semantic correction is done.
The caller must record whether the supplied references were independently
audio-checked. The output contains counts and scores, never transcript text or media.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from audio_transcriber.metrics import _distance

MODELS = ("whisper-tiny.en-int4-ov", "whisper-base.en-int4-ov")
ASCII_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)*")
UNICODE_TOKEN = re.compile(r"[^\W_]+(?:'[^\W_]+)*")


def tokens(text: str, pattern: re.Pattern[str] = ASCII_TOKEN) -> list[str]:
    return pattern.findall(text.casefold())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--unicode-words", action="store_true")
    args = parser.parse_args()
    pattern = UNICODE_TOKEN if args.unicode_words else ASCII_TOKEN
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    by_id = {case["id"]: case for case in manifest["cases"]}
    sessions = {}
    for directory in (args.data_dir / "lectures").iterdir():
        path = directory / "session.json"
        if not path.is_file() or not (directory / "raw-transcript.json").is_file():
            continue
        session = json.loads(path.read_text(encoding="utf-8"))
        model = session.get("diagnostics", {}).get("model_id")
        title = session.get("title", "")
        case_id = next(
            (id_ for id_ in by_id if title.startswith(id_ + "-") or title == id_ + ".wav"),
            None,
        )
        if model not in MODELS or case_id is None or session.get("status") != "ready":
            continue
        key = (model, case_id)
        if key not in sessions or session["created_at"] > sessions[key][0]["created_at"]:
            sessions[key] = (session, directory)
    rows = []
    for model in MODELS:
        for case_id, case in by_id.items():
            session, directory = sessions[(model, case_id)]
            diagnostics = session["diagnostics"]
            transcript = json.loads((directory / "raw-transcript.json").read_text(encoding="utf-8"))
            hypothesis = " ".join(segment["text"] for segment in transcript["segments"])
            reference_words = tokens(case["reference_text"], pattern)
            hypothesis_words = tokens(hypothesis, pattern)
            errors = _distance(reference_words, hypothesis_words)
            rows.append(
                {
                    "model_id": model,
                    "case_id": case_id,
                    "reference_words": len(reference_words),
                    "hypothesis_words": len(hypothesis_words),
                    "word_errors": errors,
                    "normalized_wer": round(errors / max(1, len(reference_words)), 4),
                    "inference_seconds": diagnostics["inference_seconds"],
                    "rtf": round(diagnostics["inference_seconds"] / case["audio_seconds"], 4),
                    "actual_device": diagnostics["actual_device"],
                    "fallback_events": diagnostics["fallback_events"],
                }
            )
    summary = {}
    for model in MODELS:
        subset = [row for row in rows if row["model_id"] == model]
        summary[model] = {
            "pooled_wer": round(
                sum(row["word_errors"] for row in subset)
                / sum(row["reference_words"] for row in subset),
                4,
            ),
            "mean_case_wer": round(sum(row["normalized_wer"] for row in subset) / len(subset), 4),
            "audio_seconds": round(
                sum(by_id[row["case_id"]]["audio_seconds"] for row in subset), 2
            ),
        }
    result = {
        "manifest": manifest["name"],
        "normalization": (
            "Unicode casefold; Unicode letter/digit words with internal apostrophes; "
            "punctuation ignored; numbers retained"
            if args.unicode_words
            else "Unicode casefold; tokens [a-z0-9]+ with internal apostrophes; "
            "punctuation ignored; numbers retained"
        ),
        "rows": rows,
        "summary": summary,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
