# Held-out continuous lecture overlap comparison (2026-10-01)

Three new Open Yale Courses passages were fixed before the overlap runs, from
three lecturers absent from the initial Yale comparison. They total 1,432.22
seconds (23:52) and 3,583 scored reference words. "Held out" means unused in
the initial local overlap decision; absence from Whisper's training data is
not established. All sources are still from Yale, so this is not an
independent test of recording conditions at another institution.

| Source passage | Duration | Words | tiny WER: 1 s → 0 s | base WER: 1 s → 0 s |
| --- | ---: | ---: | ---: | ---: |
| [Mark Saltzman, BENG 100: disease control](https://oyc.yale.edu/biomedical-engineering/beng-100/lecture-1), chapter 4 | 490.62 s | 1,305 | 10.11% → 6.67% | 10.96% → 8.35% |
| [Paul Bloom, PSYC 110: scientific consensus against dualism](https://oyc.yale.edu/psychology/psyc-110/lecture-2), chapter 2 | 442.60 s | 1,054 | 10.44% → 9.30% | 10.25% → 5.69% |
| [Robert Wyman, MCDB 150: population biology introduction](https://oyc.yale.edu/molecular-cellular-and-developmental-biology/mcdb-150/lecture-1), chapter 1 | 499.00 s | 1,224 | 17.81% → 10.38% | 9.97% → 8.17% |
| **Pooled** | **23:52** | **3,583** | **12.84% → 8.71%** | **10.41% → 7.51%** |

Both models ran each passage twice at each overlap setting: 24 completed CPU
runs, all `ready`, with zero reported fallback. Each pair used 0,1 then 1,0
ordering. Repeated normalized transcript hashes and WER were identical for
every condition. Zero overlap improved all six model/passage comparisons.
Pooled edit totals were 460 → 312 for tiny and 373 → 269 for base.

The [source snapshot](sources.json) records URLs, original MP3/HTML hashes,
prepared-WAV hashes, exact clip boundaries, Python/runtime versions, and
verified model revisions. [runs.json](runs.json) contains the measurements;
[analysis.json](analysis.json) adds edit types and boundary diagnostics.
Neither contains audio, reference text, model text, or private paths.

## Errors at chunk boundaries

Full transcript alignment was checked against the official reference text.
A seam deletion is a contiguous missing reference span whose neighboring
output words came from different input chunks. This avoids inventing
reference word timestamps, but does not catch every omission near a seam.
Minimum-edit alignment prefers diagonal operations when costs tie; some
error locations and substitution/deletion choices can be ambiguous.

The first repetition contained five single-word seam deletions for tiny and
three for base at zero overlap. All eight reference words matched exactly
in the corresponding 1-second output. The local context excerpts were
inspected: seven were short words; one was a place name. At 1-second overlap,
the same diagnostic found two missing phrases totaling eight words at other
boundaries. These are text comparisons, not an independent listening audit.

| Model | Overlap | Substitutions | Deletions | Insertions | Seam deletion events / words |
| --- | ---: | ---: | ---: | ---: | ---: |
| tiny | 1 s | 139 | 120 | 201 | 1 / 5 |
| tiny | 0 s | 139 | 68 | 105 | 5 / 5 |
| base | 1 s | 96 | 57 | 220 | 1 / 3 |
| base | 0 s | 95 | 59 | 115 | 3 / 3 |

Thus the base improvement is primarily fewer insertions, with two more
reference deletions overall. Zero overlap does not eliminate cut-word
omissions. Raw chunk output had 42 suffix/prefix matches of 2–20 words at
1-second seams, versus four at zero-overlap seams across the six first
repetitions. Such matches can include legitimate repetition. The existing
whole-segment merger dropped one segment in each base biomedical engineering
1-second run; it did not handle most partial phrase matches.

## Runtime

Each CPU model pipeline was warmed before measurement and reused. Batch wall
time includes source import, normalization, chunk reads, and checkpoint and
transcript writes; it excludes the warmup, source download, and clip preparation.
The table sums the median of the two runs for each passage. It is a small
one-host timing comparison, without control of background system activity.

| Model | Inference: 1 s → 0 s | Batch wall: 1 s → 0 s | Inference RTF: 1 s → 0 s |
| --- | ---: | ---: | ---: |
| tiny | 56.66 s → 44.61 s | 66.76 s → 53.41 s | 0.0396 → 0.0311 |
| base | 79.73 s → 72.68 s | 88.46 s → 81.11 s | 0.0557 → 0.0507 |

Zero overlap was faster in the pooled measurements, but not on every case:
base's biomedical engineering inference medians were 25.665 s at 1 second
and 26.175 s at zero. The differences do not support a universal speed claim.

One session-metadata save returned Windows `WinError 5` before inference on
the 23rd attempted run. Restarting the harness completed the two remaining
measurements; its completed-run index preserved the first 22. The failure's
cause was not isolated, and that incomplete attempt is excluded from WER and
runtime totals. The two resumed measurements used a newly warmed pipeline.

## Reference limits and decision

Yale's published transcripts are independent of these model outputs, but
their words were not audited by listening. The BENG chapter markers were
about 11 seconds later than the MP3 phrases; PSYC had a similar discrepancy.
Gross alignment probes located the chapter's opening and closing phrases
before the overlap runs. Those two boundaries are ASR-assisted, not
independently verified. The original markers and applied boundaries are
recorded in sources.json; no chapter was selected or replaced based on its
A/B WER. MCDB's 0–499-second published interval matched its opening and
closing text in the probes. Transcript editing, mathematical wording, and
the clip ends can still affect scores.

The evidence supports retaining zero overlap as the current local default.
Across the initial and held-out Yale sets it improved all 12 model/passage
comparisons. It does not establish finished boundary handling or verified
gold WER. Positive overlap remains available explicitly. The 100 short
NPTEL excerpts cannot test this choice because every excerpt fits in one
30-second chunk.

The lecture authors and Yale University supply the source material through
Open Yale Courses, accessed 2026-10-01. [Yale's terms](https://oyc.yale.edu/terms)
describe most lecture material as CC BY-NC-SA 3.0; this local evaluation is
noncommercial. Original recordings, text-bearing manifests, raw chunk logs,
and seam-review excerpts remain in ignored local storage.

## Reproduce

Download the three MP3s and HTML pages named in sources.json into an ignored
directory. Run `host-validation/Prepare-YaleContinuousPilot.py SOURCE_DIR
PREPARED_DIR --ffmpeg PATH --source-set holdout`. Then run
`host-validation/Measure-OverlapPilot.py PREPARED_DIR/manifest.json MODEL_ROOT
LOCAL_DATA_ROOT OUTPUT.json --rounds 2` with the verified model directories.
Finally run `host-validation/Analyze-OverlapPilot.py PREPARED_DIR/manifest.json
LOCAL_DATA_ROOT ANALYSIS.json LOCAL_REVIEW.json`. Keep the data root and review
output ignored; they contain lecture text and media. The scripts run through
the application's `BatchRunner` and validate alignment edit totals against
the existing WER scorer.

The Windows network-free suite passed 105 tests, skipped one symlink test,
and deselected one opt-in live test. Ruff lint/format checks passed. Arithmetic,
ready status, CPU/fallback labels, repeated transcript hashes, and evidence
sanitization were checked against the completed local sessions. No commit or
push was performed.
