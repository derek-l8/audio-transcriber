# Test results

Updated: 2026-08-26 UTC (pytest 9.0.3 re-verification).

Results are always reported separately: deterministic default suite first, then
opt-in live tests. They are never merged into one ambiguous count.

## Default network-free suite (verified-sandbox)

Environment: Linux container, Python 3.11.2, venv with pytest 9.0.3 /
pytest-cov 6.0.0 / ruff 0.9.10 / mypy 1.15.0 / openvino 2026.3.0 /
openvino-genai 2026.3.0.0.

- Re-verified 2026-08-26 after the pytest 8.3.5 → 9.0.3 security bump
  (Dependabot: vulnerable tmpdir handling): `pytest -m "not live"` — 96 passed,
  1 deselected; `--cov` run also green (85% total).

- `pytest -m "not live"` with sockets monkeypatched to raise
  (`socket.socket` denied) and the acquisition fetcher patched out:
  see exact counts in the final validation section of this pass; any failure
  here would be a regression of test isolation.
- The real-download test is skipped by default (marker `live`, gated on
  `NPU_SCRIBE_RUN_LIVE=1`); no collection-time reachability probe exists.
- `ruff format --check .` / `ruff check .`: clean.
- `mypy src` strict: clean.
- Byte compilation: clean.

## Opt-in live tests

`NPU_SCRIBE_RUN_LIVE=1 pytest -m live` performs the real pinned-model download.
Earlier passes executed this successfully end-to-end from this sandbox; it is
not re-run automatically and must be labelled separately whenever executed.
The installed model copy can be verified offline via
`npu-scribe models download whisper-tiny.en-int4-ov` against an existing install
(verification-only, no redownload).

## Sandbox CPU evidence (verified-sandbox, earlier pass, unchanged claims)

- Real CPU transcription of a synthetic 95 s WAV through the chunked pipeline:
  4 chunks, absolute timestamps preserved, RTF ≈ 0.014–0.018 — a speed/loading
  proof on synthetic audio, not accuracy.
- Interruption after chunk 1 → explicit resume produced raw segments identical
  to the uninterrupted run.

## Implemented but unexecuted Windows harness behavior

The rewritten PowerShell harness is covered by static contract tests
(`tests/test_host_validation.py`) pinning: parameter surface, per-user data/venv
locations outside Git, single resolved interpreter, version + import gates,
process-tree timeout enforcement, valid-WAV fixture validated via the
application's media boundary, enumerated-devices-only testing,
requested-vs-actual provenance parsing, automated interruption/resume, sampled
peak memory, and measured-only metrics. PowerShell cannot execute in this
sandbox; every harness output remains unverified until an owner-run report is
returned.

## Owner-run Windows results

None returned yet.
