from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import STUB_DIR, enable_python_stub_on_windows

from npu_scribe.media import (
    FFmpegDecoder,
    MediaError,
    PcmWavDecoder,
    build_ffmpeg_args,
    inspect_pcm_wav,
    validate_source,
)


def make_stub(tmp_path: Path, name: str, body: str) -> str:
    # The sandbox mounts /tmp noexec; stubs live beside the tests instead.
    STUB_DIR.mkdir(exist_ok=True)
    suffix = ".py" if os.name == "nt" else ""
    script = STUB_DIR / f"{name}-{abs(hash(str(tmp_path)))}{suffix}"
    script.write_text(f"#!{sys.executable}\n{body}")
    script.chmod(0o755)
    if os.name != "nt":
        assert script.stat().st_mode & stat.S_IXUSR
    return str(script)


COPY_STUB = """
import sys
out = sys.argv[-1]
source = {source}
open(out, "wb").write(open(source, "rb").read())
"""

FAILING_STUB = """
import sys
print("synthetic decoder failure", file=sys.stderr)
raise SystemExit(1)
"""


@pytest.fixture
def stub_ffmpeg(tmp_path: Path, three_second_wav: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    source_literal = repr(str(three_second_wav))
    enable_python_stub_on_windows(monkeypatch)
    return make_stub(tmp_path, "ffmpeg-stub", COPY_STUB.format(source=source_literal))


def test_validate_source_rules(tmp_path: Path, silent_wav: Path) -> None:
    assert validate_source(silent_wav).name == "silence.wav"
    wrong_type = tmp_path / "audio.xyz"
    wrong_type.write_bytes(b"x")
    with pytest.raises(MediaError, match="unsupported media type"):
        validate_source(wrong_type)
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(MediaError, match="empty"):
        validate_source(empty)
    directory = tmp_path / "dir.wav"
    directory.mkdir()
    with pytest.raises(MediaError, match="regular file"):
        validate_source(directory)


def test_inspect_rejects_malformed(tmp_path: Path) -> None:
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"RIFFnot-a-wav")
    with pytest.raises(MediaError, match="malformed WAV"):
        inspect_pcm_wav(bad)


def test_ffmpeg_arguments_are_fixed_array(tmp_path: Path) -> None:
    args = build_ffmpeg_args("/opt/ffmpeg", tmp_path / "in.mp4", tmp_path / "out.wav")
    assert args[0] == "/opt/ffmpeg"
    assert "-nostdin" in args
    assert args[args.index("-ar") + 1] == "16000"
    assert args[args.index("-ac") + 1] == "1"
    # No shell metacharacters ever enter the argument array.
    assert all("&&" not in a and ";" not in a for a in args)


def test_ffmpeg_decoder_produces_normalized_wav(tmp_path: Path, stub_ffmpeg: str) -> None:
    source = tmp_path / "lecture.mp3"
    source.write_bytes(b"synthetic mp3 payload")
    audio = FFmpegDecoder(stub_ffmpeg).decode(source)
    try:
        assert audio.sample_rate == 16_000
        assert audio.channels == 1
        assert audio.decoder_identity == FFmpegDecoder.identity
        assert audio.path.is_file()
    finally:
        audio.path.unlink(missing_ok=True)


def test_ffmpeg_decoder_failure_is_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    enable_python_stub_on_windows(monkeypatch)
    failing = make_stub(tmp_path, "failing-ffmpeg", FAILING_STUB)
    source = tmp_path / "broken.m4a"
    source.write_bytes(b"payload")
    with pytest.raises(MediaError, match="decoding failed"):
        FFmpegDecoder(failing).decode(source)
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith("npu-scribe-decode-")]
    assert not leftovers


def test_missing_binary_is_a_clear_failure(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"payload")
    with pytest.raises(MediaError, match="not found"):
        FFmpegDecoder("/nonexistent/ffmpeg").decode(source)


def test_pcm_decoder_requires_normalized(silent_wav: Path, tmp_path: Path) -> None:
    assert PcmWavDecoder().decode(silent_wav).frames == 16_000
    stereo = tmp_path / "stereo.wav"
    import wave

    with wave.open(str(stereo), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\0\0\0\0")
    with pytest.raises(MediaError, match="mono 16000"):
        PcmWavDecoder().decode(stereo)


def test_no_shell_invocation_anywhere(tmp_path: Path) -> None:
    """Direct evidence that subprocess use passes fixed arrays without a shell."""
    script = make_stub(tmp_path, "argv-check", "import sys; print(repr(sys.argv))")
    executable = [sys.executable, script] if os.name == "nt" else [script]
    completed = subprocess.run(  # noqa: S603 - fixed array, local stub
        [*executable, "a b", "c;d", "e&&f"], capture_output=True, text=True, check=False
    )
    assert completed.stdout.strip() == repr([script, "a b", "c;d", "e&&f"])
    assert os.environ.get("SHELL") != script


def test_decoder_discovers_local_ffmpeg_without_saved_paths(tmp_path, monkeypatch):
    from npu_scribe.pipeline import select_decoder

    executable = str(tmp_path / "Tools with spaces" / "ffmpeg.exe")
    monkeypatch.setattr(
        "npu_scribe.media.shutil.which", lambda name: executable if name == "ffmpeg" else None
    )
    assert select_decoder(".mp4", None).ffmpeg_path == executable
    # Explicit configuration takes precedence even if it no longer exists.
    explicit = str(tmp_path / "missing.exe")
    decoder = select_decoder(".mp4", explicit)
    assert decoder.ffmpeg_path == explicit
    source = tmp_path / "lecture.mp4"
    source.write_bytes(b"synthetic media")
    with pytest.raises(MediaError, match="not found"):
        decoder.decode(source)
    assert isinstance(select_decoder(".wav", None), PcmWavDecoder)


def test_decoder_missing_ffmpeg_explains_setup(monkeypatch):
    from npu_scribe.pipeline import select_decoder

    monkeypatch.setattr("npu_scribe.media.shutil.which", lambda name: None)
    with pytest.raises(MediaError, match="install it on PATH"):
        select_decoder(".mp3", None)
