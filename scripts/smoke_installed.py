"""Smoke a wheel installation using synthetic audio and its installed launchers."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import wave
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", type=Path, help="a new disposable directory outside src")
    args = parser.parse_args()
    import npu_scribe

    origin = Path(npu_scribe.__file__).resolve()
    if not origin.is_relative_to(Path(sys.prefix).resolve()):
        raise RuntimeError("Application was not imported from this environment's installation")
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    suffix = ".exe" if os.name == "nt" else ""
    cli = Path(sys.executable).parent / f"npu-scribe{suffix}"
    desktop = Path(sys.executable).parent / f"npu-scribe-desktop{suffix}"

    def run(program: Path, arguments: list[str], expected: int = 0) -> str:
        result = subprocess.run(  # noqa: S603 - installed launcher with synthetic test arguments
            [str(program), *arguments],
            cwd=work,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != expected:
            raise RuntimeError(f"Launcher returned {result.returncode}: {result.stderr}")
        return result.stdout

    run(cli, ["--help"])
    run(desktop, ["--help"])
    if "whisper-tiny.en-int4-ov" not in run(cli, ["models", "list"]):
        raise RuntimeError("Installed CLI did not list the approved model")
    source = work / "synthetic.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0\0" * (31 * 16000))
    stop = work / "pause.stop"
    stop.touch()
    base = ["--data-dir", str(work / "library")]
    paused = run(
        cli,
        base
        + [
            "transcribe",
            str(source),
            "--model",
            "mock",
            "--device",
            "CPU",
            "--stop-file",
            str(stop),
        ],
        expected=130,
    )
    session_id = paused.split("session: ", 1)[1].splitlines()[0]
    stop.unlink()
    resumed = run(cli, base + ["resume", session_id, "--model", "mock", "--device", "CPU"])
    if "status: ready" not in resumed:
        raise RuntimeError("Synthetic session did not finish after resume")
    session_dir = work / "library" / "lectures" / session_id
    session = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    if len(session["diagnostics"]["chunk_records"]) != 2:
        raise RuntimeError("Expected two committed synthetic chunks")
    for layer in ("raw", "balanced"):
        for fmt in ("json", "text", "markdown", "srt"):
            run(cli, base + ["export", session_id, "--layer", layer, "--format", fmt])
    exports = list((session_dir / "exports").iterdir())
    if len(exports) != 8 or any(path.stat().st_size == 0 for path in exports):
        raise RuntimeError("Expected eight nonempty exports")
    if (session_dir / "checkpoint.json").exists():
        raise RuntimeError("Completed session still has a checkpoint")
    print(
        "Installed wheel passed: both launchers, model listing, "
        "synthetic pause/resume, eight exports."
    )
    print("Mock transcription only; no accuracy or hardware inference claim.")


if __name__ == "__main__":
    main()
