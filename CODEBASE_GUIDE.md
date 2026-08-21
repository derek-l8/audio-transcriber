# Codebase guide

- `models.py`: versioned segment, transcript, provenance, and session records.
- `engines.py`: `SpeechEngine`, deterministic mock, PCM validation, OpenVINO adapter.
- `storage.py`: `atomic_write`, safe child resolution, immutable `SessionStore` layers.
- `pipeline.py`: `run_lecture` processing/checkpoint orchestration.
- `cleanup.py`: commands, literal escaping, deterministic modes, rewrite risk checks.
- `dictionary.py`: explicit versioned mappings with conflict rejection.
- `devices.py`: measured policy that rejects disguised fallbacks.
- `export.py`: text, Markdown, SRT, and versioned JSON.
- `metrics.py`: dependency-free WER/CER.
- `cli.py`: deterministic CLI, mock by default and explicit local model path for OpenVINO.

Follow a feature into the tests with `rg 'symbol_name' tests src`. Start debugging storage
at `SessionStore.save_transcript`; start inference debugging at provenance construction.
