"""Check native frozen GUI close during CPU inference and GUI resume.

Repeat a supplied local public speech excerpt into a bounded ten-minute fixture.
No downloads, source mutation, accuracy measurement or manual UI review.
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
    parser.add_argument("--excerpt", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[1]
    executable, excerpt, ffmpeg, models = (
        p.resolve(strict=True)
        for p in (args.executable, args.excerpt, args.ffmpeg, args.model_root)
    )
    work = args.work_dir.resolve()
    if os.name != "nt":
        raise RuntimeError("Windows required")
    for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        value = os.environ.get(name)
        if value and any(
            p.is_relative_to(Path(value).resolve())
            for p in (checkout, executable, excerpt, ffmpeg, models, work)
        ):
            raise RuntimeError("Use local paths outside OneDrive")
    if not work.is_relative_to(checkout / ".scratch") or work.exists():
        raise RuntimeError("Use a fresh work directory in this checkout's .scratch")
    work.mkdir(parents=True)
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(key, None)
    windows = Path(env["WINDIR"])
    env["PATH"] = os.pathsep.join((str(windows / "System32"), str(windows)))
    source_hash = digest(excerpt)
    decoded = work / "excerpt.wav"
    with (work / "decode.log").open("w") as log:
        subprocess.run(  # noqa: S603 - explicit local decoder and supplied excerpt
            [
                str(ffmpeg),
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(excerpt),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(decoded),
            ],
            env=env,
            cwd=work,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=60,
        )
    with wave.open(str(decoded), "rb") as stream:
        frames = stream.readframes(stream.getnframes())
    if not frames:
        raise RuntimeError("Excerpt contains no audio frames")
    size = 600 * 16000 * 2
    repeated = work / "repeated-public-speech.wav"
    with wave.open(str(repeated), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes((frames * (size // len(frames) + 1))[:size])
    repeated_hash = digest(repeated)
    library = work / "library"
    library.mkdir()
    (library / "desktop-settings.json").write_text(
        json.dumps({"model_root": str(models), "model": "whisper-tiny.en-int4-ov"}),
        encoding="utf-8",
    )
    native_report = work / "native-result.json"
    with (work / "native.log").open("w") as log:
        subprocess.run(  # noqa: S603 - own production GUI via the local Windows driver
            [
                str(windows / "System32/WindowsPowerShell/v1.0/powershell.exe"),
                "-NoProfile",
                "-File",
                str(Path(__file__).with_name("FrozenJobCloseDriver.ps1")),
                "-Exe",
                str(executable),
                "-Data",
                str(library),
                "-Media",
                str(repeated),
                "-Report",
                str(native_report),
            ],
            env=env,
            cwd=work,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=420,
        )
    folders = list((library / "lectures").iterdir())
    if len(folders) != 1:
        raise RuntimeError("Expected a single imported lecture")
    folder = folders[0]
    paused = read_json(work / "paused-checkpoint.json")
    session = read_json(folder / "session.json")
    raw = read_json(folder / "raw-transcript.json")
    records = session["diagnostics"]["chunk_records"]
    if [r["index"] for r in records] != list(range(20)) or session["status"] != "ready":
        raise RuntimeError("Resumed job did not complete twenty ordered unique chunks")
    if raw["segments"][: len(paused["segments"])] != paused["segments"]:
        raise RuntimeError("Resume changed previously committed transcript segments")
    if session["diagnostics"]["actual_device"] != "CPU" or any(
        r["device_used"] != "CPU" for r in records
    ):
        raise RuntimeError("Job did not stay on requested CPU")
    if (
        digest(excerpt) != source_hash
        or digest(repeated) != repeated_hash
        or digest(folder / "source/original.wav") != repeated_hash
    ):
        raise RuntimeError("Original or fixture source hash changed")
    result = {
        "scope": (
            "One-host native frozen GUI close during real CPU inference and GUI resume; "
            "repeated public speech excerpt, not an uninterrupted lecture or accuracy result."
        ),
        "fixture_seconds": 600,
        "chunks": 20,
        "model": "whisper-tiny.en-int4-ov",
        "actual_device": "CPU",
        "gui_sha256": digest(executable),
        "worker_sha256": digest(executable.with_name("audio-transcriber-worker.exe")),
        "native": read_json(native_report),
        "source_hashes_preserved": True,
        "ordered_unique_chunks": True,
        "committed_segments_preserved": True,
        "fallback_events": len(session["diagnostics"]["fallback_events"]),
    }
    (work / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("Frozen GUI close during CPU job and native resume passed")


if __name__ == "__main__":
    main()
