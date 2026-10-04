"""Collect runtime notices from the exact environment used for a Windows build."""

from __future__ import annotations

import hashlib
import json
import sys
from importlib.metadata import distribution
from pathlib import Path

from packaging.requirements import Requirement


def collect_notices(root: Path, output: Path) -> list[tuple[str, str]]:
    output.mkdir(parents=True, exist_ok=True)
    files: list[tuple[str, str]] = []
    inventory = []
    pending = ["platformdirs", "PySide6", "openvino", "openvino-genai", "pyinstaller"]
    visited = set()
    while pending:
        dist = distribution(pending.pop())
        name = dist.metadata["Name"]
        key = name.lower().replace("_", "-")
        if key in visited:
            continue
        visited.add(key)
        copied = []
        for item in dist.files or ():
            text = str(item)
            if ".dist-info/" not in text or not any(
                token in text.lower() for token in ("license", "copying", "notice", "licensing")
            ):
                continue
            source = Path(dist.locate_file(item))
            if not source.is_file():
                raise FileNotFoundError(f"Missing notice for {name}: {item}")
            relative = Path(*Path(text).parts[1:])
            target = Path("licenses") / key / relative.parent
            files.append((str(source), str(target)))
            copied.append(
                {
                    "file": str(target / source.name).replace("\\", "/"),
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                }
            )
        if not copied:
            raise RuntimeError(f"No runtime notices found for {name}")
        inventory.append({"package": name, "version": dist.version, "notices": copied})
        for dependency in () if key == "pyinstaller" else dist.requires or ():
            requirement = Requirement(dependency)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise FileNotFoundError("Python LICENSE.txt is required")
    files.append((str(python_license), "licenses/python"))
    files.extend(
        (str(file), "licenses")
        for file in (root / "packaging/licenses").iterdir()
        if file.is_file()
    )
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        files.append((str(root / name), "licenses"))
    index = output / "runtime-inventory.json"
    index.write_text(
        json.dumps({"python": sys.version.split()[0], "packages": inventory}, indent=2) + "\n",
        encoding="utf-8",
    )
    files.append((str(index), "licenses"))
    return files
