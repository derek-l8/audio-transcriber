# Pause detector refinement — 2026-10-02

Investigated the three earlier regressions; tested one frozen candidate on new passages from three lecturers. Development: 12 completed pause-v2 CPU sessions on the three existing passages (both models, two repeats), compared with the prior fixed/v1 measurements. Independent project-validation set: 1274.00 seconds (21.23 minutes), 3030 normalized reference words, 36 completed CPU sessions (three strategies, two models, two repeats). All completed sessions ready, CPU, no reported device fallback.

## Decision from the independent comparison

Keep pause-v2 experimental; do not replace fixed cuts or pause-v1 with it.
On the new set, v2 has slightly lower tiny WER than v1 (12.67% versus 12.90%),
but higher base WER (9.77% versus 8.98%) on every passage. Base seam-deletion
words rise from 3 with v1 to 13 with v2, versus 7 with fixed cuts. Stricter
quiet detection did not establish safer speech boundaries. Both pause
strategies beat fixed cuts on 5/6 model/passage comparisons and lower pooled
WER, but tiny still regresses on game theory and development psychology remains
worse with v2. Fixed zero-overlap remains default; both candidates stay opt-in.

## What the regressions show

These observations describe output and waveform energy. They do not establish whether every reference-absent phrase was absent from the recording; no listening audit was available.

- Biomedical engineering, tiny: v1’s longest consecutive identical-word run was 14 words, versus 5 with fixed cuts. New reference-relative errors clustered in chunks ending at 354.58 and 384.49 seconds. The former was a forced 30-second fallback in active audio (160 ms neighborhood RMS -24.93 dBFS); the latter was a selected but comparatively weak gap (-37.30 dBFS). V2 reduced the longest run to 6 and the total errors from 104 to 86. This supports investigating cut/context-dependent repetition, not deleting repeated words from transcripts.
- Population biology, tiny: changed names and phrases contributed errors; there was no long identical-word run. Some v1 cuts were very quiet, but the 205.62-second cut had neighborhood RMS -39.23 dBFS. V2 used deeper gaps and reduced total errors from 131 to 122. Low energy alone does not establish word boundaries or causality.
- Psychology, base: v1 added a reference-absent nine-word sentence at one quiet chunk tail and missed other reference words. V2 did not resolve the regression: total errors rose from 62 to 70, versus 60 with fixed cuts. Quiet gaps and decoder context both remain possible contributors.

regression-diagnostics.json contains numerical cut levels, fallback counts, and repetition lengths. Full error contexts stay in ignored local files. A different chunk boundary changes both endpoint acoustics and the context seen by Whisper; this experiment does not isolate those two effects.

## Frozen candidate

pause-v2 uses 20 ms RMS blocks, at least 240 ms of quiet, a threshold no greater than -45 dBFS and 10% of peak local RMS, and a cut 120 ms after the observed start of quiet. It searches the last three seconds before the maximum cut with up to 300 ms of lookahead; actual inference inputs remain <=30 seconds. It rejects a quiet run already in progress at the search region’s start. If none qualifies, it retains the maximum-length cut. Every source frame remains covered once; no silence or transcript words are removed.

Parameters were set from the earlier regression inspection before reading new-lecture WER, then frozen for all new runs. frozen-candidate.json records parameters and local source-code hashes. pause-v1 remains unchanged. Both candidates are opt-in and fixed zero-overlap cuts remain default. Checkpoint schema 2 saves selected frame boundaries; pause-v2 resume is tested without rerunning selection.

## Development results

| Model/passage | Fixed WER | V1 WER | V2 WER |
|---|---:|---:|---:|
| tiny.en / holdout-beng100-disease-control | 6.67% | 7.97% | 6.59% |
| tiny.en / holdout-mcdb150-population-biology | 10.38% | 10.70% | 9.97% |
| base.en / holdout-psyc110-neuroscience | 5.69% | 5.88% | 6.64% |

Development is not independent confirmation. V2 improves two original regressions and worsens the third; its combined error count on those three model/passage pairs is 278 versus 274 fixed and 297 v1. Development runtime is not used for the decision: a short alignment probe overlapped early development inference.

## New-lecture results

| Model | Strategy | WER | S / D / I | Seam-deleted words | Inference seconds | Batch wall seconds |
|---|---|---:|---|---:|---:|---:|
| tiny.en | fixed | 13.40% | 193 / 66 / 147 | 8 | 31.75 | 38.94 |
| tiny.en | pause-v1 | 12.90% | 179 / 61 / 151 | 5 | 30.67 | 38.66 |
| tiny.en | pause-v2 | 12.67% | 170 / 64 / 150 | 5 | 31.13 | 39.34 |
| base.en | fixed | 11.49% | 133 / 72 / 143 | 7 | 56.08 | 63.41 |
| base.en | pause-v1 | 8.98% | 103 / 63 / 106 | 3 | 52.89 | 61.16 |
| base.en | pause-v2 | 9.77% | 100 / 77 / 119 | 13 | 49.91 | 58.26 |

