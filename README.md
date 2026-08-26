# NPU Scribe

NPU Scribe is an English-only, local Windows lecture transcription application
designed for a system with an Intel NPU: device selection is measured, actual
device provenance is recorded per run, and CPU/GPU are supported fallbacks —
no specific hardware model is required. It is under active development.
Milestone 1 — a reliable command-line batch-transcription
workflow for imported files — is implemented and verified in the Linux sandbox;
all Windows, NPU, GPU, endurance, and accuracy claims still require owner-run
host validation.

## What works now (verified in the sandbox)

- `npu-scribe` CLI: model management, device listing, batch transcription,
  explicit resume, exports, and manifest-driven evaluation.
- Explicit, checksum-verified download of manifest-approved OpenVINO Whisper
  models from `huggingface.co` only; staged verification with atomic promotion.
- Import of WAV/MP3/M4A/MP4 through a media-decoder boundary; validated mono
  16 kHz PCM WAV flows without FFmpeg, other containers need a configured
  FFmpeg binary (adapter tested with deterministic stubs).
- Bounded-memory chunking (default 30 s chunks, 1 s overlap), absolute source
  timestamps parsed from the pinned OpenVINO GenAI runtime's real result
  structure (`WhisperDecodedResults.chunks`), overlap deduplication that never
  deletes legitimate repeated content outside the overlap window.
- Atomic per-chunk checkpoints and explicit resume that refuses fingerprint,
  model, decoder, or chunking mismatches; resumed runs produce byte-identical
  raw segments to uninterrupted runs (verified with the real pinned model).
- Immutable raw transcript plus deterministic Balanced layer per session.
- Exports: versioned JSON, Markdown, text, SRT (validated) for both layers.
- Measured device benchmarks with warmup/run separation, identity-keyed cache,
  automatic selection, verified-device fallback with recorded provenance.
- No network access during ordinary transcription (socket-denial tested);
  network is used only by explicit `models download` / `evaluate` commands.

## Prerequisites

- Python 3.11 or 3.12 (3.11 is used for development).
- FFmpeg binary on PATH (or passed via `--ffmpeg`) for MP3/M4A/MP4 inputs;
  plain mono 16 kHz WAV needs nothing extra. FFmpeg is not bundled.
- No NPU/GPU required: OpenVINO falls back to CPU automatically; actual device
  provenance is recorded per run.
- Sessions, exports, and models live under the per-user data directory, never
  inside this repository.

## Quick start

```bash
python -m pip install -e '.[inference]'
npu-scribe models list
npu-scribe models download whisper-tiny.en-int4-ov
npu-scribe transcribe lecture.wav --model whisper-tiny.en-int4-ov --device auto
npu-scribe resume SESSION_ID
npu-scribe export SESSION_ID --format srt --layer balanced
```

## Not yet claimed

No NPU acceleration, Windows compatibility, bundled FFmpeg, one-hour endurance,
accuracy threshold, or model superiority claim is verified yet. The desktop UI,
microphone recording, dictation insertion, semantic rewriting, summaries, and
math-symbol conversion are intentionally out of scope for this milestone.

Models are never bundled or fetched during ordinary operation. Do not place
models, recordings, transcripts, or diagnostics inside the repository.

License: original code is MIT. Third-party runtimes, models, media codecs, and
datasets retain their own licenses; see `THIRD_PARTY_NOTICES.md`.
