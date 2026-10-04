"""Audio conversion, recovery persistence, and Windows insertion contracts."""

from __future__ import annotations

import array
import ctypes
import math
import sys
import wave
from types import SimpleNamespace

import pytest

from npu_scribe.dictation import DictationHistory, Hotkey, normalize_capture, parse_hotkey
from npu_scribe.insertion import FocusTarget
from npu_scribe.windows_dictation import Input, WindowsInput


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ctrl+Alt+Space", Hotkey(3, 32)),
        ("Ctrl+Shift+F9", Hotkey(6, 120)),
        ("Win+Z", Hotkey(8, 90)),
        ("Alt+F24", Hotkey(1, 135)),
    ],
)
def test_shortcut_parsing(text, expected):
    assert parse_hotkey(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "Space", "Ctrl+Ctrl+Z", "Ctrl+F25", "Hyper+A", "Ctrl+é", "Ctrl+A, Ctrl+B", "Ctrl+Alt+"],
)
def test_shortcut_rejects_ambiguous_or_unmodified_input(text):
    with pytest.raises(ValueError):
        parse_hotkey(text)


@pytest.mark.parametrize(
    ("kind", "code", "amplitude", "rate", "channels"),
    [
        ("int16", "h", 8192, 16000, 1),
        ("int32", "i", 536870912, 48000, 2),
        ("float", "f", 0.25, 48000, 2),
        ("uint8", "B", 160, 8000, 1),
    ],
)
def test_capture_normalization_duration_channels_and_scale(
    tmp_path, kind, code, amplitude, rate, channels
):
    samples = array.array(code, [amplitude] * (rate * channels))
    if sys.byteorder != "little":
        samples.byteswap()
    source = tmp_path / "capture.pcm"
    source.write_bytes(samples.tobytes())
    result = normalize_capture(source, tmp_path / "recording.wav", rate, channels, kind)
    with wave.open(str(result), "rb") as audio:
        assert (
            audio.getnchannels(),
            audio.getsampwidth(),
            audio.getframerate(),
            audio.getnframes(),
        ) == (1, 2, 16000, 16000)
        values = array.array("h", audio.readframes(16000))
        if sys.byteorder != "little":
            values.byteswap()
        assert min(values) == max(values) == 8192


def test_capture_downmix_and_nonfinite_values(tmp_path):
    values = array.array("f", [math.nan, math.inf, -0.25, 0.25] * 2400)
    if sys.byteorder != "little":
        values.byteswap()
    source = tmp_path / "capture.pcm"
    source.write_bytes(values.tobytes())
    result = normalize_capture(source, tmp_path / "recording.wav", 48000, 2, "float")
    with wave.open(str(result), "rb") as audio:
        assert set(audio.readframes(audio.getnframes())) == {0}


@pytest.mark.parametrize(
    ("data", "message"), [(b"", "complete"), (b"a", "complete"), (b"00", "too short")]
)
def test_invalid_capture_remains_recoverable(tmp_path, data, message):
    source = tmp_path / "capture.pcm"
    source.write_bytes(data)
    with pytest.raises(ValueError, match=message):
        normalize_capture(source, tmp_path / "recording.wav", 16000, 1, "int16")
    assert source.read_bytes() == data
    assert not (tmp_path / "recording.wav").exists()


def test_capture_limit_checked_before_read(tmp_path):
    source = tmp_path / "capture.pcm"
    with source.open("wb") as target:
        target.truncate(120 * 16000 * 2 + 2)
    with pytest.raises(ValueError, match="limit"):
        normalize_capture(source, tmp_path / "recording.wav", 16000, 1, "int16")


