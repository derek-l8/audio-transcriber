# Test results

Updated 2026-08-21 UTC.

## Passed in current sandbox

- Repository and PRD inspection.
- Ruff formatting/lint gate after fixes.
- 10 unit/integration tests passed in 0.21 s; 80% statement coverage.
- Strict mypy (14 source files), Ruff format/lint, and byte compilation passed.
- OpenVINO 2026.3.0 CPU loaded and executed pinned Whisper tiny.en INT4 on synthetic WAV.
  Load 0.611 s, inference 0.334 s, one un-warmed run; this is not a latency/accuracy claim.

## Failed in current sandbox

- System package installation: container root package lists are read-only.
- First English-only Whisper invocation rejected explicit `language` and `task`; adapter
  fixed and proof rerun successfully.

## Skipped due to environment

- FFmpeg media decoding, PowerShell, Windows UI, NPU/GPU, microphone, installer.

## Owner-run Windows results

None returned.

## Still unverified

Offline socket denial, endurance, representative model evaluation, and
every host acceptance item.
