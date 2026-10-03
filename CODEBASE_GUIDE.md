# Codebase guide

- `models.py`: versioned segment, transcript, provenance, and session records.
- `media.py`: media-decoder boundary; PCM WAV direct, FFmpeg adapter (fixed argv).
- `chunking.py`: bounded chunk planning/reads, absolute timestamps, overlap merge.
- `checkpoint.py`: versioned durable checkpoints; resume validation.
- `engines.py`: `SpeechEngine`, deterministic mock, OpenVINO GenAI adapter with
  real timestamp-chunk parsing and English forcing for multilingual checkpoints.
- `storage.py`: `atomic_write`, safe child resolution, imported-source copies,
  immutable raw/balanced layers, exports directories.
- `pipeline.py`: `BatchRunner` batch orchestration with device fallback;
  `run_lecture` kept as a compatibility wrapper.
- `acquisition.py`: manifest-approved staged downloads with SHA-256 verification.
- `cleanup.py`: conservative Balanced rules; older formatting/rewrite helpers
  remain available but are not the model-based cleanup path.
- `ai_cleanup.py`: local text model, bounded requests, lecture/dictation prompts,
  heuristic source fallback, AUTO device fallback, cancellation, retained AI versions,
  and separate formatted excerpt summaries.
- `formatting.py`: independent source-preserving layout, validated passage plans,
  prose fallback, complete snapshots and formatted exports.
- `editing.py`: manual revisions, retained history, source hashes and stale-write checks.
- `desktop.py` / `desktop_ui.py`: optional Qt launcher and child-worker interface.
- `desktop_player.py` / `desktop_editing.py`: playback, seeking and edit/history dialogs.
- `dictionary.py`: explicit versioned mappings with conflict rejection.
- `devices.py`: measured benchmarks, identity-keyed cache, selection/fallback order.
- `export.py`: text, Markdown, SRT (validated), and versioned JSON to files.
- `evaluate.py`: manifest-driven evaluation with the recorded selection policy.
- `metrics.py`: dependency-free WER/CER.
- `cli.py`: subcommand CLI (`models`, `devices`, `transcribe`, `resume`,
  `export`, `cleanup`, `cleanup-text`, `format`, `summarize`, `evaluate`) tested through the real entry point.

Follow a feature into the tests with `rg 'symbol_name' tests src`. Start debugging storage
at `SessionStore.save_transcript`; start inference debugging at provenance construction;
start resume debugging at `BatchRunner.resume`.
