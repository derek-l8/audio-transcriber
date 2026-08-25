# Owner Windows validation — Milestone 1

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
   working-set memory, with a 6-hour enforced timeout.
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

Status: the harness itself is static-tested for structure but has **not** been
executed on Windows yet; treat all its outputs as unverified until an owner-run
report exists.
