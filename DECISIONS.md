# Architecture decisions

For measured model/device/chunking choices, see the compact
[tests and decisions](docs/TESTED_DECISIONS.md) record.

## ADR-001: Python/PySide desktop with platform adapters

Status: accepted provisionally on 2026-08-21; one-host Windows CLI/device smoke
completed 2026-09-30. Source desktop, installed-wheel and earlier frozen/installer
checks followed on one Windows host. Current AI-cleanup packaging and broader
compatibility remain unverified; see [implementation status](REQUIREMENTS.md).

### Decision

Use one Python 3.11 application packaged for Windows. Keep transcription, cleanup,
storage, metrics, and orchestration UI-independent. Use PySide6 for the lecture
window, tray, recording, and playback; OpenVINO GenAI for Whisper and local rewrite
inference; and narrow `ctypes` Win32 adapters for `RegisterHotKey`, focus identity,
UI Automation safety checks, transactional clipboard/paste, and `SendInput`.
The tray, recording, hotkeys and native insertion are planned adapters; the
current desktop implements imported-file review and playback.

The runtime must explicitly request a device, reject unavailable manual selections,
and record requested and actual devices. NPU claims require a successful owner-run
OpenVINO workload, not hardware enumeration.

### Compared alternatives

| Stack | Strengths | Costs and risks | Result |
|---|---|---|---|
| Python + PySide6 | Direct official OpenVINO GenAI API; one language; Qt tray/multimedia; Linux-testable core | Larger bundle; global shortcuts and safe insertion need Win32 adapters; Current AI-cleanup packaging still unverified | Chosen |
| C#/.NET host + Python inference service | Strong Windows UI Automation, notifications, packaging | IPC, two runtimes, service lifecycle, duplicated schemas, harder owner maintenance | Rejected for v1 |
| C++/Qt + OpenVINO GenAI | Native runtime and compact integration | Highest implementation complexity; slower iteration; harder educational ownership | Rejected |
| Tauri/Rust host + service | Small modern UI host | Still needs inference sidecar and Windows automation work; webview adds focus complexity | Rejected |

### Packaging

Build a PyInstaller onedir application on Windows and install it per-user with Inno
Setup. Onedir keeps OpenVINO/Qt binaries inspectable and avoids one-file extraction
latency. Installer execution, Start menu, startup, tray, upgrade, and uninstall are
host-only checks.

### Model policy

Manifest-approved OpenVINO IR exports only (no pickle, no remote code, no repo
scripts). `whisper-tiny.en-int4-ov` is the development/proof model;
`whisper-base.en-int4-ov` is the accuracy candidate compared in the
[Windows speech studies](MODEL_EVALUATION.md). Optional Qwen2.5 7B cleanup is
implemented and has targeted quality/speed checks, but broad meaning preservation
is unverified. Balanced remains deterministic.
No final default model is declared until representative WER/RTF results exist.

## ADR-002: Ordinary immutable transcript layers

Each session directory owns a preserved source copy and atomic JSON metadata.
Raw and balanced timestamped JSON files are create-once. Edited text and generated
derivatives are separate files. A schema version is mandatory. Interrupted
`recording` or `processing` sessions become `interrupted` on recovery; source,
raw audio, and raw transcripts are never replaced. Finalized sessions refuse
resume — a new session is the documented retry path.

## ADR-003: Media-decoder boundary and explicit acquisition (added 2026-08-25)

### Decision

All decoding flows through `media.py`. PCM WAV is handled directly; every other
container requires a selected or PATH-discovered FFmpeg binary invoked with a fixed
argument array, never a shell. Model downloads flow through `acquisition.py`:
manifest-only models and hosts, staged temp download, per-file SHA-256 and size
verification, rejection of symlinks/unexpected/path-escaping content, atomic
rename promotion, quarantine-by-cleanup of incomplete stages. Ordinary
transcription never performs network I/O (enforced by test).

### Consequences

- FFmpeg is not bundled yet; until packaging pins and license-reviews a build,
  non-WAV imports require an external FFmpeg executable. An explicit `--ffmpeg`
  selection overrides PATH discovery. No bundled-FFmpeg
  claim is made.
- Adding a model candidate requires recording authoritative source, revision,
  checksums, sizes, license, required files, runtime compatibility, and
  remote-code status in the manifest first.

## ADR-004: Default chunk overlap (local, 2026-10-01)

Use 30-second chunks with zero overlap by default. Keep positive overlap as an
explicit transcription/evaluation option. The initial Yale comparison and a
held-out comparison on three new lecturers favored zero on all 12 matched
model/passage results. On the held-out set, WER fell from 12.84% to 8.71% for
tiny and 10.41% to 7.51% for base. Pooled warm CPU timings also favored zero.
Evidence: [held-out comparison](host-validation/evidence/2026-10-01/overlap-holdout/README.md).

Fixed cuts can omit words: the held-out text alignment found eight single
reference words missing at zero-overlap seams that positive-overlap output
retained. Positive overlap also introduced many partial repetitions that the
whole-segment merger did not remove. This default reflects the measured
overall tradeoff on six Yale passages, not completed boundary handling or an
audio-audited accuracy guarantee. Historical reports preserve their original
chunk settings.

## ADR-005: Experimental pause-based cuts (local, 2026-10-01)

Expose `pause-v1` as an opt-in zero-overlap chunk strategy. Search near the
maximum-length boundary for a quiet run and cut inside it; preserve every
source frame and store the exact window plan in schema 2 checkpoints before
inference. Resume uses the plan without rerunning pause selection. Continue
reading older fixed schema 1 checkpoints and upgrade them on save.

Keep fixed cuts as the default. The six-passage paired pilot lowers pooled WER
for both models and reduces aligned seam deletions, but three passage/model
comparisons regress and seven new seam-deleted reference words appear compared
with fixed output. Quiet-energy cuts do not prove speech-safe boundaries.
The references are published text without independent audio checking.
Evidence: [pause pilot](host-validation/evidence/2026-10-01/pause-pilot/README.md).

## ADR-006: Do not adopt stricter pause cuts as default (local, 2026-10-02)

Keep pause-v2 opt-in. It requires deeper/longer quiet intervals and cuts near
their beginning, but the new three-lecture comparison worsens base WER on
every passage relative to v1 and raises its seam-deleted word count from 3 to
13. Tiny has a small pooled improvement over v1 but still regresses on game
theory relative to fixed cuts. Development fixes two earlier regressions and
worsens the third. The results do not establish universal boundary safety.
Do not change the fixed zero-overlap default. Preserve v1 behavior and saved
plans when adding v2; use exact stored plans for resumed sessions.
Evidence: [pause refinement](host-validation/evidence/2026-10-02/pause-refinement/README.md).

## Remaining product risks

- Explicit NPU/GPU pipeline construction and generation succeeded on one host;
  broader driver compatibility and independent internal hardware attribution
  remain unverified.
- Earlier Windows bundle/installer checks predate AI cleanup. Rebuild and validate
  the current executable/installer before binary release; complete redistribution
  notices remain open.
- Live dictation shortcuts and Win32 insertion are proposed adapters, not current
  desktop functionality; hold semantics and application safety need host tests.
- Desktop applications expose different edit controls. The tested insertion contract
  guards focus identity, password/elevation boundaries and clipboard restoration;
  native clipboard/paste adapters and insertion history are not implemented.
- The two-second dictation target may require streaming, a smaller Whisper model, and no
  semantic model in Balanced mode; only measurements can choose this.
