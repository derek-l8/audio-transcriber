# Architecture decisions

## ADR-001: Python/PySide desktop with platform adapters

Status: accepted provisionally on 2026-08-21; Windows validation pending.

### Decision

Use one Python 3.11 application packaged for Windows. Keep transcription, cleanup,
storage, metrics, and orchestration UI-independent. Use PySide6 for the lecture
window, tray, recording, and playback; OpenVINO GenAI for Whisper and local rewrite
inference; and narrow `ctypes` Win32 adapters for `RegisterHotKey`, focus identity,
UI Automation safety checks, transactional clipboard/paste, and `SendInput`.

The runtime must explicitly request a device, reject unavailable manual selections,
and record requested and actual devices. NPU claims require a successful owner-run
OpenVINO workload, not hardware enumeration.

### Compared alternatives

| Stack | Strengths | Costs and risks | Result |
|---|---|---|---|
| Python + PySide6 | Direct official OpenVINO GenAI API; one language; Qt tray/multimedia; Linux-testable core | Larger bundle; global shortcuts and safe insertion need Win32 adapters; Windows packaging still unverified | Chosen |
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
`whisper-base.en-int4-ov` is the first accuracy candidate awaiting Windows
evaluation. A semantic rewriter remains optional until a small OpenVINO-compatible
model passes meaning-preservation and latency evaluation; Balanced is deterministic-first.
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
container requires an explicitly configured FFmpeg binary invoked with a fixed
argument array, never a shell. Model downloads flow through `acquisition.py`:
manifest-only models and hosts, staged temp download, per-file SHA-256 and size
verification, rejection of symlinks/unexpected/path-escaping content, atomic
rename promotion, quarantine-by-cleanup of incomplete stages. Ordinary
transcription never performs network I/O (enforced by test).

### Consequences

- FFmpeg is not bundled yet; until packaging pins and license-reviews a build,
  non-WAV imports require the owner to configure `--ffmpeg`. No bundled-FFmpeg
  claim is made.
- Adding a model candidate requires recording authoritative source, revision,
  checksums, sizes, license, required files, runtime compatibility, and
  remote-code status in the manifest first.

## Risks

- Actual OpenVINO NPU/GPU compilation/execution and driver compatibility are unverified.
- PyInstaller collection of OpenVINO/Qt and installer behavior require Windows builds.
- Qt shortcuts are not system-global; the Win32 adapter and hold semantics need host tests.
- Word, Notion, and Codex expose different edit controls. Clipboard/paste is the common
  fallback, guarded by focus identity, password/elevation checks, restoration, and history.
- The two-second dictation target may require streaming, a smaller Whisper model, and no
  semantic model in Balanced mode; only measurements can choose this.
