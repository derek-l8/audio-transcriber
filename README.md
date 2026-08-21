# NPU Scribe

NPU Scribe is an English-only, local Windows lecture transcription and dictation
application under active development. It preserves source audio and immutable raw text
below cleanup and edits. OpenVINO backends are selected from measured workload results;
no NPU or Windows compatibility claim has yet been verified.

The current sandbox build provides the UI-independent core: PCM WAV inspection, an
OpenVINO GenAI Whisper adapter, a deterministic mock, transcript schemas, atomic session
storage, cleanup modes, dictionary substitution, exports, metrics, and device policy.
The desktop UI, Windows adapters, installer, and owner validation harness remain in work.

```bash
python -m pip install -e '.[dev]'
pytest
ruff check .
mypy src
```

Models are never bundled or fetched during ordinary operation. Do not place models,
recordings, transcripts, or diagnostics inside the repository. See
`REQUIREMENTS.md` for exact coverage and `.agent/TEST_RESULTS.md` for evidence.

License: original code is MIT. Third-party runtimes, models, media codecs, and datasets
retain their own licenses; redistribution review is not yet complete.
