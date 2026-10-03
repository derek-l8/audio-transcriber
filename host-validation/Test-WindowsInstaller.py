"""Compile/test an isolated installer identity; never use the normal app identity.

Requires an approved local Inno compiler, complete bundle, model and public clip.
All generated files must stay inside this checkout's ignored .scratch directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import winreg
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "NPU Scribe Validation"
APP_ID = "{5AA8A0D2-4E78-47BD-9230-0387D4F56B44}"
REG_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}_is1"


def registered() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY):
            return True
    except FileNotFoundError:
        return False


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def snapshot(directory: Path) -> dict[str, str]:
    return {str(p.relative_to(directory)): sha256(p) for p in directory.rglob("*") if p.is_file()}


def run(command: list[str], log: Path, *, cwd: Path, env=None, timeout=300) -> None:
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(  # noqa: S603 - local compiler/installer with fixed test identity
            command,
            cwd=cwd,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(  # noqa: S603 - only the validation process tree is terminated
                [
                    str(Path(os.environ["WINDIR"]) / "System32/taskkill.exe"),
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                ],
                capture_output=True,
                check=False,
                timeout=30,
            )
            process.wait(timeout=30)
            raise
    if code != 0:
        raise RuntimeError(f"Validation command failed with exit code {code}; see ignored log")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--validation-dir", type=Path, required=True)
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[1]
    for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        synced = os.environ.get(name)
        if synced and checkout.is_relative_to(Path(synced).resolve()):
            raise RuntimeError("Run validation from a checkout outside OneDrive")
    base = args.validation_dir.resolve()
    if not base.is_relative_to((ROOT / ".scratch").resolve()) or base.exists():
        raise RuntimeError("Use a fresh directory inside this checkout's .scratch")
    if registered():
        raise RuntimeError("An existing validation identity is registered; preserve it")
    startup = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"
    programs = startup.parent
    shortcuts = [startup / f"{APP_NAME}.lnk", programs / APP_NAME]
    if any(path.exists() for path in shortcuts):
        raise RuntimeError("Existing validation shortcuts found; preserve them")
    compiler = args.compiler.resolve(strict=True)
    bundle = args.bundle.resolve(strict=True)
    media = args.media.resolve(strict=True)
    model_root = args.model_root.resolve(strict=True)
    ffmpeg = args.ffmpeg.resolve(strict=True)
    base.mkdir(parents=True)
    output = base / "output"
    output.mkdir()
    run(
        [
            str(compiler),
            f"--define=BundleDir={bundle}",
            f"--define=AppName={APP_NAME}",
            f"--define=AppId={{{APP_ID}",
            f"--output-dir={output}",
            "--output-filename=npu-scribe-validation",
            str(ROOT / "packaging/npu-scribe.iss"),
        ],
        base / "compile.log",
        cwd=ROOT,
    )
    installer = output / "npu-scribe-validation.exe"
    app_dir = base / "installed"
    outside_library = base / "separate-library"
    outside_library.mkdir()
    (outside_library / "personal-note.txt").write_text("validation sentinel\n", encoding="utf-8")
    common = [
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/SP-",
        "/NORESTART",
        "/NOICONS",
        "/NOCLOSEAPPLICATIONS",
        "/NORESTARTAPPLICATIONS",
        f"/DIR={app_dir}",
    ]
    # Omit /TASKS: verify the fresh install's opt-in default through saved settings.
    run(
        [
            str(installer),
            *common,
            f"/SAVEINF={base / 'settings.inf'}",
            f"/LOG={base / 'install-detail.log'}",
        ],
        base / "install.log",
        cwd=base,
    )
    if not registered() or any(path.exists() for path in shortcuts):
        raise RuntimeError("Isolated registration or disabled shortcut check failed")
    # SAVEINF uses plain text here; inspect its ASCII key without assuming UTF-16.
    settings = (base / "settings.inf").read_bytes().splitlines()
    if b"Tasks=" not in settings:
        raise RuntimeError("Startup task was not off by default")
    payload = snapshot(bundle)
    if any(
        not (app_dir / name).is_file() or sha256(app_dir / name) != digest
        for name, digest in payload.items()
    ):
        raise RuntimeError("Installed payload differs from the bundle")
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(key, None)
    env["PATH"] = os.pathsep.join((str(Path(env["WINDIR"]) / "System32"), env["WINDIR"]))
    inside_library = app_dir / "personal-library"
    worker = app_dir / "npu-scribe-worker.exe"
    run(
        [
            str(worker),
            "--data-dir",
            str(inside_library),
            "--model-root",
            str(model_root),
            "transcribe",
            str(media),
            "--model",
            "whisper-tiny.en-int4-ov",
            "--device",
            "CPU",
            "--ffmpeg",
            str(ffmpeg),
        ],
        base / "worker.log",
        cwd=base,
        env=env,
    )
    sessions = list((inside_library / "lectures").glob("*/session.json"))
    if len(sessions) != 1:
        raise RuntimeError("Expected one installed-worker lecture")
    session = json.loads(sessions[0].read_text(encoding="utf-8"))
    if session["status"] != "ready" or session["diagnostics"]["actual_device"] != "CPU":
        raise RuntimeError("Installed-worker CPU inference did not complete")
    shutil.copytree(inside_library, outside_library, dirs_exist_ok=True)
    # Test nested unknown files inside a directory also containing installed files.
    nested_note = app_dir / "_internal/personal-note.txt"
    nested_note.write_text("validation sentinel\n", encoding="utf-8")
    original_inside = snapshot(inside_library)
    original_outside = snapshot(outside_library)
    note_hash = sha256(nested_note)
    run(
        [
            str(sys.executable),
            str(ROOT / "host-validation/Test-FrozenWindow.py"),
            str(app_dir / "NPU Scribe.exe"),
            "--data-dir",
            str(base / "gui-library"),
            "--report",
            str(base / "gui-results.json"),
        ],
        base / "gui.log",
        cwd=ROOT,
    )
    run(
        [str(installer), *common, f"/LOG={base / 'reinstall-detail.log'}"],
        base / "reinstall.log",
        cwd=base,
    )
    if snapshot(inside_library) != original_inside or snapshot(outside_library) != original_outside:
        raise RuntimeError("Reinstall changed a validation library")
    if sha256(nested_note) != note_hash or any(path.exists() for path in shortcuts):
        raise RuntimeError("Reinstall changed a user file or created a shortcut")
    # Uninstall only this new, verified workspace target and identity.
    if not app_dir.resolve().is_relative_to((ROOT / ".scratch").resolve()):
        raise RuntimeError("Uninstall target escaped ignored workspace storage")
    run(
        [
            str(app_dir / "unins000.exe"),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            f"/LOG={base / 'uninstall-detail.log'}",
        ],
        base / "uninstall.log",
        cwd=base,
    )
    if registered() or any(path.exists() for path in shortcuts):
        raise RuntimeError("Validation registration/shortcuts remain after uninstall")
    if any((app_dir / name).exists() for name in payload):
        raise RuntimeError("Installed payload remains after uninstall")
    if snapshot(inside_library) != original_inside or snapshot(outside_library) != original_outside:
        raise RuntimeError("Uninstall changed a validation library")
    if not nested_note.is_file() or sha256(nested_note) != note_hash:
        raise RuntimeError("Uninstall removed or changed an unknown nested file")
    results = {
        "compiler_version": "7.1.0",
        "compile": "passed",
        "installer_sha256": sha256(installer),
        "payload_files_verified": len(payload),
        "fresh_install": "passed",
        "startup_default": "unchecked",
        "shortcuts_created": False,
        "installed_worker_cpu_inference": "passed",
        "reinstall": "passed",
        "uninstall": "passed",
        "installed_payload_removed": True,
        "validation_registration_removed": True,
        "inside_library_files_preserved": len(original_inside),
        "separate_library_files_preserved": len(original_outside),
        "unknown_nested_file_preserved": True,
        "frozen_window": json.loads((base / "gui-results.json").read_text(encoding="utf-8")),
        "scope": "One Windows x64 host; separate validation identity, silent install/reinstall/"
        "uninstall, no shortcuts; public clip CPU inference; idle native GUI lifecycle. "
        "No visual installer wizard or GUI workflow validation.",
    }
    (base / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("Installer, reinstall, user-file preservation, and uninstall passed")


if __name__ == "__main__":
    main()
