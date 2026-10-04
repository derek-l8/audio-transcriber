"""Audio normalization and durable, bounded dictation results."""

from __future__ import annotations

import array
import json
import math
import re
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage import atomic_json, safe_child

MAX_SECONDS = 120


@dataclass(frozen=True)
class Hotkey:
    modifiers: int
    key: int


def parse_hotkey(text: str) -> Hotkey:
    parts = [p.strip().upper() for p in text.split("+")]
    modifiers = 0
    for part in parts[:-1]:
        value = {"CTRL": 2, "ALT": 1, "SHIFT": 4, "WIN": 8, "META": 8}.get(part)
        if value is None or modifiers & value:
            raise ValueError("Use one shortcut such as Ctrl+Alt+Space or Ctrl+Shift+F9.")
        modifiers |= value
    key = parts[-1]
    keys = {
        "SPACE": 32,
        "RETURN": 13,
        "ENTER": 13,
        "TAB": 9,
        "ESC": 27,
        "ESCAPE": 27,
        "BACKSPACE": 8,
        "HOME": 36,
        "END": 35,
        "INSERT": 45,
        "DELETE": 46,
        "LEFT": 37,
        "UP": 38,
        "RIGHT": 39,
        "DOWN": 40,
    }
    if re.fullmatch(r"F(?:[1-9]|1[0-9]|2[0-4])", key):
        code = 111 + int(key[1:])
    elif len(key) == 1 and key.isascii() and key.isalnum():
        code = ord(key)
    elif key in keys:
        code = keys[key]
    else:
        raise ValueError("Choose a letter, number, Space, or function key.")
    if not modifiers:
        raise ValueError("Include Ctrl, Alt, Shift, or Win in the shortcut.")
    return Hotkey(modifiers, code)


def normalize_capture(
    source: Path,
    destination: Path,
    rate: int,
    channels: int,
    sample_type: str,
    *,
    require_sound: bool = False,
) -> Path:
    """Convert a bounded native microphone buffer to the engine's PCM WAV format."""
    types = {
        "int16": ("h", 32768.0),
        "int32": ("i", 2147483648.0),
        "float": ("f", 1.0),
        "uint8": ("B", 128.0),
    }
    if sample_type not in types or not 8000 <= rate <= 192000 or not 1 <= channels <= 8:
        raise ValueError("Unsupported microphone format.")
    kind, scale = types[sample_type]
    samples = array.array(kind)
    size = source.stat().st_size
    if size > min(64 * 1024 * 1024, MAX_SECONDS * rate * channels * samples.itemsize):
        raise ValueError("Recording exceeds the two-minute limit.")
    if not size or size % (samples.itemsize * channels):
        raise ValueError("No complete audio frames were recorded.")
    samples.frombytes(source.read_bytes())
    if sys.byteorder != "little":
        samples.byteswap()
    frames = len(samples) // channels
    output = array.array("h")
    for i in range(frames * 16000 // rate):
        position = i * rate / 16000
        left = int(position)
        right = min(left + 1, frames - 1)
        fraction = position - left
        value = sum(
            samples[left * channels + c] * (1 - fraction) + samples[right * channels + c] * fraction
            for c in range(channels)
        )
        value = value / channels
        value = (value - 128) / scale if sample_type == "uint8" else value / scale
        value = value if math.isfinite(value) else 0.0
        output.append(max(-32768, min(32767, round(value * 32768))))
    if len(output) < 1600:
        raise ValueError("Recording was too short. Hold the shortcut a little longer.")
    if require_sound and max(abs(v) for v in output) < 32:
        raise ValueError("Recording is too quiet. Check the microphone, mute, and input level.")
    if sys.byteorder != "little":
        output.byteswap()
    with wave.open(str(destination), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16000)
        target.writeframes(output.tobytes())
    return destination


class DictationHistory:
    def __init__(self, root: Path):
        self.root = root / "history"

    def save(self, record: dict[str, Any]) -> None:
        folder = safe_child(self.root, str(record["id"]))
        atomic_json(folder.with_suffix(".json"), record)

    def records(self) -> list[dict[str, Any]]:
        result = []
        for path in self.root.glob("*.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict) and isinstance(value.get("text"), str):
                    result.append(value)
            except (OSError, ValueError):
                continue
        return sorted(result, key=lambda r: str(r.get("created_at", "")), reverse=True)
