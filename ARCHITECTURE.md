# Architecture

The design is a single packaged Python application with UI-independent core
services and replaceable platform adapters. `DECISIONS.md` contains the recorded
decisions and alternatives.

## Core layers (all UI-independent, Linux-testable)

- `acquisition.py` — manifest-approved model downloads: HTTPS host allowlist,
  staged temp directory, per-file SHA-256 + size verification, symlink/path-escape
  rejection, atomic rename promotion. Ordinary transcription never imports it.
- `media.py` — the media-decoder boundary. Direct PCM WAV inspection plus an
  FFmpeg adapter that validates inputs (type, regular file, size, extension),
  passes a fixed argument array with no shell, decodes in a private temp dir,
  bounds captured diagnostics, and always cleans up. Produces normalized mono
  16 kHz PCM.
- `chunking.py` — bounded-memory chunk planning and reads (never loads a full
  recording), absolute timestamp conversion, strict segment validation
  (monotonic, within window), overlap merging that drops only temporal-overlap
  duplicates and preserves legitimate repetition elsewhere.
- `checkpoint.py` — versioned durable checkpoint schema; `save/load/validate_resume`
  refuse any mismatch of session id, source fingerprint, model identity/integrity,
  decoder identity, or chunking settings.
- `storage.py` — `SessionStore`: atomic write-then-rename everywhere, validated
  identifiers, imported source copies with fingerprints, immutable raw/balanced
  transcript files, exports directories, recovery marking.
- `engines.py` — `SpeechEngine` protocol, deterministic `MockSpeechEngine`, and
  lazy `OpenVINOWhisperEngine`. The engine parses the pinned OpenVINO GenAI
  result structure (`WhisperDecodedResults.chunks` with `start_ts`/`end_ts`
  seconds — verified by introspecting the installed 2026.3.0.0 package and a
  live CPU run) and forces English output for multilingual checkpoints via
  explicit `language="en"`, `task="transcribe"` (English-only checkpoints
  reject these arguments).
- `devices.py` — measured benchmarking with separate warmup and runs, median,
  failure categorization, cache keyed on model/runtime/device identity +
  benchmark version, selection policy, fallback order.
- `pipeline.py` — batch orchestration: import copy → decode → chunked
  transcription → checkpoint after each chunk → device fallback with recorded
  provenance → raw transcript first, then Balanced cleanup → finalize (removes
  checkpoint and work files). `resume()` continues only from validated state.
- `cleanup.py` / `dictionary.py` / `export.py` / `evaluate.py` / `metrics.py` /
  `cli.py` — deterministic Balanced cleanup, explicit-only dictionary rules,
  four export formats, manifest-driven evaluation, metrics, CLI.

## Planned outer adapters

PySide6 multimedia/UI, Win32 global shortcut/focus/insertion, bundled+licensed
FFmpeg binary, and PyInstaller/Inno Setup packaging must depend inward on these
core interfaces. No core operation may access the network.

Process isolation was considered but rejected for v1: long inference runs behind
the same engine interface so a future UI thread stays responsive without IPC.

## Data directory layout (platform-appropriate app data, never the repo)

```
<data>/lectures/<session-id>/
    session.json            mutable status/diagnostics
    source/original.<ext>   preserved private copy of the import
    source/source.json      size + sha-256 fingerprint
    checkpoint.json         atomic per-chunk progress (removed on finalize)
    raw-transcript.json     create-once immutable
    balanced-transcript.json create-once immutable
    exports/                generated, never silently overwritten
<data>/models/<model-id>/   checksum-verified installs
<data>/device-benchmarks.json
<data>/evaluation/          evaluation media and reports
```

Default location comes from `platformdirs`; override with `--data-dir` or
`NPUSCRIBE_DATA_DIR`.
