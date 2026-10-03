# Pause-based chunk boundary pilot — 2026-10-01

Paired fixed versus pause-v1 comparison on six previously prepared Yale passages: 2946.22 seconds (49.10 minutes), 7728 ASCII-normalized reference words, two models, two repeats, 48 completed CPU sessions. No reported device fallback. All condition-specific normalized transcripts and error counts matched across repeats.

## Results

Pause-v1 lowers pooled WER and the measured seam deletion count for both models,
but improves only 9 of 12 passage/model comparisons. Keep it experimental and
opt-in; fixed zero-overlap cuts remain the local default. Tiny regresses on
biomedical engineering and population biology, and base regresses on psychology.
The largest regression is tiny biomedical engineering: 6.67% to 7.97% WER.

Of 36 reference words deleted at fixed seams across the two models, 35 are
exact matches in pause output (tiny 13/13, base 22/23). Seven reference words
deleted at pause seams are exact matches in fixed output (tiny 1, base 6).
This comparison uses text alignment, not a listening audit. The net improvement
does not establish that every new cut preserves speech.

| Model | Cuts | WER | S / D / I | Seam deletion words | Inference seconds | Batch wall seconds |
|---|---|---:|---|---:|---:|---:|
| tiny.en | fixed | 9.68% | 337 / 175 / 236 | 13 | 78.55 | 95.72 |
| tiny.en | pause-v1 | 8.71% | 312 / 132 / 229 | 2 | 76.08 | 94.89 |
| base.en | fixed | 8.10% | 221 / 159 / 246 | 23 | 136.98 | 154.22 |
| base.en | pause-v1 | 7.45% | 200 / 152 / 224 | 8 | 125.90 | 144.89 |

WER is word error rate; S/D/I are substitutions, deletions, and insertions.

| Model | Passage | Fixed WER | Pause WER | Fixed / pause seam words |
|---|---|---:|---:|---:|
| base.en | yale-phys200-rigid-bodies | 8.50% | 6.46% | 9 / 0 |
| base.en | yale-astr160-course-topics | 5.61% | 4.57% | 2 / 2 |
| base.en | yale-chem125a-orbital-plots | 11.26% | 11.19% | 9 / 2 |
| base.en | holdout-beng100-disease-control | 8.35% | 7.74% | 1 / 1 |
| base.en | holdout-psyc110-neuroscience | 5.69% | 5.88% | 0 / 3 |
| base.en | holdout-mcdb150-population-biology | 8.17% | 8.09% | 2 / 0 |
| tiny.en | yale-phys200-rigid-bodies | 10.11% | 7.44% | 1 / 0 |
| tiny.en | yale-astr160-course-topics | 5.69% | 4.33% | 0 / 0 |
| tiny.en | yale-chem125a-orbital-plots | 14.99% | 13.23% | 7 / 1 |
| tiny.en | holdout-beng100-disease-control | 6.67% | 7.97% | 1 / 1 |
| tiny.en | holdout-psyc110-neuroscience | 9.30% | 7.87% | 1 / 0 |
| tiny.en | holdout-mcdb150-population-biology | 10.38% | 10.70% | 3 / 0 |

Runtime is the sum of each passage’s median from two repeats. Each model pipeline was warmed before measured runs; order was fixed/pause in repeat 1 and pause/fixed in repeat 2. Batch wall includes import, normalization inspection, pause selection, inference, checkpoint writes, and final transcript writes. It excludes pipeline warmup, source preparation, reference scoring, and the helper’s separate boundary planning for instrumentation. Two repeats on one host do not establish universal speed.

## Algorithm and implementation

- Keep zero overlap and a maximum 30-second input. Search only the final three seconds before each maximum-length cut (half the chunk for shorter requested chunks).
- Compute 20 ms RMS blocks. A qualifying quiet run lasts at least 160 ms with RMS no more than 20% of the search region’s peak, capped at -35 dBFS. Cut at the midpoint of the latest qualifying quiet run; otherwise retain the maximum-length cut.
- Parameters were chosen before running this comparison and were not tuned against these scores. Quiet energy is a heuristic, not speech recognition; background noise can prevent selection and unvoiced speech can resemble a pause.
- Consecutive windows cover every source frame once. The planner reads at most three seconds of samples per search. Input sample memory remains bounded; the window plan grows with recording duration.
- Checkpoint schema 2 stores the exact plan before inference. Resume validates and reuses it without searching again. Schema 1 fixed checkpoints remain readable and upgrade on save; older application code rejects schema 2.
- `--chunk-strategy pause-v1` is available for transcribe/evaluate. Resume uses the saved session strategy. `fixed` remains the default because three passage/model comparisons regress and new seam omissions remain. Positive overlap is rejected for pause-v1.

## Timestamp failure and repair

An initial tiny astronomy pause attempt stopped on the first chunk because adjacent OpenVINO timestamps overlapped by about 1.9 microseconds. A direct reproduction confirmed the returned numerical values. The adapter now snaps overlaps of at most 10 microseconds to the preceding endpoint. Larger overlaps retain valid-span text in runtime order as one uncertain span covering the input chunk. Two regression cases verify preserved text and monotonic output. The failed attempt is excluded from scores and timing; five completed measurements were retained, and the remaining runs used newly warmed pipelines. This repair does not alter normalized text on the retained successful measurements.

None of the 48 completed transcripts required the larger-overlap uncertain-span
fallback. The observed failure was numerical timestamp drift.

## Reference and boundary limits

These are published Yale chapter transcripts, not independently audio-checked references. Existing source alignment and editorial differences remain. Both conditions use identical prepared audio, hashes, and reference text. The six passages were already evaluated in overlap experiments; this is a paired engineering experiment, not a new held-out test or proof that these recordings were absent from model training. Source preparation provenance is in sources.json and the prior initial/held-out reports.

A seam deletion is a reference deletion whose neighboring hypothesis words originate from different input chunks, found by minimum-edit alignment. It does not capture all words near a cut and can be ambiguous. Numerical edit totals are checked against the independent rolling-row scorer. comparison.json reports how many deleted words at fixed seams are exact matches in pause output, and the reverse. Full text contexts and raw audio remain in ignored local scratch storage. No listening audit was performed.

## Verification

- 48 ready sessions, CPU and zero reported fallback; all audio hashes checked against the pinned manifests.
- Coverage and maximum input duration checked for every recorded plan; repeat normalized transcripts identical.
- Deterministic suite: 113 passed, 1 skipped (Windows symlink privilege), 1 opt-in live test deselected.
- Ruff lint/format and git diff whitespace checks passed.
- Changes remain local; no commit or push.

## Reproduce

Use the existing six prepared cases from `.scratch/yale/pilot/manifest.json` and `.scratch/overlap-holdout/pilot/manifest.json`, preserving their source hashes and reference text. Combine their case lists into one ignored manifest. Then:

```powershell
.venv\Scripts\python.exe host-validation/Measure-OverlapPilot.py MANIFEST MODEL_ROOT IGNORED_DATA_ROOT host-validation/evidence/2026-10-01/pause-pilot/runs.json --comparison pause
.venv\Scripts\python.exe host-validation/Analyze-OverlapPilot.py MANIFEST IGNORED_DATA_ROOT host-validation/evidence/2026-10-01/pause-pilot/analysis.json IGNORED_REVIEW_JSON
```

Completed-run keys include model, case, repeat, and strategy. A fresh data/output root is required when changing the algorithm or input data. The model directory must contain the checksum-verified manifest-approved tiny/base revisions.
