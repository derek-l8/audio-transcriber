"""Compile/test an isolated installer identity; never use the normal app identity.

Requires an approved local Inno compiler, complete bundle, model and short recording.
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
APP_NAME = "Audio Transcriber Validation"
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
    parser.add_argument("--check-cleanup", action="store_true")
    parser.add_argument("--download-model", action="store_true")
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
    desktop_dir = base / "desktop"
    desktop_dir.mkdir()
    desktop_shortcut = desktop_dir / f"{APP_NAME}.lnk"
    output = base / "output"
    output.mkdir()
    run(
        [
            str(compiler),
            f"--define=BundleDir={bundle}",
            f"--define=AppName={APP_NAME}",
            f"--define=AppId={{{APP_ID}",
            f"--define=DesktopDir={desktop_dir}",
            f"--output-dir={output}",
            "--output-filename=audio-transcriber-validation",
            str(ROOT / "packaging/audio-transcriber.iss"),
        ],
        base / "compile.log",
        cwd=ROOT,
    )
    installer = output / "audio-transcriber-validation.exe"
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
    # Omit /TASKS: check desktop-on and startup-off defaults in isolated storage.
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
    if b"Tasks=desktopicon" not in settings:
        raise RuntimeError("Expected desktop shortcut on and startup off by default")
    if not desktop_shortcut.is_file():
        raise RuntimeError("Default desktop shortcut was not created")
    shortcut_env = os.environ.copy()
    shortcut_env["AUDIO_TRANSCRIBER_SHORTCUT"] = str(desktop_shortcut)
    shortcut_env["AUDIO_TRANSCRIBER_EXECUTABLE"] = str(app_dir / "Audio Transcriber.exe")
    run(
        [
            str(Path(os.environ["WINDIR"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"),
            "-NoProfile",
            "-Command",
            "$link = (New-Object -ComObject WScript.Shell).CreateShortcut("
            "$env:AUDIO_TRANSCRIBER_SHORTCUT); "
            "if ($link.TargetPath -ne $env:AUDIO_TRANSCRIBER_EXECUTABLE) "
            "{ throw 'Desktop shortcut target differs' }",
        ],
        base / "desktop-shortcut.log",
        cwd=base,
        env=shortcut_env,
    )
    run(
        [
            str(Path(os.environ["WINDIR"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"),
            "-NoProfile",
            "-File",
            str(ROOT / "host-validation/Test-DesktopShortcut.ps1"),
            "-Shortcut",
            str(desktop_shortcut),
            "-Library",
            str(base / "shortcut-library"),
        ],
        base / "desktop-shortcut-launch.log",
        cwd=base,
    )
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
    acquired_model = None
    if args.download_model:
        acquired_model = base / "downloaded-models"
        run(
            [
                str(app_dir / "audio-transcriber-worker.exe"),
                "--data-dir",
                str(base / "acquisition-data"),
                "--model-root",
                str(acquired_model),
                "models",
                "download",
                "whisper-tiny.en-int4-ov",
            ],
            base / "model-download.log",
            cwd=base,
            env=env,
        )
        from audio_transcriber.acquisition import get_spec, verify_installed

        if not verify_installed(acquired_model, get_spec("whisper-tiny.en-int4-ov")):
            raise RuntimeError("Installed-worker model download verification failed")
    inside_library = app_dir / "personal-library"
    worker = app_dir / "audio-transcriber-worker.exe"
    run(
        [
            str(worker),
            "--data-dir",
            str(inside_library),
            "--model-root",
            str(model_root if args.check_cleanup else acquired_model or model_root),
            "transcribe",
            str(media),
            "--model",
            "whisper-tiny.en-int4-ov",
            "--device",
            "CPU",
            "--ffmpeg",
            str(ffmpeg),
            *([] if args.check_cleanup else ["--cleanup", "off", "--formatting", "off"]),
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
    if not json.loads((sessions[0].parent / "raw-transcript.json").read_text(encoding="utf-8"))[
        "segments"
    ]:
        raise RuntimeError("Installed-worker transcript is empty")
    original_raw = sha256(sessions[0].parent / "raw-transcript.json")
    if args.check_cleanup:
        ai = json.loads((sessions[0].parent / "ai-transcript.json").read_text(encoding="utf-8"))
        formatted = json.loads(
            (sessions[0].parent / "formatted-transcript.json").read_text(encoding="utf-8")
        )
        if ai["transformation"]["style"] != "light" or ai["transformation"]["mode"] != "lecture":
            raise RuntimeError("Installed lecture cleanup defaults differ")
        if formatted["transformation"]["style"] != "structured":
            raise RuntimeError("Installed lecture formatting default differs")
        for layer, filename in (
            ("ai", "ai-transcript.json"),
            ("formatted", "formatted-transcript.json"),
        ):
            if not (sessions[0].parent / filename).is_file():
                raise RuntimeError(f"Installed-worker {layer} result is missing")
            run(
                [
                    str(worker),
                    "--data-dir",
                    str(inside_library),
                    "export",
                    session["id"],
                    "--layer",
                    layer,
                    "--format",
                    "markdown",
                ],
                base / f"export-{layer}.log",
                cwd=base,
                env=env,
            )
    if sha256(sessions[0].parent / "raw-transcript.json") != original_raw:
        raise RuntimeError("Cleanup or export changed the raw transcript")
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
            str(ROOT / "host-validation/Test-FrozenReview.py"),
            str(app_dir / "Audio Transcriber.exe"),
            "--work-dir",
            str(base / "gui-review"),
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
    if (
        sha256(nested_note) != note_hash
        or any(path.exists() for path in shortcuts)
        or not desktop_shortcut.is_file()
    ):
        raise RuntimeError("Reinstall changed a user file or created a shortcut")
    run(
        [
            str(compiler),
            f"--define=BundleDir={bundle}",
            f"--define=AppName={APP_NAME}",
            f"--define=AppId={{{APP_ID}",
            f"--define=DesktopDir={desktop_dir}",
            "--define=AppVersion=0.1.1",
            f"--output-dir={output}",
            "--output-filename=audio-transcriber-validation-upgrade",
            str(ROOT / "packaging/audio-transcriber.iss"),
        ],
        base / "compile-upgrade.log",
        cwd=ROOT,
    )
    run(
        [
            str(output / "audio-transcriber-validation-upgrade.exe"),
            *common,
            f"/LOG={base / 'upgrade-detail.log'}",
        ],
        base / "upgrade.log",
        cwd=base,
    )
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as key:
        if winreg.QueryValueEx(key, "DisplayVersion")[0] != "0.1.1":
            raise RuntimeError("Upgrade registration did not advance")
    if snapshot(inside_library) != original_inside or snapshot(outside_library) != original_outside:
        raise RuntimeError("Versioned reinstall changed a validation library")
    if (
        sha256(nested_note) != note_hash
        or any(path.exists() for path in shortcuts)
        or not desktop_shortcut.is_file()
    ):
        raise RuntimeError("Versioned reinstall changed a user file or created a shortcut")
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
    if registered() or any(path.exists() for path in [*shortcuts, desktop_shortcut]):
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
        "desktop_shortcut_created_and_target_verified": True,
        "desktop_shortcut_opened_without_cli_arguments": True,
        "desktop_shortcut_removed_on_uninstall": True,
        "shortcuts_outside_validation_storage_created": False,
        "installed_worker_cpu_inference": "passed",
        "reinstall": "passed",
        "versioned_reinstall": "0.1.0 to 0.1.1; same application payload",
        "installed_worker_model_download": "passed" if args.download_model else "not requested",
        "installed_lecture_defaults": "light / structured"
        if args.check_cleanup
        else "not requested",
        "installed_worker_cleanup_and_formatting": "passed"
        if args.check_cleanup
        else "not requested",
        "installed_worker_ai_and_formatted_exports": "passed"
        if args.check_cleanup
        else "not requested",
        "uninstall": "passed",
        "installed_payload_removed": True,
        "validation_registration_removed": True,
        "inside_library_files_preserved": len(original_inside),
        "separate_library_files_preserved": len(original_outside),
        "unknown_nested_file_preserved": True,
        "frozen_window": json.loads((base / "gui-results.json").read_text(encoding="utf-8")),
        "scope": "One Windows x64 host; separate validation identity, silent install/reinstall/"
        "uninstall, desktop shortcut in isolated storage; supplied recording CPU inference; "
        "owned native GUI workflows "
        "and fresh processing defaults. "
        "No visual installer wizard or real microphone capture.",
    }
    (base / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("Installer, reinstall, user-file preservation, and uninstall passed")


if __name__ == "__main__":
    main()
