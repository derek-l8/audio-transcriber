# Testing

## Command reference

| Purpose | Command |
|---|---|
| Default deterministic suite (network-free, model-free) | `pytest -m "not live"` or plain `pytest` |
| Coverage for the default suite | `pytest --cov=npu_scribe --cov-report=term -m "not live"` |
| Opt-in live model acquisition (real network) | `NPU_SCRIBE_RUN_LIVE=1 pytest -m live` |
| Windows validation (owner machine) | see `host-validation/README.md`: `.\Invoke-NpuScribeValidation.ps1 -SetupEnvironment -DownloadModels` |
| Endurance (~60-minute file) | same harness with `-LongFile PATH` |

Quality gate (default suite only):

```bash
pytest
ruff format --check .
ruff check .
mypy src
python -m compileall -q src tests
```

## Test isolation policy

- Plain `pytest` must never perform DNS, socket, HTTP, model-download, or
  dataset-download activity. This is enforced, not hoped for:
  - the real-download test is marked `@pytest.mark.live` and additionally
    requires `NPU_SCRIBE_RUN_LIVE=1`;
  - no test module performs network I/O at import/collection time;
  - regression tests monkeypatch `socket.socket` and the acquisition fetcher to
    prove ordinary CLI commands are network-free;
  - a static contract test scans test sources so collection-time probes cannot
    return unnoticed.
- Deterministic synthetic tests cover manifest safety, checksums, staging,
  atomic promotion, quarantine cleanup, and installed-model tampering without
  any network access.

## Result reporting convention

Default-suite results and live results are always reported separately — never
merged into one ambiguous count. Example honest summary:

> Default network-free suite: N passed, M skipped in T s.
> Opt-in live (`NPU_SCRIBE_RUN_LIVE=1 pytest -m live`): reported separately when run.

## Current layers

- `test_core.py`, `test_storage_pipeline.py`, `test_media.py`,
  `test_chunking.py`, `test_checkpoints.py`, `test_acquisition.py`,
  `test_batch_flow.py`, `test_cli.py`, `test_devices.py`,
  `test_evaluation.py`, `test_exports.py`, `test_reporting.py`.
- `test_host_validation.py` pins the PowerShell harness's structure by static
  inspection (parameters, timeout enforcement, valid-WAV fixture, enumerated
  devices only, automated interruption/resume, measured-only metrics). The
  sandbox cannot execute PowerShell; actual Windows behavior is pending until an
  owner-run report is returned.

## Conventions

- Hardware, FFmpeg, and network are mocked or stubbed deterministically;
  executable stubs live in gitignored `tests/.stubs` because `/tmp` is noexec.
- Host results go in sanitized reports copied to `.agent/TEST_RESULTS.md`;
  a skip is never a pass.
- No cloud model, speech API, or paid API is ever invoked by product tests.
