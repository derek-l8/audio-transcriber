# Architecture

The design is a single packaged Python application with UI-independent core
services and replaceable platform adapters. `DECISIONS.md` contains the recorded
decisions and alternatives.

## UI-independent core layers

- `acquisition.py` — manifest-approved model downloads: HTTPS host allowlist,
  staged temp directory, per-file SHA-256 + size verification, symlink/path-escape
  rejection, atomic rename promotion. Ordinary transcription imports manifest
  definitions but does not invoke the downloader.
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
  transcript files, exports directories, recovery marking. `editing.py` keeps
  separate versioned manual edits with source hashes and revision checks.
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

- `ai_cleanup.py` — a separate lazy OpenVINO LLM pipeline with independent
  CPU/GPU/NPU selection and GPU-to-CPU fallback for AUTO. Fresh chat history per bounded source block,
  lecture/dictation prompts and light/medium styles. Concrete numeric/negation/
  text-size checks retain the source on warnings. Important edits need review.
  Summary requests structured source-passage selections, validates indices and
  headings, and renders source text with conservative rules. Its output/history
  are separate; summary selection permits omissions.
  Completed results retain immutable AI snapshots and atomically publish a latest
  file with source hash, original speech provenance, and cleanup settings.

- `formatting.py` — independent layouts reading Raw, Balanced, or AI. Mostly prose
  requires no model; Mixed/Structured reuse the cleanup pipeline where available.
  Layout plans must cover every numbered passage once in source order. Headings
  quote their block; tables require explicit comparable numeric rows, and steps
  require source step markers. Invalid plans fall back to complete prose. Original
  versions remain unchanged; formatted snapshots and source hashes are retained.

## Desktop and outer adapters

The PySide6 desktop provides a lecture library, playback, editing and exports.
It starts CLI transcription and cleanup through `QProcess`. Transcription checks
a stop-file between chunks; cleanup checks cancellation between source blocks
and during generation. Model compilation must finish before cancellation can
complete. The GUI and CLI share the same storage and pipeline.
Source installations start a worker with the current Python interpreter. The
experimental frozen recipe uses a separate console worker beside the GUI.

`desktop_dictation.py` adds a nonmodal dictation window. Qt captures bounded native
PCM; a short thread converts it to mono 16 kHz WAV. A separate CLI process runs
speech and selected cleanup in dictation mode, then exits to release model memory.
Dictation has its own sessions, cache, settings, recordings, and durable recovery
history under the library's `dictation` directory. File and dictation jobs share
a desktop busy guard.

`dictation.py` handles shortcut parsing, audio conversion, and atomic history.
`windows_dictation.py` registers a Windows hotkey, checks focused-field metadata
through UI Automation, and sends Unicode input after saving the recovery copy.
Hold mode polls release of the configured keys; no keyboard hook is installed.
Focus/password checks fail to recovery, and closing unregisters the shortcut.
A bundled FFmpeg decoder executable remains unimplemented. Earlier PyInstaller bundles and the Inno Setup recipe
passed [one-host installation and lifecycle checks](host-validation/evidence/2026-10-02/package-validation/README.md)
and [native frozen review checks](host-validation/evidence/2026-10-02/frozen-review/README.md).
Those builds predate AI cleanup; the current cleanup-enabled executable and
installer have not been rebuilt and exercised. Wizard/startup/version-upgrade
checks and complete redistribution notices also remain pending. See
[packaging](packaging/README.md).
Only explicit acquisition/evaluation commands initiate network downloads.

## Data directory layout

```
<data>/lectures/<session-id>/
    session.json            mutable status/diagnostics
    source/original.<ext>   preserved private copy of the import
    source/source.json      size + sha-256 fingerprint
    checkpoint.json         atomic per-chunk progress (removed on finalize)
    raw-transcript.json     create-once immutable
    balanced-transcript.json create-once immutable
    edits/                  retained manual revision snapshots
    ai-transcript.json      latest complete AI result (optional)
    ai-cleanup-history/     retained complete AI snapshots
    formatted-transcript.json latest complete layout (optional)
    formatting-history/     retained complete layout snapshots
    summary-transcript.json latest complete excerpt notes (optional)
    summary-history/        retained complete summary snapshots
    exports/                generated, never silently overwritten
<data>/models/<model-id>/   checksum-verified installs
<data>/cache/cleanup/       separate text-model compilation caches
<data>/device-benchmarks.json
<data>/evaluation/          evaluation media and reports
```

Default location comes from `platformdirs`; override with `--data-dir` or
`NPUSCRIBE_DATA_DIR`. The application does not prevent an override into the
repository or a cloud-synced folder. See [Privacy](PRIVACY.md).
