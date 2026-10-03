# Windows validation — Milestone 1

Open an ordinary (non-Administrator) PowerShell in this directory. The intended
one-command novice experience:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\Invoke-NpuScribeValidation.ps1 -SetupEnvironment -DownloadModels
```

Optional additions:

```powershell
-DataDirectory PATH        # override the per-user validation data location
-FfmpegPath PATH           # required for MP3/M4A/MP4 inputs (not bundled yet)
-EvaluationManifest PATH   # measured WER/CER/RTF on prepared public material
-LongFile PATH             # automated interruption/resume + endurance run
-IncludeLegacyUiChecks     # append round-1 owner-observed UI prompts
```

What this does, in order:

1. Resolves the repository root from the script location and creates a
   validation data directory under `%LOCALAPPDATA%\npu-scribe\validation-data`
   (never inside the repository). `-DataDirectory` overrides it.
2. With `-SetupEnvironment` (the only network-dependent setup step): creates a
   dedicated per-user virtual environment at
   `%LOCALAPPDATA%\npu-scribe\validation-venv` — outside Git — and installs this
   project plus the pinned inference dependencies (`openvino==2026.3.0`,
   `openvino-genai==2026.3.0.0`).
3. Checks the Python version (3.11/3.12) and that `npu_scribe`, `openvino`, and
   `openvino_genai` import; without them it fails with exact recovery
   instructions instead of a cascade of misleading errors.
4. Enumerates real OpenVINO devices and tests **only those**. A missing GPU/NPU
   is recorded as `unavailable`, never as a failed inference attempt.
5. With `-DownloadModels`: downloads manifest-approved models only when asked.
6. Generates a valid mono 16 kHz 16-bit PCM WAV fixture (RIFF/WAVE header,
   validated through the application's own `inspect_pcm_wav` boundary) and runs
   a per-device smoke transcription. This proves runtime/device execution only —
   it is never described as an accuracy test. Actual-device provenance is parsed
   from the CLI's stable output; NPU success is claimed only if provenance says
   the session actually ran on NPU.
7. With `-LongFile`: performs a fully automated interruption/resume exercise —
   starts transcription, waits (bounded) for a durable checkpoint of a new
   session, terminates the process tree, verifies the checkpoint survived, then
   automatically runs `resume SESSION_ID` with identical settings and verifies
   the session reaches `ready` with unique, ordered chunk records. Afterwards it
   runs one continuous pass over the same file for endurance, sampling peak
   process-tree working-set memory every 10 seconds, with a 6-hour enforced
   timeout. Samples can miss shorter memory spikes.
8. With `-EvaluationManifest`: measures WER/CER/RTF on prepared public material;
   WER/CER appear in the report only from that measured evaluation file.
9. Writes sanitized Markdown + JSON reports (`schema_version 3`) recording exact
   Python/package/OpenVINO versions, requested vs actual devices, timings,
   chunk counts, fallback events, sampled memory, and resume results.

Every long-running step enforces its timeout by killing the child process tree;
timeouts are reported distinctly from failures.

The script never records transcript content, audio, clipboard contents,
username, credentials, or private absolute paths. Review both reports before
returning them; `skip` and `unverified` never count as passes.

Preparing an evaluation manifest: point `audio_url` at the official public
source and record its SHA-256, exact size, license, and reference-transcript
provenance. See `MODEL_EVALUATION.md`. Do not bundle copyrighted media here.

Status: executed on one Windows host on 2026-09-30. Sanitized JSON reports are
in `evidence/2026-09-30/`. CPU/GPU/NPU smoke checks used synthetic silence;
the one-hour endurance and resume checks used synthetic CPU audio. These do
not measure speech accuracy, NPU speedup, broad compatibility, or two-hour
memory growth. A repeat run can use a checksum-verified installed tiny model
without `-DownloadModels`.

For a separate continuous two-hour CPU run with a process-tree memory series,
use PowerShell 7:

```powershell
pwsh -File .\Measure-NpuScribeEndurance.ps1 -LongFile PATH
```

The [one-host result](evidence/2026-09-30/two-hour-endurance/README.md) includes
two successful synthetic runs, recoverability checks, and sampling limits.

For three-way pause refinement comparisons, use `Measure-OverlapPilot.py`
with `--strategies fixed pause-v1 pause-v2`. Prepare new pinned Yale sources
with `Prepare-YaleContinuousPilot.py --source-set refinement`. The same analyzer
groups reports by strategy and overlap. Keep all text-bearing files ignored.
See [the new-lecture refinement result](evidence/2026-10-02/pause-refinement/README.md).

For the original two-way overlap comparison, use
`Prepare-YaleContinuousPilot.py --source-set holdout` with the pinned source
MP3s/HTML and an explicit FFmpeg executable, then `Measure-OverlapPilot.py`.
The latter verifies the installed tiny/base model files, warms each CPU
pipeline, and runs 0,1 then 1,0 pairs through `BatchRunner`. Its completed-run
index allows a rerun to skip finished measurements. `Analyze-OverlapPilot.py`
checks edit counts and missing reference text across chunk seams. Keep the
supplied data root and text-review output in ignored local storage; they
contain recordings and transcript text. Only the numeric reports belong in
the evidence directory. See [the held-out result and reproduction details](evidence/2026-10-01/overlap-holdout/README.md).

The same measurement helper accepts `--comparison pause` to compare fixed
zero-overlap cuts with the experimental pause-v1 strategy. Both conditions
use the same WAV and reference; alternate repeats reverse their order. Run
`Analyze-OverlapPilot.py` against the completed index to inspect seam deletions.
Use a fresh data/output root for each algorithm or manifest change. The pause
comparison uses all six previously prepared Yale passages, rather than new
held-out material. See [the pause pilot](evidence/2026-10-01/pause-pilot/README.md).

## Installation and frozen worker checks

See [the package validation result](evidence/2026-10-02/package-validation/README.md) for fresh installation and one-host bundle evidence. `Test-DesktopWorkflow.py --worker-executable PATH` drives an existing frozen CLI worker from the source Qt UI; it does not automate the frozen window. The [packaging guide](../packaging/README.md) gives the complete commands and remaining gates. `Test-FrozenWindow.py` checks native idle close/reopen; `Test-WindowsInstaller.py` uses a separate test identity for install/reinstall/uninstall and library preservation. Keep all checkouts and generated files outside synced folders.


`Test-FrozenReview.py` checks the actual frozen Windows GUI through owned
accessibility controls and targeted Windows messages using a fresh silent/mock
library. Dropdowns, playback, seeking, editing, search, latest/older history
previews, twelve exports, normal close/reopen and immutable artifact checks passed in the [native review result](evidence/2026-10-02/frozen-review/README.md).
`Test-FrozenJobClose.py` also passed native import, close during a real CPU job,
reopen/resume and committed-text/audio preservation using repeated public speech.
See the packaging guide for commands; use fresh ignored work directories.

## AI cleanup quality and speed

See the [matched cleanup result](evidence/2026-10-02/ai-cleanup-comparison/README.md)
for CPU/GPU/NPU text-model quality, warmed latency, startup, and CPU-time evidence.
`Compare-AiCleanup.py` runs identical cases sequentially with reversed device/case
order on the second pass. The evidence guide gives synthetic-only reproduction
commands and distinguishes strict check failures from semantic errors.
