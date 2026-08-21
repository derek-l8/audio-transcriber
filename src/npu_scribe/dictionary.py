from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .storage import atomic_json


@dataclass(frozen=True)
class DictionaryEntry:
    spoken: str
    written: str


class PersonalDictionary:
    def __init__(self, entries: list[DictionaryEntry] | None = None):
        self.entries = entries or []
        keys = [e.spoken.casefold() for e in self.entries]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate or conflicting dictionary entries")

    def apply(self, text: str) -> tuple[str, tuple[str, ...]]:
        applied: list[str] = []
        for entry in sorted(self.entries, key=lambda e: len(e.spoken), reverse=True):
            text, count = re.subn(
                rf"\b{re.escape(entry.spoken)}\b", entry.written, text, flags=re.IGNORECASE
            )
            if count:
                applied.append(entry.spoken)
        return text, tuple(applied)

    def export(self, path: Path) -> None:
        atomic_json(path, {"schema_version": 1, "entries": [e.__dict__ for e in self.entries]})

    @classmethod
    def load(cls, path: Path) -> PersonalDictionary:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1 or not isinstance(data.get("entries"), list):
            raise ValueError("unsupported dictionary schema")
        return cls([DictionaryEntry(str(e["spoken"]), str(e["written"])) for e in data["entries"]])
