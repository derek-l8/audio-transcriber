"""Source launchers and the frozen worker contract; no PyInstaller dependency."""

from __future__ import annotations

import builtins
import subprocess
import sys
from pathlib import Path

import pytest

from npu_scribe import desktop
from npu_scribe.desktop import worker_command

ROOT = Path(__file__).resolve().parents[1]


def test_worker_uses_current_python_environment():
    program, arguments = worker_command(["models", "list"])
    assert program == sys.executable
    assert arguments == ["-m", "npu_scribe.cli", "models", "list"]


def test_frozen_worker_is_a_sibling_console_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "NPU Scribe.exe"))
    program, arguments = worker_command(["models", "list"])
    assert program == str(tmp_path / "npu-scribe-worker.exe")
    assert arguments == ["models", "list"]


def test_packaging_launchers_import_as_scripts(tmp_path, three_second_wav):
    desktop = subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned entry point
        [sys.executable, str(ROOT / "packaging" / "desktop_entry.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert desktop.returncode == 0, desktop.stderr
    assert "--data-dir" in desktop.stdout
    worker = subprocess.run(  # noqa: S603 - fixed interpreter, source entry and synthetic fixture
        [
            sys.executable,
            str(ROOT / "packaging" / "worker_entry.py"),
            "--data-dir",
            str(tmp_path / "library"),
            "transcribe",
            "--cleanup",
            "off",
            "--formatting",
            "off",
            str(three_second_wav),
            "--model",
            "mock",
            "--device",
            "CPU",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert worker.returncode == 0, worker.stderr
    assert "status: ready" in worker.stdout
    assert "actual_device: CPU" in worker.stdout


@pytest.mark.parametrize("frozen", [False, True])
def test_desktop_startup_failure_keeps_diagnostics(monkeypatch, tmp_path, frozen):
    real_import = builtins.__import__

    def missing_desktop(name, *args, **kwargs):
        if name.startswith("PySide6"):
            raise ImportError("missing desktop dependency fixture")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(sys, "argv", ["npu-scribe-desktop", "--data-dir", str(tmp_path)])
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(builtins, "__import__", missing_desktop)
    with pytest.raises(SystemExit, match="Details:"):
        desktop.main()
    assert "missing desktop dependency fixture" in (tmp_path / "startup-error.log").read_text(
        encoding="utf-8"
    )
