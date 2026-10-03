# Provisional MIT OCW lecture evaluation — 2026-09-30

Four roughly two-minute clips (461.77 seconds total) came from two MIT
OpenCourseWare courses and two lecturers. The [source record](sources.json)
lists each official lecture page, MIT-linked video, timed caption file,
published transcript PDF, license, clip interval, and SHA-256 hashes. Audio,
captions, PDFs, and the text-bearing evaluation manifest remain in the per-user
validation directory outside Git. The source material is CC BY-NC-SA 4.0;
these derived clips were used for local, noncommercial testing.

The official PDF transcripts and time-coded captions differ by 0–1 tokens in
each selected interval. They appear to be two presentations of the same
transcript, so this check establishes provenance and alignment, **not** an
independently verified word-for-word reference. Some published caption wording
is suspect. The figures below are **caption-relative error rates**, not
established accuracy against manually checked speech.

Both pinned models ran on the same Windows host with OpenVINO 2026.3.0 and
openvino-genai 2026.3.0.0, explicit CPU selection, the product's default
30-second chunks and 1-second overlap, and the same aligned PCM clips. All
eight final cases completed. `WER` and `CER` in the original reports use
case-insensitive whitespace tokenization and retain punctuation.

| Clip | Tiny WER | Base WER | Tiny RTF | Base RTF |
|---|---:|---:|---:|---:|
| 6.01SC: Object-Oriented Programming | 0.0885 | 0.0721 | 0.0232 | 0.0461 |
| 6.01SC: Circuits | 0.0885 | 0.1091 | 0.0244 | 0.0357 |
| 6.01SC: Op-Amps | 0.0764 | 0.0945 | 0.0219 | 0.0350 |
| 6.002: Circuit Abstraction | 0.2849 | 0.2582 | 0.0225 | 0.0354 |

Mean clip WER is 0.1346 for tiny and 0.1335 for base: a difference of about
0.11 percentage points. A separate punctuation-insensitive word comparison
across all 1,256 caption words gave 0.0916 for tiny and 0.0924 for base,
reversing the ranking. Total recorded chunk time was 10.622 seconds for tiny
and 17.560 seconds for base across the 461.77 seconds of audio. Chunk time
includes first-use model loading; one run per model does not establish a
stable speed ratio. No default model follows from these small, caption-based
measurements.

The first batch pass exposed a base-model repetition at a zero-duration
timestamp and an out-of-range timestamp on another clip. The engine now
discards zero-duration and out-of-audio spans. The batch runner now reuses a
loaded engine across chunks, and a failed evaluation case yields a failed
report and nonzero CLI exit. The attached [tiny report](tiny.report.json) and
[base report](base.report.json) are from the corrected path. Individual
single-model reports intentionally make no model selection.

The remaining reference-quality step requires listening to the audio. This
environment can inspect audio files and transcripts but cannot hear playback,
so no manual correction or gold WER is claimed.
