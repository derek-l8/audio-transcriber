from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FocusTarget:
    handle: int
    process_id: int
    application: str
    editable: bool
    password: bool = False
    elevated: bool = False
    identity: str = ""


@dataclass(frozen=True)
class InsertResult:
    inserted: bool
    fallback_text: str
    reason: str | None = None


class Clipboard(Protocol):
    def snapshot(self) -> object: ...
    def set_text(self, text: str) -> None: ...
    def restore(self, snapshot: object) -> None: ...


class FocusProvider(Protocol):
    def current(self) -> FocusTarget: ...


class PasteSender(Protocol):
    def paste(self, target: FocusTarget) -> bool: ...


class SafeInserter:
    """Transactional insertion; target/platform discovery is delegated and testable."""

    def __init__(self, clipboard: Clipboard, focus: FocusProvider, sender: PasteSender):
        self.clipboard, self.focus, self.sender = clipboard, focus, sender

    def insert(self, text: str, intended: FocusTarget) -> InsertResult:
        if not text:
            return InsertResult(False, text, "empty result")
        if not intended.editable or intended.password:
            return InsertResult(False, text, "unsafe or non-editable target")
        if intended.elevated:
            return InsertResult(False, text, "elevation boundary")
        current = self.focus.current()
        if (current.handle, current.process_id, current.identity) != (
            intended.handle,
            intended.process_id,
            intended.identity,
        ):
            return InsertResult(False, text, "focus changed")
        snapshot = self.clipboard.snapshot()
        try:
            self.clipboard.set_text(text)
            if not self.sender.paste(intended):
                return InsertResult(False, text, "paste rejected")
            return InsertResult(True, text)
        finally:
            self.clipboard.restore(snapshot)
