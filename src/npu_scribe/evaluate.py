"""Manifest-driven evaluation of candidate models on public lecture material.

Evaluation media is never bundled: manifests reference official sources with
license, checksum, and expected size. Downloads are explicit evaluation actions;
ordinary transcription remains offline.

Selection policy (recorded per candidate):
1. compare at least two models on identical measured cases and one device;
2. reject a model with RTF >= 1.0 on any case and prefer RTF <= 0.5 throughout;
3. among eligible models choose the lowest mean case word error rate.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

from .metrics import cer, wer

EVAL_SCHEMA_VERSION = 1
READ_CHUNK = 1024 * 1024


class EvaluationError(Exception):
    pass


@dataclass
class CaseResult:
    case_id: str
    model_id: str
    requested_device: str
    actual_device: str
    wer: float | None = None
    cer: float | None = None
    rtf: float | None = None
    load_seconds: float | None = None
    inference_seconds: float | None = None
    audio_seconds: float | None = None
    peak_memory_mb: float | None = None
    runtime_version: str | None = None
    status: str = "measured"
    notes: str = ""


@dataclass
class EvaluationReport:
    schema_version: int = EVAL_SCHEMA_VERSION
    manifest_name: str = ""
    results: list[CaseResult] = field(default_factory=list)
    selection: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manifest": self.manifest_name,
            "results": [asdict(r) for r in self.results],
            "selection": self.selection,
        }


def load_manifest(path: Path) -> dict[str, Any]:
    value: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema_version") != EVAL_SCHEMA_VERSION:
        raise EvaluationError("unsupported evaluation manifest schema version")
    if not isinstance(value.get("cases"), list) or not value["cases"]:
        raise EvaluationError("evaluation manifest must declare at least one case")
    required = {
        "id",
        "audio_url",
        "audio_sha256",
        "expected_size_bytes",
        "license",
        "official_source",
        "reference_text",
        "reference_provenance",
    }
    for index, case in enumerate(value["cases"]):
        missing = required - set(case)
        if missing:
            raise EvaluationError(f"case {index} is missing fields: {sorted(missing)}")
    return cast(dict[str, Any], value)


def fetch_case_audio(case: dict[str, Any], destination_dir: Path) -> Path:
    """Explicit download of one declared public evaluation file, verified on arrival."""
    parsed = urllib.parse.urlsplit(str(case["audio_url"]))
    if parsed.scheme not in ("https", "file"):
        raise EvaluationError("evaluation audio URL must use https or file")
    destination_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(case["audio_url"].encode()).hexdigest()[:16]
    suffix = Path(str(case["audio_url"]).split("?")[0]).suffix or ".bin"
    target = destination_dir / f"{case['id']}-{digest}{suffix}"
    if target.is_file():
        _verify_file(target, case)
        return target
    temporary = destination_dir / f".{target.name}.part"
    received = 0
    try:
        with (
            urllib.request.urlopen(  # noqa: S310 - scheme validated to https/file above
                str(case["audio_url"]), timeout=300
            ) as response,
            temporary.open("wb") as out,
        ):
            while chunk := response.read(READ_CHUNK):
                received += len(chunk)
                if received > int(case["expected_size_bytes"]) * 2 + 1024 * 1024:
                    raise EvaluationError(
                        f"download for case '{case['id']}' exceeded its size limit"
                    )
                out.write(chunk)
        _verify_file(temporary, case)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    temporary.rename(target)
    return target


def _verify_file(path: Path, case: dict[str, Any]) -> None:
    size = path.stat().st_size
    if size != int(case["expected_size_bytes"]):
        raise EvaluationError(
            f"'{case['id']}' size mismatch ({size} != {case['expected_size_bytes']})"
        )
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(READ_CHUNK):
            digest.update(chunk)
    if digest.hexdigest() != case["audio_sha256"]:
        raise EvaluationError(f"'{case['id']}' failed its SHA-256 check")


def peak_memory_mb() -> float | None:
    if sys.platform == "win32":
        # The Windows validation harness measures process peak working set.
        return None
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        # Linux reports KiB; macOS reports bytes.
        scale = 1024.0 if sys.platform != "darwin" else 1024.0 * 1024.0
        return round(usage.ru_maxrss / scale, 2)
    except (OSError, ValueError):
        return None


def select_model(results: list[CaseResult]) -> dict[str, Any]:
    """Compare complete, matched case sets on the same device by mean WER."""
    groups: dict[str, list[CaseResult]] = {}
    for result in results:
        groups.setdefault(result.model_id, []).append(result)
    case_ids = {result.case_id for result in results}
    comparable = len(groups) >= 2 and bool(case_ids)
    for group in groups.values():
        comparable &= (
            len(group) == len(case_ids)
            and {item.case_id for item in group} == case_ids
            and all(
                item.status == "measured" and item.wer is not None and item.rtf is not None
                for item in group
            )
        )
    comparable &= len({item.actual_device for item in results}) == 1
    rejected_rtf = sorted(
        model_id
        for model_id, group in groups.items()
        if any(item.rtf is not None and item.rtf >= 1.0 for item in group)
    )
    eligible = sorted(model_id for model_id in groups if model_id not in rejected_rtf)
    if not comparable:
        return {
            "rejected_real_time_or_slower": rejected_rtf,
            "eligible_ids": [],
            "preferred_rtf_le_05": False,
            "selected_model_id": None,
            "note": "Compare at least two models on identical measured cases and one device.",
        }
    preferred = [
        model_id
        for model_id in eligible
        if all(item.rtf is not None and item.rtf <= 0.5 for item in groups[model_id])
    ]
    pool = preferred or eligible
    chosen = (
        min(
            pool,
            key=lambda model_id: (
                sum(item.wer or 0.0 for item in groups[model_id]) / len(groups[model_id])
            ),
        )
        if pool
        else None
    )
    return {
        "rejected_real_time_or_slower": rejected_rtf,
        "eligible_ids": eligible,
        "preferred_rtf_le_05": bool(preferred),
        "selected_model_id": chosen,
        "note": (
            "No eligible model met the measured real-time requirement."
            if chosen is None
            else "Provisional selection by mean WER on matched cases; review reference quality."
        ),
    }


def evaluate_case(
    case: dict[str, Any],
    audio_path: Path,
    transcribe: Callable[[Path], tuple[str, float, float | None, str, str]],
) -> CaseResult:
    """Measure one case. `transcribe` returns (hypothesis, inference s, load s|None,
    actual device, runtime version)."""
    result = CaseResult(
        case_id=str(case["id"]),
        model_id=str(case.get("model_id", "")),
        requested_device=str(case.get("device", "auto")),
        actual_device="unmeasured",
    )
    try:
        hypothesis, inference_seconds, load_seconds, device, runtime = transcribe(audio_path)
        result.actual_device = device
        result.runtime_version = runtime
        result.load_seconds = load_seconds
        result.inference_seconds = round(inference_seconds, 3)
        result.audio_seconds = float(case.get("audio_seconds", 0.0)) or None
        if result.audio_seconds:
            result.rtf = round(inference_seconds / result.audio_seconds, 4)
        result.wer = round(wer(str(case["reference_text"]), hypothesis), 4)
        result.cer = round(cer(str(case["reference_text"]), hypothesis), 4)
        result.peak_memory_mb = peak_memory_mb()
    except Exception as error:  # noqa: BLE001 - a failed case is data, not a crash
        result.status = "failed"
        result.notes = type(error).__name__
    return result


def write_report(report: EvaluationReport, destination: Path) -> None:
    from .storage import atomic_json

    atomic_json(destination, report.to_dict())
