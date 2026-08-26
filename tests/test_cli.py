from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

from npu_scribe.cli import main


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "app-data"


def test_transcribe_creates_session_and_prints_id(data_dir: Path, capsys) -> None:
    wav = data_dir.parent / "in.wav"
    # conftest writes wavs via wave; create one inline to avoid fixture coupling.
    import wave

    with wave.open(str(wav), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\0\0" * 48_000)

    code = main(
        [
            "--data-dir",
            str(data_dir),
            "transcribe",
            str(wav),
            "--model",
            "mock",
            "--device",
            "auto",
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    session_id = output.split("session: ")[1].splitlines()[0]
    assert (data_dir / "lectures" / session_id / "raw-transcript.json").is_file()


def test_export_all_formats_and_layers(
    data_dir: Path, tmp_path: Path, three_second_wav: Path
) -> None:
    code = main(
        ["--data-dir", str(data_dir), "transcribe", str(three_second_wav), "--model", "mock"]
    )
    assert code == 0
    session_id = next((data_dir / "lectures").iterdir()).name
    for fmt in ("json", "markdown", "text", "srt"):
        for layer in ("raw", "balanced"):
            code = main(
                [
                    "--data-dir",
                    str(data_dir),
                    "export",
                    session_id,
                    "--format",
                    fmt,
                    "--layer",
                    layer,
                ]
            )
            assert code == 0
        path = (
            data_dir
            / "lectures"
            / session_id
            / "exports"
            / f"{session_id}.{layer}.{fmt if fmt != 'markdown' else 'md'}"
        )
        assert path.is_file()
        content = path.read_text()
        assert content.strip()
    # JSON identifies the selected layer and carries provenance.
    payload = json.loads(
        (data_dir / "lectures" / session_id / "exports" / f"{session_id}.raw.json").read_text()
    )
    assert payload["layer"] == "raw"
    assert payload["provenance"]["actual_device"]


def test_export_refuses_overwrite_without_flag(
    data_dir: Path, three_second_wav: Path, capsys
) -> None:
    main(["--data-dir", str(data_dir), "transcribe", str(three_second_wav), "--model", "mock"])
    session_id = next((data_dir / "lectures").iterdir()).name
    args = ["--data-dir", str(data_dir), "export", session_id, "--format", "text", "--layer", "raw"]
    assert main(args) == 0
    code = main(args + [])
    assert code == 1
    assert "already exists" in capsys.readouterr().err
    assert main(args + ["--overwrite"]) == 0


def test_models_list_and_unknown_download_refused(data_dir: Path, capsys) -> None:
    assert main(["--data-dir", str(data_dir), "models", "list"]) == 0
    listing = capsys.readouterr().out
    assert "whisper-tiny.en-int4-ov" in listing
    assert "development-proof" in listing
    code = main(["--data-dir", str(data_dir), "models", "download", "not-approved"])
    assert code == 1
    assert "not manifest-approved" in capsys.readouterr().err


def test_devices_reports_without_openvino_claim(data_dir: Path, capsys) -> None:
    code = main(["--data-dir", str(data_dir), "devices"])
    assert code == 0
    out = capsys.readouterr().out
    assert "runtime:" in out


def test_resume_missing_session_fails_cleanly(data_dir: Path, capsys) -> None:
    code = main(["--data-dir", str(data_dir), "resume", "nonexistent0", "--model", "mock"])
    assert code == 1
    assert "error:" in capsys.readouterr().err


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("NPU_SCRIBE_RUN_LIVE") != "1",
    reason="live network test; run with NPU_SCRIBE_RUN_LIVE=1 and -m live",
)
def test_models_download_real_pinned_model_live(data_dir: Path) -> None:
    """Opt-in: full download of the pinned tiny.en proof model over real HTTPS."""
    code = main(["--data-dir", str(data_dir), "models", "download", "whisper-tiny.en-int4-ov"])
    assert code == 0
    install = data_dir / "models" / "whisper-tiny.en-int4-ov"
    assert install.is_dir()
    files = sorted(p.name for p in install.iterdir())
    assert "openvino_encoder_model.bin" in files
    assert all(not p.is_symlink() for p in install.iterdir())


# ---------------------------------------------------------------- test isolation


class _DeniedSocket(socket.socket):
    def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("network socket created during a default test")


def test_default_commands_are_network_free(
    data_dir: Path, three_second_wav: Path, monkeypatch, capsys
) -> None:
    """Regression: ordinary commands never open sockets or touch the downloader."""
    import npu_scribe.acquisition as acquisition

    def denied_fetcher(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("live downloader invoked during a default command")

    monkeypatch.setattr(socket, "socket", _DeniedSocket)
    monkeypatch.setattr(acquisition, "https_fetcher", denied_fetcher)
    assert main(["--data-dir", str(data_dir), "models", "list"]) == 0
    capsys.readouterr()
    assert main(["--data-dir", str(data_dir), "devices"]) == 0
    capsys.readouterr()
    assert (
        main(["--data-dir", str(data_dir), "transcribe", str(three_second_wav), "--model", "mock"])
        == 0
    )
    session_id = next((data_dir / "lectures").iterdir()).name
    assert (
        main(
            [
                "--data-dir",
                str(data_dir),
                "export",
                session_id,
                "--format",
                "text",
                "--layer",
                "raw",
            ]
        )
        == 0
    )
    capsys.readouterr()


def _test_sources() -> dict[str, str]:
    directory = Path(__file__).parent
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(directory.glob("test_*.py"))}


def test_no_network_activity_at_collection_time() -> None:
    """No test module may perform network I/O at import/collection scope."""
    for name, text in _test_sources().items():
        for number, line in enumerate(text.splitlines(), 1):
            module_level = bool(line) and not line[0].isspace()
            stripped = line.strip()
            is_definition = stripped.startswith(("class ", "def "))
            if (
                module_level
                and not is_definition
                and ("urlopen(" in line or "socket.socket(" in line)
            ):
                pytest.fail(f"{name}:{number} performs network activity at module level")


def test_real_downloader_only_behind_live_marker_and_env_gate() -> None:
    cli_tests = _test_sources()["test_cli.py"]
    forbidden_probe = "_hf_" + "reachable"  # assembled to avoid self-reference
    assert forbidden_probe not in cli_tests, "collection-time reachability probes are forbidden"
    assert "@pytest.mark.live" in cli_tests
    assert 'os.environ.get("NPU_SCRIBE_RUN_LIVE")' in cli_tests
