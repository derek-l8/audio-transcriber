# Iteration report

Milestone 1's vertical slice is complete and verified in the sandbox: explicit
vetted model download → import with preserved source copy → safe decode →
bounded chunked transcription → atomic checkpoints and explicit resume →
immutable raw transcript → deterministic Balanced transcript → timestamped
exports in four formats → measured accuracy/speed/device/failure reporting.

## Retained from Milestone 0

`SessionStore` (extended, not replaced), immutable transcript layers,
`SpeechEngine` protocol, `OpenVINOWhisperEngine`, deterministic cleanup and
spoken-formatting rules, device policy (`choose_device`), metrics, exports
formats, insertion/OneDrive contracts, packaging definitions.

## Intentional pre-release replacements

- `cli.py`: the old positional-argument single-command CLI is replaced by the
  documented subcommand interface required by Milestone 1.
- Transcript layer name `cleaned` → `balanced` to match product vocabulary;
  storage enforces the same create-once immutability.
- `pipeline.run_lecture` retained only as a compatibility wrapper; new work goes
  through `BatchRunner`.

## Corrected stale claims

- `.agent/STATUS.md` now states plainly that the Milestone 1 changes are
  uncommitted on `feature/batch-transcription-core`; the working tree is not
  clean and must not be described as such until the owner commits.
- `.agent/TEST_RESULTS.md` separates deterministic default-suite results from
  opt-in live tests; earlier "75 passed" style summaries that mixed both are
  superseded.
- The Windows harness no longer claims capabilities it lacks: timeouts are
  enforced, devices come from real OpenVINO enumeration, actual-device
  provenance is parsed from CLI output, interruption/resume is automated, peak
  memory is sampled, and WER/CER appear only when measured evaluation data
  exists. Static contract tests pin these properties; actual Windows execution
  remains pending.

## Public-release blockers

No trusted-baseline review by owner yet (single setup commit), no owner-run
Windows results, FFmpeg not bundled/pinned, installer unverified, model
evaluation manifests not yet supplied with public lecture material.

## Security posture

Manifest-only models/hosts, staged checksum verification, no pickle/no remote
code, socket-denial test for transcription path, sanitized reports, atomic
writes everywhere, validated identifiers. Open items for owner review:
final FFmpeg build license/pin, redistribution status of each selected model
(Apache-2.0 recorded but owner should confirm), evaluation dataset licenses.
