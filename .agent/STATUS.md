# Implementation status

Updated: 2026-08-21 UTC

Current milestone: Milestone 0 sandbox gate met; partial Milestones 1–5 implemented.

## Evidence and decisions

- Read the complete 804-line PRD at `docs/NPU-SCRIBE-PRD.md`.
- Chose a provisional Python/PySide/OpenVINO architecture; see `DECISIONS.md`.
- Added contracts and initial implementations for speech engines, immutable storage,
  exports, metrics, cleanup, dictionary, device policy, and lecture orchestration.
- OpenVINO 2026.3 CPU proof loaded and executed pinned Whisper tiny.en INT4 from scratch;
  exact single-run evidence is in `MODEL_EVALUATION.md`. Only CPU was enumerated.
- Added initial desktop entry point, insertion/OneDrive contracts, PyInstaller/Inno Setup
  definitions, and round-one PowerShell validation. These are host-unverified.
- `/workspace` is correct. No startup boundary-failure report was present.
- Git branch `main` has no commits and all starting files were untracked. Owner explicitly
  directed continuation; `.git` remains untouched. Packaging diffs may be unreliable.
- Sandbox Python is 3.11.2. Root package directories are read-only; `python3-venv`, FFmpeg,
  PowerShell, .NET, and Rust are absent. Pip was bootstrapped into `/agent/scratch` only.

## Commands and results

- `rg --files -uu ...`, PRD chunk reads, source inspection: passed.
- `apt-get update`: failed because `/var/lib/apt/lists` is read-only.
- Scratch pip bootstrap: succeeded; checksum recorded in `.agent/SOURCES.md`.
- `ruff format --check .` and `ruff check .`: passed after fixes.
- `mypy src`: passed in strict mode across 14 source files.
- `pytest --cov=npu_scribe`: 10 passed, 80% total coverage.
- `python3 -m compileall -q src`: passed.
- Large-file scan: no repository files over 5 MB.

## Host-only pending

All Windows/NPU, microphone, tray, shortcut, Word/Notion/Codex insertion, startup,
installer, and target-machine performance evidence is pending.

## Next action

Finish chunking/media/history/UI/diagnostics and expand the Windows harness with identical
device benchmarks after the model-acquisition manifest is implemented.
