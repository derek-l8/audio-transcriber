# Implementation status

Updated: 2026-08-26 UTC

Current milestone: Milestone 1 (CLI batch transcription vertical slice)
implemented and committed as `ac0394b` ("Complete batch transcription core")
on branch `feature/batch-transcription-core`. The working tree must not be
described as clean unless `git status` genuinely shows it clean at check time.
`.git` was never modified by agent passes.

## What exists now

- Full CLI: `models list|download`, `devices`, `transcribe`, `resume`,
  `export`, `evaluate` — with stable machine-readable session output
  (`actual_device:`, `requested_device:`, `chunks_completed:`,
  `fallback_events:`, `inference_seconds:`).
- Secure model acquisition with a bundled manifest of two verified-checksum
  models (tiny.en proof, base.en candidate); real download verified earlier in
  the sandbox and re-runnable only behind the opt-in `live` test marker
  (`NPU_SCRIBE_RUN_LIVE=1 pytest -m live`).
- Media-decoder boundary; direct PCM WAV plus FFmpeg adapter (stub-tested;
  FFmpeg not bundled).
- Bounded chunking, absolute timestamps parsed from the pinned OpenVINO GenAI
  result structure, overlap dedup, atomic checkpoints, explicit resume with
  mismatch refusal, immutable raw + deterministic Balanced layers, four export
  formats, manifest-driven evaluation harness, measured device benchmarks with
  fallback provenance.

## Evidence quality labels used everywhere

- **verified-sandbox**: executed here (Linux CPU container) with recorded results.
- **implemented-unverified**: implemented and unit/static-tested with mocks or
  stubs; needs a real Windows run for evidence.
- **pending**: designed or planned only.

## Sandbox environment notes

- Python 3.11.2. `/tmp` is mounted noexec, so executable test stubs live in
  gitignored `tests/.stubs/`. System package installation remains impossible
  (read-only apt lists). A local virtualenv at `.venv/` (gitignored) hosts dev
  dependencies plus OpenVINO 2026.3.0 / openvino-genai 2026.3.0.0.
- huggingface.co was reachable from this sandbox during earlier passes; the
  default suite never uses that network path.

## Host-only pending

All NPU/GPU evidence, Windows packaging/installer, microphone/UI, insertion,
one-hour endurance, representative accuracy — and execution of the rewritten
PowerShell harness itself (static-tested only).

## Next action

Owner runs `host-validation\Invoke-NpuScribeValidation.ps1 -SetupEnvironment -DownloadModels`,
supplies one public evaluation lecture via a manifest, and returns the two
sanitized reports. Then compare tiny/base candidates per the selection policy
and only then consider a default-model statement.
