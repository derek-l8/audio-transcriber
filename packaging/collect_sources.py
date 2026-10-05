"""Download pinned library sources and prepare local binary-release materials."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def notices(archives: list[Path]) -> str:
    parts = [
        "Qt / PySide and third-party source notices\n",
        "Copyright (C) The Qt Company Ltd. and other contributors.\n",
        "The following attribution and license files come from the supplied upstream sources.\n",
        "They include notices for source tools and optional components as well as libraries.\n",
        "FFmpeg DLLs report 7.1.5; see LIBRARY_BUILD.md for the attribution mismatch.\n",
    ]
    for archive in archives:
        with tarfile.open(archive, mode="r|*") as source:
            for member in source:
                name = Path(member.name).name.lower()
                license_file = name.startswith(("license", "copying", "copyright", "notice"))
                attribution = name == "qt_attribution.json"
                if not member.isfile() or not (license_file or attribution):
                    continue
                stream = source.extractfile(member)
                if stream is None:
                    raise RuntimeError(f"Unreadable source notice: {member.name}")
                content = stream.read().decode("utf-8", errors="replace")
                parts.extend([f"\n--- {archive.name}: {member.name} ---\n", content, "\n"])
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / ".scratch/library-sources")
    args = parser.parse_args()
    cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    manifest = ROOT / "packaging/third-party-sources.json"
    records = json.loads(manifest.read_text(encoding="utf-8"))
    archives = []
    for record in records:
        name = record["file"]
        if Path(name).name != name:
            raise RuntimeError("Source manifest filenames must be plain filenames")
        path = cache / name
        if not path.exists():
            if not record["url"].startswith("https://"):
                raise RuntimeError("Source downloads require HTTPS")
            temporary = path.with_suffix(path.suffix + ".part")
            with urllib.request.urlopen(record["url"], timeout=60) as response:  # noqa: S310
                with temporary.open("wb") as target:
                    while chunk := response.read(1024 * 1024):
                        target.write(chunk)
            if digest(temporary) != record["sha256"]:
                raise RuntimeError(f"Source hash mismatch: {name}")
            temporary.replace(path)
        if digest(path) != record["sha256"]:
            raise RuntimeError(f"Cached source hash mismatch: {name}")
        archives.append(path)
        print(f"Verified {name}", flush=True)
    materials = ROOT / "build/source-materials"
    materials.mkdir(parents=True, exist_ok=True)
    notice = materials / "qt-third-party-notices.txt"
    notice.write_text(notices(archives), encoding="utf-8")
    (materials / "source-notices.json").write_text(
        json.dumps({"manifest_sha256": digest(manifest), "notices_sha256": digest(notice)}) + "\n",
        encoding="utf-8",
    )
    destination = ROOT / "dist/release"
    destination.mkdir(parents=True, exist_ok=True)
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    bundle = destination / f"npu-scribe-{version}-library-sources.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_STORED) as output:
        for archive in archives:
            output.write(archive, "upstream/" + archive.name)
        output.write(manifest, manifest.name)
        output.write(ROOT / "packaging/LIBRARY_BUILD.md", "LIBRARY_BUILD.md")
        output.write(notice, notice.name)
    print(f"Created {bundle.name}: {bundle.stat().st_size} bytes")


if __name__ == "__main__":
    main()
