# Implementation and validation status

The current source v0.1 scope is a local English file-transcription engine,
with an optional Windows desktop interface and experimental AI cleanup.
Import, transcription, review, playback/search, checkpoint/resume, and export
are implemented. This is a source milestone; a current validated installer
release and the original live-dictation product are not complete.

[The PRD](docs/NPU-SCRIBE-PRD.md) is a historical planning document.
Its microphone, tray, insertion, and setup requirements remain future
work. The matrix retains those gaps without making them source v0.1 release gates.

Status values are **verified-sandbox**, **verified-windows-one-host**,
**implemented-unverified**, **partial**, **pending**, and **out-of-scope**.
Verification covers the recorded inputs and exercised paths. See
[remaining validation](TESTING.md#remaining-validation) for open checks.

## Implementation matrix

| Requirement group | Implementation/evidence | Status |
|---|---|---|
| Local English speech, CPU/GPU/NPU device binding | `engines.py`, `devices.py`; tiny.en and base.en completed explicit-device lecture checks and a matched repeat on one Windows host; NPU Whisper refreshes its pipeline per chunk | verified-windows-one-host for runtime binding; representative accuracy pending |
| Device selection and measured policy | Speech starts on CPU; opt-in Auto uses cached synthetic-audio benchmarks and can fall back. Cleanup defaults to AUTO (available GPU, then CPU on failure); explicit choices stay strict, and per-block devices/fallbacks are recorded. Reported device records successful requested-device generation, not an independent hardware query; no resource cap or idle scheduling | partial |
| Model acquisition separate from ordinary processing | `acquisition.py`: pinned manifest, explicit download, HTTPS host allowlist, staged per-file size/SHA-256 checks and atomic promotion. Speech and 7B cleanup models were downloaded and used; weights are not bundled | verified-windows-one-host for exercised downloads |
| First run and cloud-sync warning | Source installation and Git/ZIP update instructions use local storage; no desktop setup wizard or automatic cloud-folder warning | partial |
| Immutable Raw/Balanced layers | `storage.py`, `pipeline.py`; create-once transcript files and retained recording; hashes checked through desktop, editing, cleanup, and export workflows | verified-windows-one-host for exercised workflows |
| Editable user transcript version | Separate Edited layer, retained revisions, fixed source timestamps, stale-writer refusal and exports; source and native frozen review checks. Unsaved edit crash recovery pending | partial |
| Audio normalization and decoding | Direct mono 16 kHz 16-bit PCM WAV; MP3/M4A/MP4 through selected or PATH-discovered FFmpeg. Synthetic decoder cases, real short MP3 and full local MP4 audio streams checked; decoder is external | partial |
| Chunking, overlap, checkpoints, resume | Fixed 30-second zero-overlap default; optional pause-v1/v2 remain experimental. Saved chunk plans and mismatch checks; real resumed/uninterrupted equivalence on short speech, two-hour synthetic CPU endurance and full lecture completion | verified-windows-one-host for exercised paths; chunk-boundary accuracy incomplete |
| JSON, Markdown, text, SRT exports | `export.py`: Raw/Balanced/Edited/AI layers, separate provenance, no-overwrite and atomic writes; source cleanup exports and twelve native frozen Raw/Balanced/Edited exports checked. AI SRT retains coarse source-block timings | verified-windows-one-host for exercised exports |
| Speech WER/CER/RTF/load/latency/memory evaluation | Product-path harness plus MIT, AMI, TED-LIUM, 100 NPTEL clips, continuous Yale overlap/pause studies and an independent three-lecture refinement check. Reference quality varies; Windows per-case memory is null, with separate process-tree samples | partial |
| Independent formatting | Mostly prose without AI; Mixed/Structured source-passage layout plans, complete coverage/order validation, source-backed headings and restricted tables/steps, independent desktop controls, retained versions, CLI chaining/model reuse and document exports. General semantic grouping remains unverified | partial |
| Raw/Balanced/AI cleanup | Conservative Balanced rules; separate pinned local Qwen2.5 7B with lecture/dictation and Off/Light/Medium controls, automatic selected cleanup after desktop import/resume, guarded source fallback, retained complete versions and GUI/CLI exports. Repeated CPU/GPU/NPU quality/speed and contention studies; arbitrary semantic fidelity remains unverified | partial |
| Personal dictionary substitution | `dictionary.py`; only explicit rules replace terms | verified-sandbox; UI pending |
| Lecture import, progress and recovery | Desktop child-process import, progress, pause/resume and library reopening; real short MP3 and full 47-minute MP4 checks. Forced termination of a processing session still needs explicit CLI recovery; microphone/live recording pending | partial |
| Player/search/timestamps/uncertainty/outline/summary/storage/delete | Preserved-audio playback/seek, transcript search, timestamps, uncertainty, manual revisions and exports; source full-lecture and native frozen review checks. Separate formatted excerpt summaries; whole-lecture outline/delete pending | partial |
| Tray, hold/toggle shortcuts, cues, states, preview/history | Live dictation adapters and tray pending; imported-file transcript review and manual revision history exist | partial |
| Desktop insertion and clipboard restoration | `insertion.py` contract tests; native application integration absent | partial |
| Offline operation/no telemetry | Default tests deny sockets during synthetic processing; ordinary transcription and cleanup use local assets. Downloads are explicit acquisition/evaluation actions; no telemetry implementation | verified-sandbox for tested network boundary |
| Redacted diagnostics and support bundle | Path sanitization in public reports; full support bundle pending | partial |
| Per-user installer/startup/uninstall/data choice | Earlier frozen builds passed isolated silent install, same-version reinstall, uninstall and file-preservation checks; startup off by default. Current AI-cleanup bundle not rebuilt/tested; wizard/startup shortcut/version upgrade pending | partial |
| One-command Windows validation and sanitized reports | `Invoke-NpuScribeValidation.ps1` plus focused local helpers; sanitized device, endurance, speech, desktop and cleanup metadata in `host-validation/evidence/` | verified-windows-one-host for exercised paths |
| Two-hour bounded-memory test | Two synthetic CPU passes; denser pass sampled 408.6 MB peak and post-warmup first/last quarter medians 389.2/390.0 MB. Earlier one-hour setup sampled 1211.8 MB; no universal peak ceiling or two-hour real-speech result | verified-windows-one-host for synthetic CPU |
| Portable source/package installation | Source archive and wheel checked for required modules and runtime/private artifacts; clean installed-wheel synthetic smoke, real CPU speech and real CPU cleanup from outside the checkout on one Windows host | verified-windows-one-host for exercised installation paths |
| Required documentation/licenses/notices | MIT source, pinned model license metadata, user/development/testing/privacy guides. Complete native/transitive redistribution inventory remains open for a binary release | partial |
| System audio, diarization, DOCX, surrounding text, selection rewrite | Intentionally absent from the current scope | out-of-scope |

## Evidence and remaining limits

- [Speech evaluation](MODEL_EVALUATION.md) distinguishes caption-relative MIT
  results, human-reference AMI/TED-LIUM/NPTEL pilots, and provisional continuous
  lecture comparisons. Zero overlap improved aggregate results but still loses
  some boundary words. Pause variants remain opt-in after mixed held-out results.
- [Full local lecture playback](host-validation/evidence/2026-10-02/desktop-playback/README.md)
  checks completion and review of a 47-minute recording. Without a reference
  transcript, that run establishes no word-error-rate result.
- [Standalone installation](host-validation/evidence/2026-10-02/portable-engine/README.md)
  checks path independence and real CPU transcription.
- [Cleanup pilot](host-validation/evidence/2026-10-02/ai-cleanup/README.md),
  [matched device comparison](host-validation/evidence/2026-10-02/ai-cleanup-comparison/README.md),
  and [resource comparison](host-validation/evidence/2026-10-02/cleanup-resource-cost/README.md)
  distinguish execution, targeted fidelity checks, warmed request speed, RAM,
  and interference with synthetic graphics. A guard passing does not prove
  semantic preservation; literal commands, quotations, emphasis and math can fail.
- [Historical package/installer checks](host-validation/evidence/2026-10-02/package-validation/README.md)
  and [native frozen review](host-validation/evidence/2026-10-02/frozen-review/README.md)
  apply to recorded earlier builds. They do not validate the current
  cleanup-enabled executable or installer.

Current validation is confined to one Windows host plus earlier sandbox checks.
Independently audio-checked continuous lecture references, broad device/platform
compatibility, two-hour real-speech memory behavior, real application contention,
live microphone capture/insertion, and current installer validation remain open.