WER = word error rate; S/D/I = substitutions/deletions/insertions. Pooled WER sums errors and reference words once per condition. Timing sums each passage’s median from two repeats.

| Model | Passage | Fixed WER | V1 WER | V2 WER |
|---|---|---:|---:|---:|
| base.en | new-eeb122-natural-selection | 8.28% | 5.69% | 6.67% |
| base.en | new-econ159-dominant-strategies | 19.13% | 14.94% | 15.85% |
| base.en | new-phil176-self-identity | 6.32% | 5.52% | 6.06% |
| tiny.en | new-eeb122-natural-selection | 8.90% | 6.92% | 7.29% |
| tiny.en | new-econ159-dominant-strategies | 21.68% | 22.77% | 22.13% |
| tiny.en | new-phil176-self-identity | 8.55% | 7.57% | 7.30% |

All normalized transcripts and word-error counts matched between repeats. Order was fixed/v1/v2 then v2/v1/fixed; each model used a warmed CPU pipeline. Batch wall includes source copying, inspection, boundary selection, inference, checkpoint writes, and transcript writes; it excludes reference scoring, model warmup, download/preparation, and the helper’s separate plan for instrumentation. One host, two repeats, uncontrolled background load; short verification tooling also ran during early new measurements. These are observed timings, not a general speed claim.

## Sources and reference limits

- [Stephen Stearns, EEB 122 lecture 1](https://oyc.yale.edu/ecology-and-evolutionary-biology/eeb-122/lecture-1): chapter 3, 959–1285 seconds (326 seconds), natural selection.
- [Ben Polak, ECON 159 lecture 1](https://oyc.yale.edu/economics/econ-159/lecture-1): chapter 5, 1298–1773 seconds (475 seconds), dominant/dominated strategies, including classroom responses.
- [Shelly Kagan, PHIL 176 lecture 2](https://oyc.yale.edu/philosophy/phil-176/lecture-2): 805–1278 seconds (473 seconds). The published chapter-2 start at 805 seconds did not match the chapter’s opening text in the MP3; ASR probes placed that opening around 728 seconds. The chosen audio starts at 805 and its reference starts at the original transcript paragraph beginning “As I said”. The endpoint matched the next chapter in gross probes. This corrects reference selection before A/B scoring; it does not certify word-level edges by listening.

All recordings/transcripts were acquired from official Yale pages. Sources, original/prepared hashes, sizes, license labels, model revisions, and versions are in sources.json. These passages/lecturers were new to this project’s comparison, but all remain in the same institutional recording domain and their presence in model training is unknown. Published text can omit fillers, edit wording, or represent numbers/symbols differently from speech; the game-theory passage is especially affected by numbers and classroom discussion. Absolute WER is provisional. Identical source/reference inputs support a paired comparison, not an audio-audited accuracy claim.

Seam deletion counts use minimum-edit alignment and adjacent output words assigned to different input chunks. They omit some near-boundary errors and can be ambiguous. The scorer’s S+D+I total is checked against the independent rolling-row distance. Full transcript contexts and recordings remain ignored.

## Verification and reproduction

- 117 deterministic tests passed; 1 Windows symlink test skipped, 1 opt-in live test deselected. Tests cover stricter gap selection and pause-v2 saved-plan resume.
- All 48 completed development/new sessions: ready, zero reported fallback, continuous audio coverage, <=30-second inputs. New repeated transcript hashes and error counts identical.
- Ruff lint/format, byte compilation, git whitespace checks, and numerical/public-report checks passed. Local changes only; no commits or pushes.

Prepare pinned new sources using Prepare-YaleContinuousPilot.py with --source-set refinement and explicit FFmpeg. Keep media, references, and session data ignored. Then:

```powershell
.venv/Scripts/python.exe host-validation/Measure-OverlapPilot.py MANIFEST MODEL_ROOT IGNORED_DATA_ROOT NEW_RUNS_JSON --comparison pause --strategies fixed pause-v1 pause-v2
.venv/Scripts/python.exe host-validation/Analyze-OverlapPilot.py MANIFEST IGNORED_DATA_ROOT NEW_ANALYSIS_JSON IGNORED_REVIEW_JSON
```

Use a fresh data/output root for algorithm or source changes. Completed-run keys include model, case, repeat, overlap, and strategy.
