"""Assemble local release attachments; this does not commit, tag or publish."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(*arguments: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("Git is needed to record the local release revision")
    return subprocess.check_output(  # noqa: S603 - fixed read-only Git calls
        [executable, *arguments], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def main() -> None:
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = configuration["project"]["version"]
    destination = ROOT / "dist/release"
    source = destination / f"npu_scribe-{version}.tar.gz"
    wheel = destination / f"npu_scribe-{version}-py3-none-any.whl"
    libraries = destination / f"npu-scribe-{version}-library-sources.zip"
    installer = ROOT / f"dist/installer/npu-scribe-{version}-windows-x64.exe"
    bundle = ROOT / "dist/NPU Scribe"
    bundle_files = sorted(p for p in bundle.rglob("*") if p.is_file())
    if not bundle_files or not installer.is_file():
        raise RuntimeError("Build the bundle and installer first")
    if installer.stat().st_mtime < max(p.stat().st_mtime for p in bundle_files):
        raise RuntimeError("The installer predates the bundle; compile it again")
    manifest = ROOT / "packaging/third-party-sources.json"
    with zipfile.ZipFile(libraries) as archive:
        if archive.read(manifest.name) != manifest.read_bytes():
            raise RuntimeError("Library source manifest changed; rerun collect_sources.py")
        for record in json.loads(manifest.read_text(encoding="utf-8")):
            with archive.open("upstream/" + record["file"]) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != record["sha256"]:
                    raise RuntimeError("Library source archive hash mismatch")
    source_hashes = {}
    with tarfile.open(source) as archive:
        for member in archive.getmembers():
            relative = Path(*Path(member.name).parts[1:])
            local = ROOT / relative
            if not member.isfile() or not local.is_file():
                continue
            stream = archive.extractfile(member)
            if stream is None or hashlib.file_digest(stream, "sha256").hexdigest() != digest(local):
                raise RuntimeError(f"Source archive predates an edit: {relative}")
            source_hashes[relative.as_posix()] = digest(local)
    included = {
        Path(p.lstrip("/"))
        for p in configuration["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    }
    current_files = {
        name
        for name in git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")
        if name
        and (ROOT / name).is_file()
        and any(Path(name) == p or p in Path(name).parents for p in included)
    }
    missing = current_files - source_hashes.keys()
    if missing:
        raise RuntimeError(f"Source archive omits current files; rebuild it: {sorted(missing)}")
    with zipfile.ZipFile(wheel) as archive:
        for file in (ROOT / "src/npu_scribe").glob("*.py"):
            if archive.read("npu_scribe/" + file.name) != file.read_bytes():
                raise RuntimeError(f"Wheel predates an edit: {file.name}")
    target = destination / installer.name
    shutil.copy2(installer, target)
    attachments = [target, source, wheel, libraries]
    records = [
        {"file": p.name, "bytes": p.stat().st_size, "sha256": digest(p)} for p in attachments
    ]
    payload = {
        "version": version,
        "local_base_commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "working_tree_changes": git("status", "--short").splitlines(),
        "source_sha256": source_hashes,
        "bundle_sha256": hashlib.sha256(
            json.dumps(
                {p.relative_to(bundle).as_posix(): digest(p) for p in bundle_files},
                sort_keys=True,
            ).encode()
        ).hexdigest(),
        "attachments": records,
        "upload_files": [p.name for p in attachments] + ["release-manifest.json", "SHA256SUMS.txt"],
        "unsigned": True,
        "published": False,
    }
    output = destination / "release-manifest.json"
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    checksum_records = [*records, {"file": output.name, "sha256": digest(output)}]
    (destination / "SHA256SUMS.txt").write_text(
        "".join(f"{r['sha256']}  {r['file']}\n" for r in checksum_records), encoding="utf-8"
    )
    shutil.copy2(ROOT / "packaging/RELEASE_NOTES.md", destination / "RELEASE_NOTES.md")
    print("Prepared installer, app source/wheel, library sources, manifest and checksums.")
    if payload["working_tree_changes"]:
        print("Commit the reviewed source before choosing a release tag target.")
    else:
        print("Recorded the committed source revision; the release remains unpublished.")


if __name__ == "__main__":
    main()
