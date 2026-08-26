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
- `cleanup.py`: commands, literal escaping, deterministic modes, rewrite risk checks.
- `dictionary.py`: explicit versioned mappings with conflict rejection.
- `devices.py`: measured benchmarks, identity-keyed cache, selection/fallback order.
- `export.py`: text, Markdown, SRT (validated), and versioned JSON to files.
- `evaluate.py`: manifest-driven evaluation with the recorded selection policy.
- `metrics.py`: dependency-free WER/CER.
- `cli.py`: subcommand CLI (`models`, `devices`, `transcribe`, `resume`,
  `export`, `evaluate`) tested through the real entry point.

Follow a feature into the tests with `rg 'symbol_name' tests src`. Start debugging storage
at `SessionStore.save_transcript`; start inference debugging at provenance construction;
start resume debugging at `BatchRunner.resume`.
