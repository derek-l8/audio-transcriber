"""Explicit model acquisition: manifest-approved downloads with staged verification.

Ordinary transcription NEVER touches this module or the network. Downloads happen
only through `npu-scribe models download MODEL_ID` or the evaluation harness.

Security policy enforced here:
- Only manifest-approved model identifiers and HTTPS hosts are allowed.
- URLs are constructed from manifest fields; user input never becomes URL syntax.
- No pickle-based files, no `trust_remote_code`, no repository scripts: every
  approved artifact is OpenVINO IR plus OpenVINO Tokenizers files only.
- Files are staged in a temporary directory, size-capped, checksum-verified, and
  checked for symlinks or unexpected content before an atomic rename promotion.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ALLOWED_HOSTS = frozenset({"huggingface.co"})
MAX_MODEL_BYTES = 2 * 1024 * 1024 * 1024  # ~2 GB installed-size budget per candidate
READ_CHUNK = 1024 * 1024


class AcquisitionError(Exception):
    """Clear failure for disallowed models, bad manifests, or corrupt downloads."""


@dataclass(frozen=True)
class ModelFile:
    name: str
    sha256: str
    size: int


@dataclass(frozen=True)
class ModelSpec:
    id: str
    repo: str
    revision: str
    role: str  # "development-proof" | "candidate"
    language: str
    multilingual: bool
    license: str
    license_url: str
    requires_remote_code: bool
    serialization: str
    min_openvino_genai: str
    files: tuple[ModelFile, ...]
    source_url: str
    notes: str = ""

    @property
    def download_bytes(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def integrity(self) -> str:
        digest = hashlib.sha256()
        for entry in sorted(self.files, key=lambda f: f.name):
            digest.update(f"{entry.name}:{entry.sha256}\n".encode())
        return digest.hexdigest()

    def url_for(self, name: str) -> str:
        segments = f"{self.repo}/{self.revision}/{name}".split("/")
        if any(part in ("", ".", "..") or "/" in part for part in segments):
            raise AcquisitionError("manifest fields contain unsafe path segments")
        url = f"https://{sorted(ALLOWED_HOSTS)[0]}/{self.repo}/resolve/{self.revision}/{name}"
        host = urllib.parse.urlsplit(url).hostname
        if host not in ALLOWED_HOSTS:
            raise AcquisitionError(f"host {host} is not approved")
        if not url.startswith("https://"):
            raise AcquisitionError("only HTTPS sources are allowed")
        return url


def _spec(
    model_id: str,
    repo: str,
    revision: str,
    role: str,
    files: dict[str, tuple[int, str]],
    source_note: str,
    notes: str = "",
) -> ModelSpec:
    return ModelSpec(
        id=model_id,
        repo=repo,
        revision=revision,
        role=role,
        language="en",
        multilingual=False,
        license="Apache-2.0",
        license_url="https://huggingface.co/" + repo + "/blob/main/LICENSE",
        requires_remote_code=False,
        serialization="openvino-ir+tokenizers (no pickle)",
        min_openvino_genai="2026.3.0",
        files=tuple(ModelFile(n, sha, size) for n, (size, sha) in sorted(files.items())),
        source_url=f"https://huggingface.co/{repo} @ {revision} ({source_note})",
        notes=notes,
    )


_TINY_FILES: dict[str, tuple[int, str]] = {
    "README.md": (4309, "7b3a4bf3ddb965113afb0ab8051fc877b0ef8d4cf8a37c941e7762ed4f345237"),
    "added_tokens.json": (
        34604,
        "560be47bea388757f8d4cc185c5d82067426cbb6361e38016dd90ddc01ab203a",
    ),
    "config.json": (1272, "8e97a29f1f8d18ccb5e681d82ef13d68f4f7f74f0880c737e5e12315bf3404d6"),
    "generation_config.json": (
        1616,
        "6a93098954b90eaf273a21e63cf3e45f814ef72275faa74589b645e44c40ac9a",
    ),
    "merges.txt": (456318, "1ce1664773c50f3e0cc8842619a93edc4624525b728b188a9e0be33b7726adc5"),
    "normalizer.json": (
        52666,
        "bf1c507dc8724ca9cf9903640dacfb69dae2f00edee4f21ceba106a7392f26dd",
    ),
    "openvino_config.json": (
        449,
        "275065fa9dd91cc44574367783325c05ca53cf6e39f3cddb867dc7cf9b89edf0",
    ),
    "openvino_decoder_model.bin": (
        25255392,
        "e133f3fd1745dff94562ba8282fecab354141c38e9a95ec7832a13365dd1a271",
    ),
    "openvino_decoder_model.xml": (
        430933,
        "7662e7b7bc65c0b263529cdcb310d2c929f75900ea5f7ea91f603654660f4997",
    ),
    "openvino_detokenizer.bin": (
        749930,
        "7045e2ab69c216fa4ef1d129fcce4d36bcf5583f01b823279278b52626238e0c",
    ),
    "openvino_detokenizer.xml": (
        9699,
        "df817c6e58fe9280f9d8680b8b1fcd9af5954204917b9de0cece77a369227f14",
    ),
    "openvino_encoder_model.bin": (
        6882592,
        "34b25ed703164b7bac0d57a6176348087346e083368e6d2eb0d6ce3778519252",
    ),
    "openvino_encoder_model.xml": (
        227102,
        "983a43e864e217f3475a0751f7230bbe497c1301242ff8d302a5b65b536df5ee",
    ),
    "openvino_tokenizer.bin": (
        1926439,
        "8c9def49b61ff1cdd929b1c4b035e6714f69157587ada9cbb61cb15d6248ea2b",
    ),
    "openvino_tokenizer.xml": (
        27011,
        "64e0c8309a4901ef7369dc22d1271b9188c14813259f8006141d5b7267053f71",
    ),
    "preprocessor_config.json": (
        356,
        "994838f1fa6462c8b9b3c90edada831f11f3dd8b4664634e18f4694d005c9dbf",
    ),
    "special_tokens_map.json": (
        2173,
        "98bdf3ec5b32e31575b02f64b0a32bde7c0449075d34484a7df9bdd3cdeb9fb9",
    ),
    "tokenizer.json": (
        3855707,
        "287537d5be89a39bd18e7e3875ad9900faa668493fb759392b8f52a492eca5db",
    ),
    "tokenizer_config.json": (
        282692,
        "7498445adabf4fd836db90b0f0d979ca9dc0b543528e5d9f1912430a5879e212",
    ),
    "vocab.json": (798156, "3ba3c3109ff33976c4bd966589c11ee14fcaa1f4c9e5e154c2ed7f99d80709e7"),
}

_BASE_FILES: dict[str, tuple[int, str]] = {
    "README.md": (4256, "7bbae3c5e222ab05c1cac21f52bc1e81a03ea829316d9fcc81fcbd7a8240e2e2"),
    "added_tokens.json": (
        34604,
        "560be47bea388757f8d4cc185c5d82067426cbb6361e38016dd90ddc01ab203a",
    ),
    "config.json": (1272, "ae9ba0d02f244aa48df4d8637fcf3ce517229fb9148ecef13d44ac83b7e2a6c3"),
    "generation_config.json": (
        1526,
        "7eb6f9dca9df06ca5ae8ed43ee5b05b200af22fedbb3fe7e0f10ea354e44b641",
    ),
    "merges.txt": (456318, "1ce1664773c50f3e0cc8842619a93edc4624525b728b188a9e0be33b7726adc5"),
    "normalizer.json": (
        52666,
        "bf1c507dc8724ca9cf9903640dacfb69dae2f00edee4f21ceba106a7392f26dd",
    ),
    "openvino_config.json": (
        449,
        "0df030689716fda7e84b202a90c49e5a8123d43b3b74a444c913c2b8ada484d5",
    ),
    "openvino_decoder_model.bin": (
        40228320,
        "c1c6c3c15596ebdb06cce5d73441a361112314869a1807a28164ba5bae64331e",
    ),
    "openvino_decoder_model.xml": (
        627401,
        "5c7ff1a29d92d56d0ef73aa2ba3987b34ed8d83b826ea2b2d987e029d868ed5d",
    ),
    "openvino_detokenizer.bin": (
        749930,
        "7045e2ab69c216fa4ef1d129fcce4d36bcf5583f01b823279278b52626238e0c",
    ),
    "openvino_detokenizer.xml": (
        9699,
        "15699b574239b9d4e6ce9e37a97db2b179d3907f4afb8ee7f7950b61bb9f6902",
    ),
    "openvino_encoder_model.bin": (
        14451360,
        "a416a67095135c5cab37d2cad66ca637638257f39081ce987983e2209689405a",
    ),
    "openvino_encoder_model.xml": (
        332326,
        "9dffc149d8726bdbb980c45f191a61bc8cc3e1beb9729dbf6c92bd326b55e017",
    ),
    "openvino_tokenizer.bin": (
        1926439,
        "8c9def49b61ff1cdd929b1c4b035e6714f69157587ada9cbb61cb15d6248ea2b",
    ),
    "openvino_tokenizer.xml": (
        27011,
        "e23e9eb65cd4e0cfd7425a6a329dda7a961453fcdcec6ba4d8e8d0614b239e9a",
    ),
    "preprocessor_config.json": (
        356,
        "994838f1fa6462c8b9b3c90edada831f11f3dd8b4664634e18f4694d005c9dbf",
    ),
    "special_tokens_map.json": (
        2173,
        "98bdf3ec5b32e31575b02f64b0a32bde7c0449075d34484a7df9bdd3cdeb9fb9",
    ),
    "tokenizer.json": (
        3855707,
        "287537d5be89a39bd18e7e3875ad9900faa668493fb759392b8f52a492eca5db",
    ),
    "tokenizer_config.json": (
        282692,
        "7498445adabf4fd836db90b0f0d979ca9dc0b543528e5d9f1912430a5879e212",
    ),
    "vocab.json": (798156, "3ba3c3109ff33976c4bd966589c11ee14fcaa1f4c9e5e154c2ed7f99d80709e7"),
}

MANIFEST: dict[str, ModelSpec] = {
    spec.id: spec
    for spec in [
        _spec(
            "whisper-tiny.en-int4-ov",
            "OpenVINO/whisper-tiny.en-int4-ov",
            "2c4a4cb35a33f827f324c55f474d9197c586b485",
            "development-proof",
            _TINY_FILES,
            "checksums recorded from the sandbox feasibility download",
            "Lightweight development/proof model only; not recommended for real use.",
        ),
        _spec(
            "whisper-base.en-int4-ov",
            "OpenVINO/whisper-base.en-int4-ov",
            "b0da25f7e43548df7f35fb69fc7609c08242150a",
            "candidate",
            _BASE_FILES,
            "checksums recorded during manifest authoring",
            "Candidate awaiting Windows accuracy/speed validation; no default-model claim.",
        ),
    ]
}


def get_spec(model_id: str) -> ModelSpec:
    try:
        return MANIFEST[model_id]
    except KeyError:
        raise AcquisitionError(
            f"model '{model_id}' is not manifest-approved; run 'npu-scribe models list'"
        ) from None


Fetcher = Callable[[str, Path, int], None]


def https_fetcher(max_bytes: int = MAX_MODEL_BYTES) -> Fetcher:
    def fetch(url: str, destination: Path, expected_size: int) -> None:
        if expected_size > max_bytes:
            raise AcquisitionError("manifest file exceeds the configured size limit")
        limit = max(expected_size, max_bytes)
        received = 0
        # URL is manifest-constructed HTTPS only (see ModelSpec.url_for).
        with (
            urllib.request.urlopen(url, timeout=120) as response,  # noqa: S310
            destination.open("wb") as out,
        ):
            while chunk := response.read(READ_CHUNK):
                received += len(chunk)
                if received > limit:
                    raise AcquisitionError("download exceeded the expected size limit")
                out.write(chunk)

    return fetch


def verify_installed(models_root: Path, spec: ModelSpec) -> Path | None:
    """Return the install directory when complete and intact; otherwise None."""
    final_dir = models_root / spec.id
    if not final_dir.is_dir():
        return None
    for entry in final_dir.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise AcquisitionError(f"installed model contains unsafe entries: {entry.name}")
    for expected in spec.files:
        path = final_dir / expected.name
        if not path.is_file():
            return None
        if path.stat().st_size != expected.size:
            raise AcquisitionError(f"installed {expected.name} has an unexpected size")
        if _sha256(path) != expected.sha256:
            raise AcquisitionError(f"installed {expected.name} fails its integrity check")
    extra = {p.name for p in final_dir.iterdir()} - {f.name for f in spec.files}
    if extra:
        raise AcquisitionError(f"installed model contains unexpected files: {sorted(extra)}")
    return final_dir


def download_model(
    model_id: str,
    models_root: Path,
    fetcher: Fetcher | None = None,
) -> Path:
    """Stage, verify, and atomically promote a manifest-approved model."""
    spec = get_spec(model_id)
    if spec.requires_remote_code:
        raise AcquisitionError("models requiring remote code execution are rejected")
    existing = verify_installed(models_root, spec)
    if existing is not None:
        return existing
    fetch = fetcher or https_fetcher()
    models_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".stage-{spec.id}-", dir=models_root))
    try:
        expected_names = set()
        for entry in spec.files:
            expected_names.add(entry.name)
            target = stage / entry.name
            fetch(spec.url_for(entry.name), target, entry.size)
            if target.is_symlink() or not target.is_file():
                raise AcquisitionError(f"staged {entry.name} is not a plain file")
            actual_size = target.stat().st_size
            if actual_size != entry.size:
                raise AcquisitionError(
                    f"staged {entry.name} size mismatch ({actual_size} != {entry.size})"
                )
            actual_digest = _sha256(target)
            if actual_digest != entry.sha256:
                raise AcquisitionError(f"staged {entry.name} failed its SHA-256 check")
        extras = {p.name for p in stage.iterdir()} - expected_names
        if extras:
            raise AcquisitionError(f"unexpected staged content: {sorted(extras)}")
        final_dir = models_root / spec.id
        os.rename(stage, final_dir)
        return final_dir
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(READ_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
