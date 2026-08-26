# PRD compliance matrix

Source: `docs/NPU-SCRIBE-PRD.md` v1.1. Status values are **verified-sandbox**,
**implemented-unverified** (implemented here, awaiting Windows validation),
**partial**, **pending**, and **out-of-scope**.

| Requirement group | Implementation/evidence | Status |
|---|---|---|
| Local English speech, CPU/GPU/NPU provenance | `engines.py`, `devices.py`; real CPU inference with pinned tiny.en model verified in sandbox | partial (CPU verified-sandbox; GPU/NPU pending) |
| Explicit actual-device verification and measured policy | `devices.run_benchmark`, `choose_device`, `device_order`; per-chunk `device_used` records; Windows run required for NPU/GPU evidence | partial |
| Model acquisition separate from transcription | `acquisition.py`: manifest-only models, HTTPS host allowlist, staged SHA-256 verification, atomic promote, no pickle, no remote code; real download of pinned tiny.en verified in sandbox | verified-sandbox |
| First run, OneDrive warning | planned desktop/setup service | pending |
| Immutable raw/Balanced layers | `storage.py`, `pipeline.py`; raw + balanced create-once files | verified-sandbox |
| Audio normalization, decoding boundary | `media.py`: WAV direct, MP3/M4A/MP4 via configured FFmpeg adapter (array argv, no shell, staged temp, cleanup); FFmpeg itself not bundled yet | partial (adapter verified-sandbox via stubs; bundled FFmpeg pending) |
| Chunking, overlap, checkpoints, resume | `chunking.py`, `checkpoint.py`, pipeline: bounded chunks, absolute timestamps from real runtime result structure (`WhisperDecodedResults.chunks`), atomic checkpoints, mismatch refusal, uninterrupted-vs-resumed equivalence with the real pinned model | verified-sandbox |
| JSON v1, Markdown, text, SRT exports | `export.py`: all four formats, both layers, SRT validation, no-overwrite, atomic writes | verified-sandbox |
| WER/CER/RTF/load/latency/memory evaluation | `evaluate.py` + CLI `evaluate`: manifest-driven, checksum-verified media fetch, selection policy (reject RTF>=1.0, prefer <=0.5, lowest WER); real representative results pending owner machine | implemented-unverified |
| Raw/Balanced/Aggressive and safety | `cleanup.py` Balanced is deterministic, preserves "like", numbers, units, spoken math, uncertainty; aggressive mode gated by number/negation guard | verified-sandbox |
| Personal dictionary substitution | `dictionary.py`; only explicit rules replace terms | verified-sandbox (UI pending) |
| Lecture record/import/live/final/recovery/endurance | batch import/resume/recovery done; microphone/live recording out of scope this milestone; endurance test authored in host-validation script, awaiting owner run | partial |
| Player/search/timestamps/uncertainty/outline/summary/storage/delete | timestamps + uncertainty flags exported; player/outline/summary pending desktop UI | partial |
| Tray, hold/toggle shortcuts, cues, states, preview/history | pending Windows adapters/UI | pending |
| Word/Notion/Codex guarded insertion and clipboard restoration | `insertion.py` contract tested; host validation pending | partial |
| Offline operation/no telemetry/update/network | socket-denial test proves no network during transcription; network only in explicit `models download` / `evaluate` | verified-sandbox |
| Redacted diagnostics and support bundle | path sanitization in reports; full support bundle pending | partial |
| Per-user installer/startup/uninstall/data choice | planned PyInstaller/Inno Setup; packaging definitions exist unverified | pending |
| One-command Windows validation and sanitized reports | `host-validation/Invoke-NpuScribeValidation.ps1` rewritten for Milestone 1 flow; awaiting owner run | implemented-unverified |
| Two-hour bounded-memory test | design bounded per-chunk reads verified on 95 s multi-chunk source; 2-hour endurance pending owner run | pending |
| Required documentation/licenses/notices | MIT code; model manifests record Apache-2.0 license + revision; FFmpeg/installer license review open | partial |
| System audio, diarization, DOCX, surrounding text, selection rewrite | intentionally absent | out-of-scope |

No Windows, NPU, GPU, microphone, insertion, installer, endurance, or
accuracy-threshold claim is verified yet.
