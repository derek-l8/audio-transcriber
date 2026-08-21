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

Start with `whisper-base` INT8 for measurements, then compare tiny/base/small on the
owner machine. No model ships in Git. Explicit acquisition verifies a manifest and
license. A semantic rewriter remains optional until a small OpenVINO-compatible model
passes meaning-preservation and latency evaluation; Balanced is deterministic-first.

## ADR-002: Ordinary immutable transcript layers

Each lecture directory owns source audio and atomic JSON metadata. Raw and cleaned
timestamped JSON files are create-once. Edited text and generated derivatives are
separate files. A schema version is mandatory. Interrupted `recording` or `processing`
sessions become `interrupted` on recovery; source and raw data are never replaced.

## Risks

- Actual OpenVINO NPU compilation/execution, driver compatibility, and performance are unverified.
- PyInstaller collection of OpenVINO/Qt and installer behavior require Windows builds.
- Qt shortcuts are not system-global; the Win32 adapter and hold semantics need host tests.
- Word, Notion, and Codex expose different edit controls. Clipboard/paste is the common
  fallback, guarded by focus identity, password/elevation checks, restoration, and history.
- The two-second dictation target may require streaming, a smaller Whisper model, and no
  semantic model in Balanced mode; only measurements can choose this.
- The initial repository lacks the PRD-required trusted baseline commit.
