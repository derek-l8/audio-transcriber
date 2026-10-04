"""Windows shortcuts and Unicode insertion. No clipboard transaction is needed."""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from ctypes import wintypes
from typing import Any

from .dictation import Hotkey
from .insertion import FocusTarget, InsertResult

# Only metadata is queried: no target text, name, clipboard, or surrounding content.
FOCUS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$e = [System.Windows.Automation.AutomationElement]::FocusedElement
$c = $e.Current
$editable = $false
$p = $null
if ($e.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern,[ref]$p)) {
    $editable = -not $p.Current.IsReadOnly
} elseif ($e.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern,[ref]$p)) {
    $attribute = [System.Windows.Automation.TextPattern]::IsReadOnlyAttribute
    $v = $p.DocumentRange.GetAttributeValue($attribute)
    $editable = ($v -is [bool]) -and (-not $v)
}
@{pid=$c.ProcessId;password=$c.IsPassword;
  editable=($editable -and $c.IsEnabled -and $c.HasKeyboardFocus);
  identity=($e.GetRuntimeId() -join '.')} | ConvertTo-Json -Compress
"""


class KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("vk", wintypes.WORD),
        ("scan", wintypes.WORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra", ctypes.c_size_t),
    ]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("data", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra", ctypes.c_size_t),
    ]


class InputUnion(ctypes.Union):
    _fields_ = [("keyboard", KeyboardInput), ("mouse", MouseInput)]


class Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("value", InputUnion)]


class WindowsInput:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Global shortcuts and automatic insertion require Windows.")
        self.api: Any = ctypes.WinDLL("user32", use_last_error=True)
        self.api.GetForegroundWindow.restype = wintypes.HWND
        self.api.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.api.GetAsyncKeyState.restype = ctypes.c_short
        self.api.RegisterHotKey.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        ]
        self.api.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.api.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
        self.api.SendInput.restype = wintypes.UINT

    def register(self, ident: int, hotkey: Hotkey) -> None:
        if not self.api.RegisterHotKey(None, ident, hotkey.modifiers | 0x4000, hotkey.key):
            raise OSError("Shortcut is unavailable or already in use. Choose another shortcut.")

    def unregister(self, ident: int) -> None:
        self.api.UnregisterHotKey(None, ident)

    def held(self, key: int) -> bool:
        return bool(self.api.GetAsyncKeyState(key) & 0x8000)

    def current(self) -> FocusTarget:
        before = int(self.api.GetForegroundWindow() or 0)
        executable = shutil.which("powershell.exe")
        if not executable:
            raise OSError("Windows PowerShell is unavailable; use the recovered copy.")
        result = subprocess.run(  # noqa: S603 -- fixed script; executable resolved locally
            [executable, "-NoProfile", "-NonInteractive", "-Command", FOCUS_SCRIPT],
            capture_output=True,
            timeout=5,
            check=True,
            creationflags=0x08000000,
        )  # noqa: S603
        value = json.loads(result.stdout.decode("utf-8-sig"))
        after = int(self.api.GetForegroundWindow() or 0)
        editable = before == after and bool(value["editable"]) and int(value["pid"]) != os.getpid()
        return FocusTarget(
            after,
            int(value["pid"]),
            "Windows application",
            editable,
            bool(value["password"]),
            identity=str(value["identity"]),
        )

    def insert(
        self, text: str, intended: FocusTarget, allowed: Callable[[], bool] = lambda: True
    ) -> InsertResult:
        if not text or not intended.editable or intended.password or intended.elevated:
            return InsertResult(False, text, "Target is not a supported editable field.")
        try:
            current = self.current()
        except (OSError, ValueError, subprocess.SubprocessError):
            return InsertResult(False, text, "Could not verify the target field.")
        if (
            (current.handle, current.process_id, current.identity)
            != (intended.handle, intended.process_id, intended.identity)
            or not current.editable
            or current.password
        ):
            return InsertResult(False, text, "Focus changed; text was saved instead.")
        if any(self.held(key) for key in (16, 17, 18, 91, 92)):
            return InsertResult(False, text, "Release modifier keys and use the recovered copy.")
        if not allowed():
            return InsertResult(False, text, "Insertion cancelled; text was saved instead.")
        if int(self.api.GetForegroundWindow() or 0) != intended.handle:
            return InsertResult(False, text, "Focus changed; text was saved instead.")
        # Some Windows edit frameworks dispatch surrogate pairs through the input
        # method ahead of queued BMP characters. Flush between those groups.
        runs: list[str] = []
        plain = ""
        for char in text.replace("\r\n", "\n").replace("\n", "\r"):
            if ord(char) > 0xFFFF:
                if plain:
                    runs.append(plain)
                    plain = ""
                runs.append(char)
            else:
                plain += char
        if plain:
            runs.append(plain)
        for index, run in enumerate(runs):
            if not allowed() or int(self.api.GetForegroundWindow() or 0) != intended.handle:
                return InsertResult(
                    False, text, "Insertion stopped; review the field before copying."
                )
            units = run.encode("utf-16-le")
            events = []
            for i in range(0, len(units), 2):
                unit = int.from_bytes(units[i : i + 2], "little")
                for flag in (4, 6):
                    events.append(Input(1, InputUnion(keyboard=KeyboardInput(0, unit, flag, 0, 0))))
            batch = (Input * len(events))(*events)
            count = self.api.SendInput(len(batch), batch, ctypes.sizeof(Input))
            if count != len(batch):
                return InsertResult(
                    False, text, "Windows rejected some input; review the field before copying."
                )
            if index < len(runs) - 1:
                time.sleep(0.05)
        return InsertResult(True, text)
