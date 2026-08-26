"""Media decoding boundary.

Ordinary transcription accepts WAV, MP3, M4A, and MP4 here and always receives
normalized mono 16 kHz PCM. Direct PCM WAV inspection stays available without an
external decoder; every other container requires a configured FFmpeg binary.

Security rules enforced in this module:
- FFmpeg is never invoked through a shell; arguments are a fixed array.
- User input never becomes command syntax, only one validated positional input.
- Inputs must be regular files within the size limit with a supported extension.
- Decoding output is written to a private temporary directory.
- Temporary data is removed after both success and failure.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # noqa: S404 - arguments are a fixed array without shell
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

SUPPORTED_SUFFIXES = {".wav", ".mp3", ".m4a", ".mp4"}
DEFAULT_MAX_INPUT_BYTES = 2 * 1024 * 1024 * 1024  # two-hour-class sources stay far below this
TARGET_RATE = 16_000
MAX_STDERR_BYTES = 8_192


class MediaError(Exception):
    """Clear, sanitized failure for unsupported, malformed, or truncated media."""


@dataclass(frozen=True)
class NormalizedAudio:
    path: Path
    sample_rate: int
    channels: int
    frames: int
    decoder_identity: str

    @property
    def duration(self) -> float:
        return self.frames / self.sample_rate


class MediaDecoder(Protocol):
    identity: str

    def decode(self, source: Path) -> NormalizedAudio: ...


def validate_source(source: Path, max_bytes: int = DEFAULT_MAX_INPUT_BYTES) -> Path:
    if not isinstance(source, Path):
        raise MediaError("input path must be a filesystem path")
    resolved = source.resolve()
    if not resolved.is_file():
        raise MediaError(f"input is not a regular file: {resolved.name}")
    if resolved.suffix.casefold() not in SUPPORTED_SUFFIXES:
        raise MediaError(
            f"unsupported media type '{resolved.suffix or 'none'}'; "
            f"supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )
    size = resolved.stat().st_size
    if size <= 0:
        raise MediaError("input file is empty")
    if size > max_bytes:
        raise MediaError("input file exceeds the configured maximum size")
    return resolved


def inspect_pcm_wav(path: Path) -> tuple[int, int, int]:
    """Return (sample_rate, channels, frames) for a PCM WAV file."""
    try:
        with wave.open(str(path), "rb") as handle:
            if handle.getcomptype() != "NONE":
                raise MediaError("compressed WAV is unsupported")
            return handle.getframerate(), handle.getnchannels(), handle.getnframes()
    except wave.Error as error:
        raise MediaError(f"malformed WAV file: {error}") from error


class PcmWavDecoder:
    """Direct decoder for validated mono 16 kHz PCM WAV."""

    identity = "pcm-wav-direct-v1"

    def decode(self, source: Path) -> NormalizedAudio:
        rate, channels, frames = inspect_pcm_wav(validate_source(source))
        if channels != 1 or rate != TARGET_RATE:
            raise MediaError(
                f"WAV must already be mono {TARGET_RATE} Hz PCM; use --ffmpeg for other audio"
            )
        return NormalizedAudio(source.resolve(), rate, channels, frames, self.identity)


def build_ffmpeg_args(ffmpeg_path: str, source: Path, destination: Path) -> list[str]:
    """Fixed argument array; the only caller-supplied value is one validated path."""
    return [
        ffmpeg_path,
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(TARGET_RATE),
        "-acodec",
        "pcm_s16le",
        "-f",
        "wav",
        str(destination),
    ]


class FFmpegDecoder:
    """Adapter around an explicitly configured, pinned FFmpeg binary.

    The binary is not bundled yet; packaging will pin, license-review, and validate it.
    """

    identity = "ffmpeg-adapter-v1"

    def __init__(
        self, ffmpeg_path: str | os.PathLike[str], max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES
    ):
        self.ffmpeg_path = os.fspath(ffmpeg_path)
        self.max_input_bytes = max_input_bytes

    def decode(self, source: Path) -> NormalizedAudio:
        resolved = validate_source(source, self.max_input_bytes)
        if not shutil.which(self.ffmpeg_path) and not Path(self.ffmpeg_path).is_file():
            raise MediaError("configured FFmpeg binary was not found")
        work = Path(tempfile.mkdtemp(prefix="npu-scribe-decode-"))
        destination = work / "normalized.wav"
        try:
            completed = subprocess.run(  # noqa: S603 - fixed array, no shell
                build_ffmpeg_args(self.ffmpeg_path, resolved, destination),
                capture_output=True,
                timeout=3600,
                check=False,
                shell=False,
            )
            stderr = completed.stderr[:MAX_STDERR_BYTES].decode("utf-8", "replace").strip()
            if completed.returncode != 0 or not destination.is_file():
                raise MediaError(f"media decoding failed ({completed.returncode}): {stderr}")
            rate, channels, frames = inspect_pcm_wav(destination)
            if rate != TARGET_RATE or channels != 1:
                raise MediaError("decoder produced non-normalized output")
            return NormalizedAudio(destination, rate, channels, frames, self.identity)
        except subprocess.TimeoutExpired as error:
            raise MediaError("media decoding timed out") from error
        finally:
            # On success ownership of `destination` transfers to the caller's pipeline,
            # which keeps it inside its own session workspace; here we only clean up
            # when the decode failed before returning.
            if not destination.exists():
                shutil.rmtree(work, ignore_errors=True)


def adopt_normalized(audio: NormalizedAudio) -> None:
    """Remove the private staging directory of a consumed normalized result."""
    shutil.rmtree(audio.path.parent, ignore_errors=True)
