# PRD compliance matrix

Source: `docs/NPU-SCRIBE-PRD.md` v1.1. Status values are **verified-sandbox**,
**implemented-unverified**, **partial**, **pending**, and **out-of-scope**.

| Requirement group | Implementation/evidence | Status |
|---|---|---|
| Local English speech, CPU/GPU/NPU provenance | `engines.py`, `devices.py`; mock tests | partial |
| Explicit actual-device verification and measured policy | `devices.choose_device`; Windows run required | partial |
| First run, model acquisition, OneDrive warning | planned desktop/setup service | pending |
| Immutable raw/cleaned/editable layers | `storage.py`, `pipeline.py`, storage tests | verified-sandbox |
| Audio normalization, decoding, chunk/overlap/checkpoints | PCM WAV validation exists; FFmpeg/chunker pending | partial |
| JSON v1, Markdown, text, SRT, clipboard exports | `export.py`; clipboard/UI pending | partial |
| WER/CER/RTF/load/latency/memory evaluation | WER/CER implemented; remaining harness pending | partial |
| Raw/Balanced/Aggressive and safety | `cleanup.py`; semantic adapter/evaluation pending | partial |
| Fillers/repetition/corrections/format commands/literal escape | cleanup golden tests | verified-sandbox |
| Personal dictionary import/export/conflicts/provenance | `dictionary.py`; UI pending | partial |
| Lecture record/import/live/final/recovery/endurance | session orchestration/recovery only | partial |
| Player/search/timestamps/uncertainty/outline/summary/storage/delete | pending desktop UI | pending |
| Tray, hold/toggle shortcuts, cues, states, preview/history | pending Windows adapters/UI | pending |
| Word/Notion/Codex guarded insertion and clipboard restoration | pending adapter and host validation | pending |
| Offline operation/no telemetry/update/network | no runtime network code; test pending | partial |
| Redacted diagnostics and support bundle | pending | pending |
| Per-user installer/startup/uninstall/data choice | planned PyInstaller/Inno Setup | pending |
| One-command Windows validation and sanitized reports | pending | pending |
| Two-hour bounded-memory test | pending | pending |
| Required documentation/licenses/notices | MIT added; documentation in progress | partial |
| System audio, diarization, DOCX, surrounding text, selection rewrite | intentionally absent | out-of-scope |

No Windows, NPU, microphone, insertion, latency, installer, or offline-network claim is
verified yet.
