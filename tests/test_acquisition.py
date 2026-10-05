from __future__ import annotations

import hashlib
import os
import socket
from pathlib import Path

import pytest

from audio_transcriber.acquisition import (
    MANIFEST,
    AcquisitionError,
    ModelFile,
    ModelSpec,
    download_model,
    get_spec,
    verify_installed,
)


def local_fetcher(root: Path):
    """Deterministic stand-in for HTTPS: copies files from a fixture directory."""

    def fetch(url: str, destination: Path, expected_size: int) -> None:
        assert url.startswith("https://huggingface.co/")
        name = destination.name
        source = root / name
        if not source.is_file():
            raise FileNotFoundError(name)
        destination.write_bytes(source.read_bytes())

    return fetch


@pytest.fixture
def tiny_fixture(tmp_path: Path) -> Path:
    """A synthetic two-file 'model' with real checksums recorded in a local spec."""
    root = tmp_path / "fixture"
    root.mkdir()
    (root / "openvino_encoder_model.bin").write_bytes(b"\x01" * 1000)
    (root / "tokenizer.json").write_bytes(b"{}\n")
    return root


def local_spec(tmp_path: Path) -> ModelSpec:
    def digest(name: str) -> tuple[int, str]:
        data = (tmp_path / "fixture" / name).read_bytes()
        return len(data), hashlib.sha256(data).hexdigest()

    sizes = {name: digest(name) for name in ("openvino_encoder_model.bin", "tokenizer.json")}
    spec = ModelSpec(
        id="synthetic-model",
        repo="example/synthetic",
        revision="deadbeef",
        role="development-proof",
        language="en",
        multilingual=False,
        license="Apache-2.0",
        license_url="https://example.com/license",
        requires_remote_code=False,
        serialization="openvino-ir+tokenizers (no pickle)",
        min_openvino_genai="2026.3.0",
        files=tuple(ModelFile(n, sha, size) for n, (size, sha) in sorted(sizes.items())),
        source_url="synthetic fixture",
    )
    return spec


def test_bundled_manifest_entries_are_safe() -> None:
    assert MANIFEST, "manifest must not be empty"
    for spec in MANIFEST.values():
        assert spec.requires_remote_code is False
        assert spec.serialization.startswith("openvino-ir")
        assert ".pkl" not in " ".join(f.name for f in spec.files)
        assert spec.license
        assert spec.revision and len(spec.revision) >= 40
        total = spec.download_bytes
        assert 0 < total <= 6 * 1024**3, f"{spec.id} exceeds the text-model asset budget"
        names = [f.name for f in spec.files]
        assert len(names) == len(set(names))
        assert all(not n.endswith((".py", ".pkl", ".pt", ".pth")) for n in names)


def test_unknown_model_is_refused() -> None:
    with pytest.raises(AcquisitionError, match="not manifest-approved"):
        get_spec("some-random-model")


def test_download_with_synthetic_spec(tmp_path: Path, tiny_fixture: Path, monkeypatch) -> None:
    models = tmp_path / "models"
    spec = local_spec(tmp_path)
    monkeypatch.setitem(MANIFEST, spec.id, spec)
    result = download_model(spec.id, models, local_fetcher(tiny_fixture))
    assert result == models / spec.id
    assert sorted(p.name for p in result.iterdir()) == sorted(f.name for f in spec.files)
    assert verify_installed(models, spec) == result
    # Idempotent: a second run verifies rather than re-downloading.
    again = download_model(spec.id, models, lambda *a: (_ for _ in ()).throw(AssertionError()))
    assert again == result


def test_checksum_failure_quarantines_staging(
    tmp_path: Path, tiny_fixture: Path, monkeypatch
) -> None:
    models = tmp_path / "models"
    spec = local_spec(tmp_path)
    tampered = ModelFile(spec.files[0].name, "0" * 64, spec.files[0].size)
    files = list(spec.files)
    files[0] = tampered
    bad_spec = ModelSpec(**{**spec.__dict__, "files": tuple(files)})
    monkeypatch.setitem(MANIFEST, bad_spec.id, bad_spec)
    with pytest.raises(AcquisitionError, match="SHA-256"):
        download_model(bad_spec.id, models, local_fetcher(tiny_fixture))
    assert not models.exists() or not any(models.iterdir())


def test_size_mismatch_rejected_and_cleaned(
    tmp_path: Path, tiny_fixture: Path, monkeypatch
) -> None:
    models = tmp_path / "models"
    spec = local_spec(tmp_path)
    short = ModelFile(spec.files[1].name, spec.files[1].sha256, spec.files[1].size + 5)
    files = list(spec.files)
    files[1] = short
    bad_spec = ModelSpec(**{**spec.__dict__, "files": tuple(files)})
    monkeypatch.setitem(MANIFEST, bad_spec.id, bad_spec)
    with pytest.raises(AcquisitionError, match="size mismatch"):
        download_model(bad_spec.id, models, local_fetcher(tiny_fixture))
    assert not models.exists() or not any(
        p for p in models.iterdir() if p.name.startswith(".stage-")
    )


