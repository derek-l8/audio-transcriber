"""Align overlap-pilot output to references and inspect missing words at seams.

A seam deletion is a contiguous reference deletion whose neighboring output
words belong to different input chunks. This is an inspectable text diagnostic,
not audio verification or a word-timestamp accuracy measurement. Review text
must be written to ignored local storage; the public summary has counts only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from audio_transcriber.metrics import _distance
from audio_transcriber.storage import atomic_json

TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)*")


def words(text):
    return TOKEN.findall(text.casefold())


def alignment(reference, hypothesis):
    previous = list(range(len(hypothesis) + 1))
    directions = [bytearray([3] * (len(hypothesis) + 1))]
    for i, word in enumerate(reference, 1):
        current = [i]
        direction = bytearray(len(hypothesis) + 1)
        direction[0] = 2
        for j, candidate in enumerate(hypothesis, 1):
            mismatch = word != candidate
            cost = previous[j - 1] + mismatch
            operation = int(mismatch)
            if previous[j] + 1 < cost:
                cost, operation = previous[j] + 1, 2
            if current[-1] + 1 < cost:
                cost, operation = current[-1] + 1, 3
            current.append(cost)
            direction[j] = operation
        directions.append(direction)
        previous = current
    result = []
    i, j = len(reference), len(hypothesis)
    while i or j:
        operation = directions[i][j]
        if i and j and operation in (0, 1):
            i, j = i - 1, j - 1
            result.append(("S" if operation else "M", i, j))
        elif i and operation == 2:
            i -= 1
            result.append(("D", i, j))
        else:
            j -= 1
            result.append(("I", i, j))
    return list(reversed(result))


def segment_key(segment):
    return round(segment["start"], 6), round(segment["end"], 6), segment["text"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("data_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("review_output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in manifest["cases"]}
    runs = json.loads((args.data_root / "run-index.json").read_text(encoding="utf-8"))
    public = []
    review = []
    for run in runs:
        directory = args.data_root / "lectures" / run["session_id"]
        chunks = json.loads((directory / "chunk-input-output.json").read_text(encoding="utf-8"))
        segments = json.loads((directory / "raw-transcript.json").read_text(encoding="utf-8"))[
            "segments"
        ]
        chunk_by_segment = {}
        for chunk in chunks:
            for segment in chunk["segments"]:
                chunk_by_segment.setdefault(segment_key(segment), chunk["index"])
        reference = words(cases[run["case_id"]]["reference_text"])
        hypothesis, labels = [], []
        for segment in segments:
            tokens = words(segment["text"])
            hypothesis.extend(tokens)
            labels.extend([chunk_by_segment[segment_key(segment)]] * len(tokens))
        operations = alignment(reference, hypothesis)
        counts = Counter(operation[0] for operation in operations)
        error_count = counts["S"] + counts["D"] + counts["I"]
        if not error_count == run["word_errors"] == _distance(reference, hypothesis):
            raise ValueError("Alignment edit counts disagree with the independent scorer")
        seams = []
        index = 0
        while index < len(operations):
            operation, ref_index, hyp_index = operations[index]
            if operation != "D":
                index += 1
                continue
            missing = [ref_index]
            index += 1
            while index < len(operations) and operations[index][0] == "D":
                missing.append(operations[index][1])
                index += 1
            if (
                hyp_index == 0
                or hyp_index >= len(labels)
                or labels[hyp_index - 1] == labels[hyp_index]
            ):
                continue
            left, right = labels[hyp_index - 1], labels[hyp_index]
            seams.append(
                {
                    "left_chunk": left,
                    "right_chunk": right,
                    "boundary_seconds": chunks[right]["start"],
                    "missing_words": len(missing),
                    "reference_start_word": missing[0],
                    "reference_end_word": missing[-1] + 1,
                    "reference_context": " ".join(
                        reference[max(0, missing[0] - 10) : missing[-1] + 11]
                    ),
                    "deleted_reference_text": " ".join(reference[i] for i in missing),
                    "hypothesis_context": " ".join(
                        hypothesis[max(0, hyp_index - 10) : hyp_index + 10]
                    ),
                }
            )
        repeats = []
        for previous, current in zip(chunks, chunks[1:], strict=False):
            left = words(" ".join(s["text"] for s in previous["segments"]))
            right = words(" ".join(s["text"] for s in current["segments"]))
            length = max(
                (n for n in range(2, min(20, len(left), len(right)) + 1) if left[-n:] == right[:n]),
                default=0,
            )
            if length:
                repeats.append({"chunk": current["index"], "words": length})
        row = {k: v for k, v in run.items() if k != "session_id"}
        row.update(
            {
                "normalized_hypothesis_sha256": hashlib.sha256(
                    " ".join(hypothesis).encode("utf-8")
                ).hexdigest(),
                "substitutions": counts["S"],
                "deletions": counts["D"],
                "insertions": counts["I"],
                "uncertain_segments": sum(bool(s.get("uncertain")) for s in segments),
                "seam_deletion_events": len(seams),
                "seam_deleted_words": sum(s["missing_words"] for s in seams),
                "seam_suffix_prefix_matches": len(repeats),
                "seam_matched_words": sum(s["words"] for s in repeats),
            }
        )
        public.append(row)
        if run["repeat"] == 1:
            review.append(
                {
                    "model_id": run["model_id"],
                    "case_id": run["case_id"],
                    "overlap_seconds": run["overlap_seconds"],
                    "chunk_strategy": run.get("chunk_strategy", "fixed"),
                    "seam_deletions": seams,
                    "reference_deletions": [i for op, i, _ in operations if op == "D"],
                    "reference_matches": [i for op, i, _ in operations if op == "M"],
                }
            )
    groups = defaultdict(list)
    for row in public:
        groups[
            (row["model_id"], row["overlap_seconds"], row.get("chunk_strategy", "fixed"))
        ].append(row)
    summary = []
    for (model, overlap, strategy), rows in groups.items():
        first = [r for r in rows if r["repeat"] == 1]
        references = sum(r["reference_words"] for r in first)
        medians = []
        for case in cases:
            matching = [r for r in rows if r["case_id"] == case]
            medians.append(
                {
                    "case_id": case,
                    "inference_seconds": statistics.median(
                        r["inference_seconds"] for r in matching
                    ),
                    "batch_wall_seconds": statistics.median(
                        r["batch_wall_seconds"] for r in matching
                    ),
                }
            )
        summary.append(
            {
                "model_id": model,
                "chunk_strategy": strategy,
                "overlap_seconds": overlap,
                "reference_words": references,
                "pooled_wer": sum(r["word_errors"] for r in first) / references,
                "substitutions": sum(r["substitutions"] for r in first),
                "deletions": sum(r["deletions"] for r in first),
                "insertions": sum(r["insertions"] for r in first),
                "seam_deletion_events": sum(r["seam_deletion_events"] for r in first),
                "seam_deleted_words": sum(r["seam_deleted_words"] for r in first),
                "seam_suffix_prefix_matches": sum(r["seam_suffix_prefix_matches"] for r in first),
                "seam_matched_words": sum(r["seam_matched_words"] for r in first),
                "repeat_scores_identical": all(
                    len({r["word_errors"] for r in rows if r["case_id"] == case}) == 1
                    for case in cases
                ),
                "repeat_transcripts_identical": all(
                    len({r["normalized_hypothesis_sha256"] for r in rows if r["case_id"] == case})
                    == 1
                    for case in cases
                ),
                "median_case_timings": medians,
                "pooled_inference_rtf": sum(r["inference_seconds"] for r in medians)
                / sum(c["audio_seconds"] for c in cases.values()),
                "pooled_batch_wall_rtf": sum(r["batch_wall_seconds"] for r in medians)
                / sum(c["audio_seconds"] for c in cases.values()),
            }
        )
    atomic_json(args.output, {"method": __doc__, "summary": summary, "rows": public})
    atomic_json(args.review_output, review)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
