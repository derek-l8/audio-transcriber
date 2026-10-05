import math
import os
import struct
import sys
import wave
from pathlib import Path

import pytest

STUB_DIR = Path(__file__).parent / ".stubs"


def enable_python_stub_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Launch test decoder scripts through Python where shebangs are not executable."""
    if os.name != "nt":
        return
    from audio_transcriber import media

    build_args = media.build_ffmpeg_args

    def python_args(ffmpeg_path: str, source: Path, destination: Path) -> list[str]:
        return [sys.executable, *build_args(ffmpeg_path, source, destination)]

    monkeypatch.setattr(media, "build_ffmpeg_args", python_args)


@pytest.fixture(scope="session", autouse=True)
def deny_network_by_default():
    """The default suite must never touch the network.

    Live runs opt out explicitly via AUDIO_TRANSCRIBER_RUN_LIVE=1. Blocking happens at
    the raw socket layer so any unexpected DNS/HTTP/dataset access fails loudly
    instead of silently succeeding.
    """
    if os.environ.get("AUDIO_TRANSCRIBER_RUN_LIVE") == "1":
        yield
        return
    import socket as socket_module

    class DeniedSocket(socket_module.socket):
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError(
                "network socket created during the default (network-free) test suite"
            )

    original_socket = socket_module.socket

    def denied_create_connection(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("network disabled in the default test suite")

    original_create_connection = socket_module.create_connection
    socket_module.socket = DeniedSocket
    socket_module.create_connection = denied_create_connection
    yield
    socket_module.socket = original_socket
    socket_module.create_connection = original_create_connection


def write_wav(path: Path, seconds: float, rate: int = 16_000, frequency: float = 0.0) -> Path:
    frames = int(seconds * rate)
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        if frequency:
            data = b"".join(
                struct.pack(
                    "<h",
                    int(20000 * math.sin(2 * math.pi * frequency * i / rate)),
                )
                for i in range(frames)
            )
            target.writeframes(data)
        else:
            target.writeframes(b"\0\0" * frames)
    return path


@pytest.fixture
def silent_wav(tmp_path: Path) -> Path:
    return write_wav(tmp_path / "silence.wav", 1)


@pytest.fixture
def three_second_wav(tmp_path: Path) -> Path:
    return write_wav(tmp_path / "three-seconds.wav", 3)


@pytest.fixture
def stub_media(tmp_path: Path, three_second_wav: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Executable FFmpeg stand-in that emits a valid normalized WAV.

    The sandbox mounts /tmp noexec, so stubs live beside the tests on the
    overlay filesystem; the directory is gitignored and disposable.
    """
    STUB_DIR.mkdir(exist_ok=True)
    suffix = ".py" if os.name == "nt" else ""
    script = STUB_DIR / f"ffmpeg-stub-{abs(hash(str(tmp_path)))}{suffix}"
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"open(sys.argv[-1], 'wb').write(open({str(three_second_wav)!r}, 'rb').read())\n"
    )
    script.chmod(0o755)
    enable_python_stub_on_windows(monkeypatch)
    return str(script)