def test_unexpected_content_rejected(tmp_path: Path, tiny_fixture: Path, monkeypatch) -> None:
    models = tmp_path / "models"
    spec = local_spec(tmp_path)

    def sneaky_fetch(url: str, destination: Path, expected_size: int) -> None:
        local_fetcher(tiny_fixture)(url, destination, expected_size)
        if destination.name == "tokenizer.json":
            (destination.parent / "extra.py").write_text("malicious")

    monkeypatch.setitem(MANIFEST, spec.id, spec)
    with pytest.raises(AcquisitionError, match="unexpected staged content"):
        download_model(spec.id, models, sneaky_fetch)
    assert not models.exists() or not any(models.iterdir())


def test_symlinked_stage_entry_rejected(tmp_path: Path, tiny_fixture: Path, monkeypatch) -> None:
    models = tmp_path / "models"
    spec = local_spec(tmp_path)

    def link_fetch(url: str, destination: Path, expected_size: int) -> None:
        if destination.name == "openvino_encoder_model.bin":
            try:
                os.symlink(tiny_fixture / destination.name, destination)
            except OSError as error:
                if os.name == "nt" and error.winerror == 1314:
                    pytest.skip("Windows symlink privilege is unavailable")
                raise
        else:
            local_fetcher(tiny_fixture)(url, destination, expected_size)

    monkeypatch.setitem(MANIFEST, spec.id, spec)
    with pytest.raises(AcquisitionError, match="not a plain file"):
        download_model(spec.id, models, link_fetch)
    assert not models.exists() or not any(models.iterdir())


def test_installed_corruption_detected(tmp_path: Path, tiny_fixture: Path, monkeypatch) -> None:
    models = tmp_path / "models"
    spec = local_spec(tmp_path)
    monkeypatch.setitem(MANIFEST, spec.id, spec)
    result = download_model(spec.id, models, local_fetcher(tiny_fixture))
    (result / "tokenizer.json").write_text("{}\n tampered with different length")
    with pytest.raises(AcquisitionError, match="unexpected size|integrity check"):
        verify_installed(models, spec)


def test_url_construction_is_manifest_only(tmp_path: Path, tiny_fixture: Path) -> None:
    spec = local_spec(tmp_path)
    url = spec.url_for("tokenizer.json")
    assert url.startswith("https://huggingface.co/")
    assert spec.revision in url
    hostile = ModelSpec(**{**spec.__dict__, "repo": "../escape"})
    with pytest.raises(AcquisitionError):
        hostile.url_for("tokenizer.json")


def test_no_runtime_network_for_transcription(
    tmp_path: Path, three_second_wav: Path, monkeypatch
) -> None:
    """After acquisition, ordinary transcription must never open a socket."""
    from audio_transcriber.engines import MockSpeechEngine
    from audio_transcriber.pipeline import BatchOptions, BatchRunner
    from audio_transcriber.storage import SessionStore

    class Denied(socket.socket):
        def __init__(self, *a, **k):
            raise AssertionError("transcription attempted network access")

    monkeypatch.setattr(socket, "socket", Denied)
    store = SessionStore(tmp_path / "data")
    options = BatchOptions(model_id="mock", requested_device="auto")
    runner = BatchRunner(store, lambda device: MockSpeechEngine(), [], options)
    session = runner.run_new(three_second_wav)
    assert session.status == "ready"


def test_large_model_range_download_checks_server_range_and_contents(tmp_path, monkeypatch):
    import io

    import audio_transcriber.acquisition as acquisition

    payload = b"verified model bytes"

    class Response(io.BytesIO):
        status = 206
        headers = {"Content-Range": f"bytes 0-{len(payload) - 1}/{len(payload)}"}

    def open_request(request, timeout):
        assert request.get_header("Range") == f"bytes=0-{len(payload) - 1}"
        return Response(payload)

    monkeypatch.setattr(acquisition.urllib.request, "urlopen", open_request)
    destination = tmp_path / "model.bin"
    acquisition._fetch_ranges("https://huggingface.co/model", destination, len(payload))
    assert destination.read_bytes() == payload
    Response.headers = {"Content-Range": "bytes 1-10/99"}
    with pytest.raises(AcquisitionError, match="unexpected byte range"):
        acquisition._fetch_ranges("https://huggingface.co/model", destination, len(payload))
