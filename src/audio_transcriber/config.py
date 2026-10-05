from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROCESSING_DEFAULTS = {
    "lecture": ("light", "structured"),
    "dictation": ("medium", "prose"),
}


@dataclass(frozen=True)
class DataLocation:
    proposed: Path
    likely_synced: bool
    local_fallback: Path


def propose_windows_data_location(home: Path, env: dict[str, str] | None = None) -> DataLocation:
    values = env or os.environ
    desktop = home / "Desktop" / "Audio Transcriber"
    onedrive = values.get("OneDrive") or values.get("OneDriveConsumer")
    likely = _within(desktop, Path(onedrive)) if onedrive else False
    return DataLocation(desktop, likely, home / "AppData" / "Local" / "Audio Transcriber Data")


def _within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
