"""Validate the production frozen GUI through owned Windows accessibility controls.

Silent synthetic audio and the frozen mock worker provide a fresh library.
No product callbacks are replaced. No other application's UI is inspected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import wave
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[1]
    executable = args.executable.resolve(strict=True)
    worker = executable.with_name("npu-scribe-worker.exe")
    worker.resolve(strict=True)
    work = args.work_dir.resolve()
    if os.name != "nt":
        raise RuntimeError("Windows is required")
    for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        synced = os.environ.get(name)
        if synced and any(
            p.is_relative_to(Path(synced).resolve())
            for p in (checkout, work, executable, args.report.resolve())
        ):
            raise RuntimeError("Use paths outside OneDrive")
    if not work.is_relative_to(checkout / ".scratch") or work.exists():
        raise RuntimeError("Use a fresh work directory inside this checkout's .scratch")
    work.mkdir(parents=True)
    source = work / "synthetic.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\0\0" * 16000 * 61)
    source_hash = digest(source)
    env = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(name, None)
    windows = Path(env["WINDIR"])
    env["PATH"] = os.pathsep.join((str(windows / "System32"), str(windows)))
    library = work / "library"
    with (work / "worker.log").open("w", encoding="utf-8") as log:
        subprocess.run(  # noqa: S603 - explicit local frozen validation executable
            [
                str(worker),
                "--data-dir",
                str(library),
                "transcribe",
                str(source),
                "--model",
                "mock",
                "--device",
                "CPU",
            ],
            cwd=work,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=60,
        )
    folders = list((library / "lectures").iterdir())
    if len(folders) != 1:
        raise RuntimeError("Expected a single synthetic fixture session")
    folder = folders[0]
    originals = [folder / f"{layer}-transcript.json" for layer in ("raw", "balanced")]
    hashes = [digest(path) for path in originals]
    native_report = work / "native-result.json"
    powershell = windows / "System32/WindowsPowerShell/v1.0/powershell.exe"
    with (work / "native.log").open("w", encoding="utf-8") as log:
        subprocess.run(  # noqa: S603 - owned GUI driver with explicit paths, no shell
            [
                str(powershell),
                "-NoProfile",
                "-File",
                str(Path(__file__).with_name("FrozenReviewDriver.ps1")),
                "-Exe",
                str(executable),
                "-Data",
                str(library),
                "-Report",
                str(native_report),
            ],
            cwd=work,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=180,
        )
    native = read_json(native_report)
    revisions = [read_json(path) for path in (folder / "edits").glob("*.json")]
    session = read_json(folder / "session.json")
    latest = read_json(folder / session["edited_transcript"])
    if len(session["diagnostics"]["chunk_records"]) != 3:
        raise RuntimeError("Expected three synthetic chunks")
    if len(revisions) != 2:
        raise RuntimeError("Expected two saved revisions")
    if sorted(record["segments"][0]["text"] for record in revisions) != [
        "Synthetic native correction one",
        "Synthetic native correction two",
    ]:
        raise RuntimeError("Previous revision text changed")
    older = next(record for record in revisions if record["revision"] != latest["revision"])
    if latest["parent"] != older["revision"] or older["parent"] is not None:
        raise RuntimeError("Saved revision chain changed")
    unchanged = [digest(path) for path in originals] == hashes
    timestamps = [(s["start"], s["end"]) for s in read_json(originals[0])["segments"]]
    preserved = all(
        [(s["start"], s["end"]) for s in record["segments"]] == timestamps for record in revisions
    )
    if not unchanged or not preserved or len(revisions) != 2:
        raise RuntimeError("Original layers, timestamps or revision count changed")
    if (
        latest["segments"][0]["text"] != "Synthetic native correction two"
        or not latest["segments"][0]["uncertain"]
    ):
        raise RuntimeError("Edited text or uncertainty flag not persisted")
    copies = list((folder / "source").glob("original.*"))
    if len(copies) != 1 or digest(source) != source_hash or digest(copies[0]) != source_hash:
        raise RuntimeError("Source audio changed")
    exports = list((work / "exports").iterdir())
    if len(exports) != 12 or any(not p.stat().st_size for p in exports):
        raise RuntimeError("Expected twelve nonempty native exports")
    for layer in ("raw", "balanced", "edited"):
        expected = latest if layer == "edited" else read_json(folder / f"{layer}-transcript.json")
        payload = read_json(work / "exports" / f"{layer}.json")
        if payload["segments"] != expected["segments"]:
            raise RuntimeError(f"Native {layer} JSON export differs from its transcript")
    report = {
        "scope": (
            "Production frozen Windows GUI through owned UI Automation; "
            "silent synthetic audio and mock transcription; no visual review, "
            "real speech accuracy or device inference claim."
        ),
        "fixture_seconds": 61,
        "fixture_chunks": 3,
        "gui_sha256": digest(executable),
        "worker_sha256": digest(worker),
        "native": native,
        "raw_balanced_unchanged": unchanged,
        "timestamps_unchanged": preserved,
        "source_hash_preserved": True,
        "edited_uncertainty_persisted": True,
        "revisions": len(revisions),
        "previous_revision_preserved_on_disk": True,
        "unverified": [
            "close during active job",
            "visual/manual usability",
            "another Windows host",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Frozen review workflow passed; two revisions and original audio/transcripts verified")


if __name__ == "__main__":
    main()