def test_history_survives_restart_and_bad_neighbor_file(tmp_path):
    history = DictationHistory(tmp_path)
    history.save({"id": "first", "text": "Original", "raw": "Original", "created_at": "2026-10-01"})
    history.save(
        {"id": "second", "text": "Cleaned", "raw": "um Cleaned", "created_at": "2026-10-02"}
    )
    (history.root / "invalid.json").write_text("{", encoding="utf-8")
    loaded = DictationHistory(tmp_path).records()
    assert [r["id"] for r in loaded] == ["second", "first"]
    assert loaded[0]["raw"] == "um Cleaned"
    with pytest.raises(ValueError):
        history.save({"id": "../escape", "text": "bad"})


class InputAPI:
    def __init__(self):
        self.events = []
        self.count = None
        self.foreground = 123
        self.keys = set()

    def GetForegroundWindow(self):
        return self.foreground

    def GetAsyncKeyState(self, key):
        return 0x8000 if key in self.keys else 0

    def SendInput(self, count, batch, size):
        assert size == ctypes.sizeof(Input)
        self.events.extend((e.value.keyboard.scan, e.value.keyboard.flags) for e in batch)
        return count if self.count is None else self.count


@pytest.fixture
def native():
    value = WindowsInput.__new__(WindowsInput)
    value.api = InputAPI()
    target = FocusTarget(123, 456, "Test editor", True, identity="field1")
    value.current = lambda: target
    return SimpleNamespace(adapter=value, target=target, api=value.api)


def test_unicode_insertion_preserves_clipboard_without_paste(native):
    result = native.adapter.insert("Café 😀\nNext", native.target)
    assert result.inserted
    encoded = "Café 😀\rNext".encode("utf-16-le")
    expected = [int.from_bytes(encoded[i : i + 2], "little") for i in range(0, len(encoded), 2)]
    assert native.api.events == [(unit, flag) for unit in expected for flag in (4, 6)]


@pytest.mark.parametrize(
    "target",
    [
        FocusTarget(123, 456, "Test", False),
        FocusTarget(123, 456, "Test", True, password=True),
        FocusTarget(123, 456, "Test", True, elevated=True),
    ],
)
def test_unsafe_insertion_targets_receive_no_input(native, target):
    assert not native.adapter.insert("Text", target).inserted
    assert not native.api.events


def test_same_window_different_field_is_rejected(native):
    native.adapter.current = lambda: FocusTarget(123, 456, "Test", True, identity="field2")
    result = native.adapter.insert("Text", native.target)
    assert not result.inserted and "Focus changed" in result.reason
    assert not native.api.events


def test_focus_race_modifier_and_cancellation_receive_no_input(native):
    native.api.foreground = 999
    assert not native.adapter.insert("Text", native.target).inserted
    native.api.foreground = 123
    native.api.keys.add(17)
    assert not native.adapter.insert("Text", native.target).inserted
    native.api.keys.clear()
    assert not native.adapter.insert("Text", native.target, lambda: False).inserted
    assert not native.api.events


def test_partial_windows_input_failure_keeps_recoverable_text(native):
    native.api.count = 1
    result = native.adapter.insert("Text", native.target)
    assert not result.inserted
    assert result.fallback_text == "Text"
    assert "review" in result.reason


def test_quiet_capture_does_not_reach_recognition(tmp_path):
    source = tmp_path / "capture.pcm"
    source.write_bytes(b"\x01\x00" * 16000)
    with pytest.raises(ValueError, match="too quiet"):
        normalize_capture(source, tmp_path / "recording.wav", 16000, 1, "int16", require_sound=True)
    assert not (tmp_path / "recording.wav").exists()
    assert source.is_file()


def test_intermediate_focus_change_stops_unicode_groups(native):
    original = native.api.SendInput

    def change_focus(count, batch, size):
        result = original(count, batch, size)
        native.api.foreground = 999
        return result

    native.api.SendInput = change_focus
    result = native.adapter.insert("Before 😀 after", native.target)
    assert not result.inserted
    assert "review" in result.reason
    assert len(native.api.events) == 14  # Only the seven BMP characters preceding the emoji.
