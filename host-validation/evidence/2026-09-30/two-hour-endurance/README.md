# Two-hour synthetic CPU endurance — 2026-09-30

The local [endurance harness](../../../Measure-AudioTranscriberEndurance.ps1) ran the
pinned base.en INT4 model on a 7,200-second, mono 16 kHz, 16-bit silent WAV on
one Intel Core Ultra 5 335 Windows host. The file was validated as PCM and
kept outside Git. The application used explicit CPU binding, 30-second chunks,
and 1-second overlap. Silence measures pipeline endurance and recoverability,
not transcription accuracy. The reports contain no audio or transcript text.

Two continuous runs finished all 249 planned chunks in unique, ascending order
with zero reported
fallbacks. The application saved a checkpoint during each run, preserved a
source copy with the same SHA-256, and saved raw and balanced transcript
layers. The second session also exported JSON, Markdown, text, and SRT for
both layers. The first run took 89.9 wall seconds; the second took 94.6.

| Run | Process-tree samples | Median actual interval | Sampled peak | Post-warmup first-quarter median | Last-quarter median |
|---|---:|---:|---:|---:|---:|
| [Requested 5 s](endurance-120min-5s.json) | 15 | 5.6 s | 396.9 MB | 387.3 MB | 387.6 MB |
| [Requested 1 s](endurance-120min.json) | 57 | 1.6 s | 408.6 MB | 389.2 MB | 390.0 MB |

Each sample sums the root process and descendants; the denser run saw three
processes at every sample. The post-warmup median changed by 0.8 MB from the
first to the last quarter of that run. This is evidence of no sustained memory
growth in these two synthetic passes. Sampling can miss shorter spikes. An
earlier one-hour validation recorded a higher 1,211.8 MB sampled peak under a
different run setup; the reason for that difference has not been established,
so these numbers do not establish a stable peak-memory requirement.

An initial attempt stopped after 125 of 249 chunks without a captured worker
error. Its durable checkpoint survived, and an explicit CPU resume completed
the session to 249 unique chunks with no reported fallback. The two later
continuous runs passed. The interruption's cause remains undetermined.
