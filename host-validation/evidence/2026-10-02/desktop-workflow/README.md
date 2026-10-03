# Desktop imported-lecture workflow

Implemented locally in the isolated `github-main-validation` checkout. No commit
or push. The placeholder window now provides a lecture library, file import,
model/device selection, configurable model folder and FFmpeg, background
transcription, chunk progress, safe pause/resume, timestamped Raw/Balanced
review, search, and exports. Raw and Balanced remain immutable.

## Windows host smoke

`results.json` records a real 72-second MP3 excerpt from the already downloaded
Yale EEB 122 lecture 1 held-out source. The excerpt begins at the beginning of
the existing `new-eeb122-natural-selection.wav` fixture. No additional source
download or accuracy scoring occurred. Pinned `whisper-tiny.en-int4-ov`, CPU,
OpenVINO/GenAI 2026.3, PySide6 6.8.2.1, configured FFmpeg 7.1.

- Imported through the Qt window into a new library and ran the real CLI child.
- Requested pause during processing; two chunks had committed when the worker
  stopped. Three total chunks completed after resume, without reported fallback.
- Resumed segment timestamps, text and flags exactly match a second uninterrupted
  import of the same compressed source.
- Search selected matching text; all four formats exported in both layers.
- The Qt event loop delivered 467 timer callbacks during the 15.56-second
  combined workflow. This shows event-loop activity during inference, not a
  quantified UI latency guarantee.
- Captured and visually inspected an offscreen rendering after reopening the
  completed library. Segoe UI was explicitly loaded in the offscreen harness
  because that platform initially rendered missing-font boxes. The native
  desktop launcher uses the platform's normal font discovery.

Audio, copies, transcript contents and the preview remain in ignored
`.scratch/desktop-real/`. The committed-format evidence contains only metadata.

## Verification and limits

The Qt tests use actual CLI child processes with a mock engine to exercise import,
review/search/export, reopening, pause/resume, closing during a job, missing
model and corrupt metadata. A core regression verifies that a pause after one
chunk preserves that chunk and resumes to the same segments as an uninterrupted
run. Real inference smoke is separate from these deterministic fixtures.

This is an imported-file workflow, not the entire lecture milestone. Microphone
recording, playback, summaries, full setup and packaging remain pending. Forced
termination recovery still uses the explicit CLI when a session is left
`processing`; the GUI does not assume that another worker has stopped. A desktop
library lock prevents duplicate GUI windows but does not lock out CLI operations.
Native mouse interaction, alternate Windows hosts, long GUI sessions, and GUI
GPU/NPU inference have not been validated by this smoke.

## Reproduce

Use an empty local library, a public lecture lasting more than one chunk, an
approved installed model folder, and an FFmpeg executable:

```powershell
python host-validation/Test-DesktopWorkflow.py lecture.mp3 `
  --data-dir .scratch/desktop-smoke/library `
  --model-root C:/path/to/models --ffmpeg C:/path/to/ffmpeg.exe `
  --report .scratch/desktop-smoke/results.json
```

The harness runs offscreen, pauses between chunks, resumes, exports both layers,
then compares with an uninterrupted session. It does not download models/media.
