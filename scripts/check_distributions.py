"""Check required modules and reject runtime/private files without extracting archives."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

PRIVATE_SUFFIXES = {".wav", ".mp3", ".m4a", ".mp4", ".onnx", ".bin", ".blob", ".pyc"}
PRIVATE_DIRECTORIES = {
    ".agent",
    ".agents",
    ".codex",
    ".git",
    ".venv",
    "__pycache__",
    "lectures",
    "recordings",
    "transcripts",
    "diagnostics",
    ".stubs",
    "reports",
    "models",
}


def check_names(names: set[str], required: set[str]) -> None:
    missing = required - names
    if missing:
        raise ValueError(f"distribution is missing: {sorted(missing)}")
    for name in sorted(names):
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe archive member: {name}")
        if (
            path.name == "AGENTS.md"
            or path.suffix.lower() in PRIVATE_SUFFIXES
            or any(
                part in PRIVATE_DIRECTORIES
                or part.startswith((".scratch", ".pytest", ".mypy", ".ruff"))
                for part in path.parts
            )
        ):
            raise ValueError(f"runtime/private artifact in distribution: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    wheels = sorted(args.directory.glob("*.whl"))
    sources = sorted(args.directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError("use a directory containing exactly one wheel and one source archive")
    root = Path(__file__).resolve().parents[1]
    modules = {
        str(p.relative_to(root / "src")).replace("\\", "/")
        for p in (root / "src" / "npu_scribe").glob("*.py")
    }
    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
        check_names(names, modules)
        if not any(name.endswith(".dist-info/entry_points.txt") for name in names):
            raise ValueError("wheel is missing launcher entry points")
    with tarfile.open(sources[0]) as archive:
        members = archive.getmembers()
        if any(not (member.isfile() or member.isdir()) for member in members):
            raise ValueError("source archive contains a link or special file")
        prefixes = {PurePosixPath(member.name).parts[0] for member in members}
        if len(prefixes) != 1:
            raise ValueError("source archive must have one root directory")
        names = {
            str(PurePosixPath(member.name).relative_to(next(iter(prefixes)))) for member in members
        }
        check_names(
            names,
            {
                "pyproject.toml",
                "README.md",
                "LICENSE",
                "docs/USER_GUIDE.md",
                "packaging/desktop_entry.py",
                "packaging/worker_entry.py",
                "packaging/npu-scribe.spec",
                "packaging/npu-scribe.iss",
                "packaging/bundle_assets.py",
                "packaging/collect_sources.py",
                "packaging/prepare_release.py",
                "packaging/third-party-sources.json",
                "packaging/LIBRARY_BUILD.md",
                "packaging/RELEASE_NOTES.md",
                "packaging/hooks/hook-PySide6.QtGui.py",
                "packaging/GettingStarted.html",
                "packaging/licenses/GPL-3.0.txt",
                "packaging/licenses/LGPL-3.0.txt",
                "packaging/licenses/LGPL-2.1.txt",
                "scripts/check_distributions.py",
                "scripts/smoke_installed.py",
                *{f"src/{m}" for m in modules},
            },
        )
    print("Wheel/source contents passed: required modules present; no checked runtime artifacts.")


if __name__ == "__main__":
    main()
