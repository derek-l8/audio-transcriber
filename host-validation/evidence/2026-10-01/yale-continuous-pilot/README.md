# Continuous classroom lecture pilot (Windows, 2026-10-01)

Three uninterrupted Open Yale Courses chapters from three lecturers were
prepared from Yale's official MP3 audio and HTML transcripts. This adds longer
speech to the earlier short NPTEL excerpts. The chapters total 1,514 seconds
(25:14) and 4,145 scored reference words:

The table below is the initial **1-second overlap** run. A matched 0-second
run and the resulting default change are reported further down.

| Lecture passage | Duration | `tiny.en` word edits / words (WER) | `base.en` word edits / words (WER) |
| --- | ---: | ---: | ---: |
| [Shankar, PHYS 200, rigid bodies](https://oyc.yale.edu/physics/phys-200/lecture-9) | 8:15 | 149 / 1,424 (10.46%) | 126 / 1,424 (8.85%) |
| [Bailyn, ASTR 160, course topics](https://oyc.yale.edu/astronomy/astr-160/lecture-1) | 7:19 | 113 / 1,247 (9.06%) | 118 / 1,247 (9.46%) |
| [McBride, CHEM 125a, orbital plots](https://oyc.yale.edu/chemistry/chem-125a/lecture-10) | 9:40 | 226 / 1,474 (15.33%) | 191 / 1,474 (12.96%) |
| **Pooled** | **25:14** | **488 / 4,145 (11.77%)** | **435 / 4,145 (10.49%)** |

Both models completed all three explicit CPU runs without reported fallback.
Recorded chunk seconds were 27.093 for tiny (RTF 0.0179) and 46.478 for base
(RTF 0.0307). These are one-pass CPU timings that include first-use pipeline
construction within each passage, but exclude media download, source decode,
and application startup. Base had fewer word edits on two of the three
passages; tiny had five fewer on the astronomy passage.

The primary scorer casefolds and ignores punctuation but uses ASCII
letter/digit tokens, retaining digits and internal apostrophes. A Unicode
letter/digit sensitivity pass gave 11.73% tiny and 10.46% base, preserving the
ranking. [`yale.json`](yale.json) and [`yale-unicode.json`](yale-unicode.json)
contain per-case counts, device, fallback, and timing; neither contains source
audio or transcript text.

## Chunk overlap comparison

The 1-second runs retained repeated words at chunk seams: an inspection found
35 adjacent suffix/prefix matches of 2–6 words near nominal seams across the
six transcripts. The existing whole-segment deduplicator dropped zero
segments. Those matches are a diagnostic, not independently audio-verified
deletions; some could be real repetition.

The same six WAVs were then transcribed on the same CPU with 30-second chunks
and **0-second overlap**. Punctuation-normalized word edits fell on all six
cases:

| Passage | tiny: 1 s → 0 s | base: 1 s → 0 s |
| --- | ---: | ---: |
| Physics | 149 → 144 | 126 → 121 |
| Astronomy | 113 → 71 | 118 → 70 |
| Chemistry | 226 → 221 | 191 → 166 |
| **Pooled WER** | **11.77% → 10.52%** | **10.49% → 8.61%** |

The 0-second Unicode-token sensitivity scores were 10.46% tiny and 8.55%
base. All six runs reached `ready` on explicit CPU, with no reported fallback
or dropped segments. The run used the same `BatchRunner` path as the CLI;
model and media files were unchanged. Scores are in
[`yale-zero-overlap.json`](yale-zero-overlap.json) and
[`yale-zero-overlap-unicode.json`](yale-zero-overlap-unicode.json). Raw output
and the A/B scripts remain in ignored local storage.

The application's default overlap is now zero. Explicit positive overlap
remains available for sources where it helps. A zero-overlap seam can split a
spoken word or lose context; this pilot shows lower transcript-relative WER
for these three passages, not a guarantee across lectures. Earlier scores in
this repository retain their original 1-second overlap settings. The 100
NPTEL excerpts are each under 15 seconds, so their one-chunk transcriptions
do not change with the overlap default.

## Reference and alignment limits

Yale publishes full transcripts with its classroom recordings and chapter
markers, but does not document a word-by-word audio verification process.
The references were not independently audited by listening in this run. The
model outputs' first and last phrases were compared with each chapter's
transcript to check gross alignment; that comparison cannot certify the
wording between them. Formulas, Greek symbols, speaker overlap, and editorial
transcript choices can also affect WER.

The chemistry page marks chapter 2 at 14:07, while its MP3 reaches the spoken
chapter-2 opening around 9:40. Applying the published marker to the MP3 gave
roughly 47% WER for **both** models and omitted hundreds of opening reference
words. That result was discarded. The final chemistry case uses 0:00–9:40 of
the MP3 and Yale's chapter-1 text; the 9:40 boundary was located with
ASR-assisted phrase matching, not a listening audit. Its opening matches the
published text. The last few reference words may lie just past the chosen
audio boundary. Source MP3 and HTML SHA-256 values, exact extraction rules,
and source URLs are pinned in `host-validation/Prepare-YaleContinuousPilot.py`.
The [Yale terms](https://oyc.yale.edu/terms) describe most course material as
CC BY-NC-SA 3.0; this local use is noncommercial. Raw media, transcript
manifests, and model output remain in ignored local directories.

## NPU investigation and device choice

The earlier [MIT lecture device runs](../../2026-09-30/device-lecture-evaluation/README.md)
found stale, truncated text on the second generation from one NPU Whisper
pipeline. Rebuilding the pipeline for each chunk restored complete output but
made NPU processing slower, especially for base.en. An [open OpenVINO issue](https://github.com/openvinotoolkit/openvino/issues/37937)
documents a matching state-reset symptom in OpenVINO 2026.3.0 and a proposed
plugin-level change on another NPU architecture. That issue supports an
upstream explanation but does not establish the exact cause on this host.
The installed Python `WhisperPipeline` exposes no public reset method, so no
safe local state-reset or reuse change was applied.

The host still uses OpenVINO 2026.3.0 / GenAI 2026.3.0.0. Its NPU reports
architecture `5010` and driver `1005540`. With the application's cached
device benchmarks, `auto` resolves to CPU for **both** models on this host;
the [sanitized device snapshot](device-decision.json) records the measurements.
The benchmark uses one second of silence and is not a sustained lecture
benchmark. The prior matched MIT repeat measured base NPU RTF 1.1788 then
1.5591 on a 118.76-second clip, so this run supplies no NPU speed claim.

## Reproduce

Download the three official lecture MP3s and pages to an ignored local
directory, then run `host-validation/Prepare-YaleContinuousPilot.py` with a
known FFmpeg executable. Evaluate both models on the prepared manifest with
`--device CPU --overlap-seconds 1` for the original pass, score those sessions,
then repeat with `--overlap-seconds 0` and score again. The `evaluate` CLI now
accepts that option. Use `host-validation/Score-ManualPilot.py` for
punctuation-normalized scores and its `--unicode-words` option for the
sensitivity pass. Score each condition before running the next one because
the scorer selects the newest matching sessions. The model selection remains
unchanged.
