# Testing

`tests/test_core.py` covers cleanup safety, formatting escape, dictionary round-trip,
device truthfulness, exports, metrics, and audio inspection. `test_storage_pipeline.py`
covers atomic immutable layers, recovery, and path traversal. Run `pytest` from the root.

Future test layers must add malformed-input properties, decoding/chunk integration,
network denial, synthetic two-hour bounded-memory processing, UI state contracts, and
Windows insertion. Host results must go in sanitized validation reports and be copied to
`.agent/TEST_RESULTS.md`; a skip is never a pass. Exact current results are recorded there.
