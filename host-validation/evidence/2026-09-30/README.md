# Windows host validation evidence — 2026-09-30

These sanitized JSON reports were produced by
`Invoke-NpuScribeValidation.ps1` on one Intel Core Ultra 5 335 Windows host
with Python 3.12.14, OpenVINO 2026.3.0, and openvino-genai 2026.3.0.0.

- `device-smoke.json`: pinned tiny and base model acquisition passed size and
  SHA-256 checks. The pinned tiny model completed synthetic-silence sessions
  with explicit CPU, GPU, and NPU requests, ready status, and no reported
  fallback. Its `actual` field follows successful construction and generation
  with the requested device; it is not an independent hardware query.
- `endurance.json`: an installed tiny model passed the integrity probe. A
  synthetic one-hour PCM WAV was interrupted after three CPU chunks and
  resumed to ready with 125 ordered unique chunks. A separate continuous CPU
  run completed in 2.4 wall minutes; the 10-second samples found a peak
  process-tree working set of 1211.8 MB.

Neither report measures WER/CER on speech, NPU speedup, two-hour memory
growth, or compatibility across Windows machines. The original reports are
kept here without altering their measurements. Model files and synthetic media
are stored outside Git.

A separate [provisional real-lecture evaluation](lecture-evaluation/README.md)
records four MIT OCW clips and caption-relative scores for tiny and base on
CPU. Its published captions have not been manually verified against audio.

The subsequent [real-lecture device matrix](device-lecture-evaluation/README.md)
ran both models on those clips with explicit CPU, GPU, and NPU requests. It
documents an NPU pipeline state defect, the local correctness fix, and the
resulting per-device timing and caption-relative WER.

The later [two-hour synthetic CPU endurance](two-hour-endurance/README.md)
completed twice with process-tree memory series and source/export checks.
