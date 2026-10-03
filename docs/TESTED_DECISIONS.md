# Tests and decisions

The project began as an attempt to use an NPU for local speech transcription
and cleanup while leaving the computer usable. Tests led to different device
choices: **CPU for speech; GPU with CPU fallback for cleanup**. NPU stays optional.

Measured September 30–October 2, 2026 on one Windows x64 host: Core Ultra 5 335,
Intel integrated graphics, Intel AI Boost NPU, 8 logical processors, 31.51 GiB
usable RAM. OpenVINO 2026.3.0 / GenAI 2026.3.0.0. The linked reports contain
methods, pinned models, and numerical results. Results apply to this computer
and these workloads; power consumption was not measured.

## Speech: model and device

The same 100 NPTEL clips from 100 lecture videos (838.42 seconds, 1,889 reference
words) ran on CPU. Word error rate counts word insertions, deletions, and
substitutions divided by reference words; lower is better.

| Model | Word edits | Pooled word error rate | Chunk time / audio time |
|---|---:|---:|---:|
| Whisper tiny.en INT4 | 455 | 24.09% | 0.1355 |
| Whisper base.en INT4 | 373 | 19.75% | 0.1803 |

**Decision:** tiny remains the small first-use model; base is the accuracy option.
Base improved pooled error by 4.34 percentage points at greater runtime cost.
The published annotations were used as supplied. Full-lecture accuracy remains
unmeasured.
[Clip selection, sources, and per-case results](../host-validation/evidence/2026-09-30/lecture-gold-pilot/README.md).

A 118.76-second MIT excerpt then ran twice per model/device. Below, recorded
chunk time divided by audio duration includes model loading but excludes app
startup; a ratio below 1 means faster than real time.

| Model | CPU: initial / repeat | GPU: initial / repeat | NPU: initial / repeat |
|---|---:|---:|---:|
| tiny.en | 0.0509 / 0.0206 | 0.1273 / 0.1135 | 0.4712 / 0.6255 |
| base.en | 0.0330 / 0.0320 | 0.0583 / 0.1174 | 1.1788 / 1.5591 |

**Decision:** start speech on CPU, which was fastest in these runs. The correct
NPU path rebuilds Whisper each chunk because reuse produced stale, truncated
text. Base on NPU was slower than real time here. Runtime binding succeeded on
all three devices; utilization was not independently measured.
[Repeat results](../host-validation/evidence/2026-09-30/lecture-gold-pilot/README.md#matched-lecture-device-repeat),
[four-clip check and NPU defect](../host-validation/evidence/2026-09-30/device-lecture-evaluation/README.md).

## Cleanup: quality, speed, and resource cost

An initial 1.5B model lost a corrected date without triggering the checks. The
chosen Qwen2.5 7B INT4 model handled targeted pilot examples better, at about
4.5 GB of downloads and several GiB of RAM. The model-size choice rests on this
small pilot. [Pilot](../host-validation/evidence/2026-10-02/ai-cleanup/README.md).

The 7B model ran 25 matched configurations twice per device with the cleanup-v2
prompt. One ambiguous case was excluded. Warmed timing excludes loading and
warmup. The current cleanup-v3 prompt has not had this three-device comparison.

| Device | Median request | Mean 25-request batch | All targeted checks passed | Final content checks passed |
|---|---:|---:|---:|---:|
| CPU | 3.78 s | 194.05 s | 40/48 | 46/48 |
| GPU | 1.09 s | 49.55 s | 42/48 | 46/48 |
| NPU | 2.99 s | 106.48 s | 40/48 | 46/48 |

GPU was faster and all devices passed 46 of 48 final-content checks. Literal
commands failed on every device; some warned outputs retained the source text.
[Inputs, outputs, startup times, and limitations](../host-validation/evidence/2026-10-02/ai-cleanup-comparison/README.md).

A separate fixed short request ran alongside moderate hardware graphics activity:

| Cleanup device | Warmed request | Worker CPU capacity used | Resident worker RAM |
|---|---:|---:|---:|
| GPU | 1.14 s | 10.1% | 4.67 GiB |
| NPU | 3.06 s | 0.96% | 5.46 GiB |
| CPU | 2.64 s | 27.9% | 8.48 GiB |

CPU percentages are the worker's share of whole-CPU capacity. RAM includes the
resident speech and cleanup pipelines, excluding the browser and loading. The
desktop now exits its speech worker before cleanup. With heavier graphics work:

| Cleanup device | Idle → cleanup graphics | Approximate slowdown | Cleanup request |
|---|---:|---:|---:|
| GPU | 59.3 → 55.4 fps | 7% | 7.78 s |
| NPU | 58.6 → 38.9 fps | 34% | 5.25 s |
| CPU | 59.1 → 53.4 fps | 10% | 7.30 s |

**Decision:** cleanup AUTO tries an available OpenVINO GPU, then CPU if it fails;
explicit device choices remain strict. GPU offered the measured balance of speed,
RAM, and graphics interference. NPU used least CPU but caused most graphics
slowdown; the cause remains unknown. These were synthetic browser workloads.
GPU counters above 100% were discarded, leaving GPU-capacity usage unresolved. [Resource measurements and method](../host-validation/evidence/2026-10-02/cleanup-resource-cost/README.md).

Cached GPU loading was 1.67–3.63 seconds in the matched comparison; first-ever
NPU compilation in the earlier pilot took 169.7 seconds. Each desktop action
starts a new worker; long cleanup reuses its model across blocks. AUTO does not
measure foreground load or impose resource caps. Off skips the cleanup model.

## Audio cuts: fixed 30 seconds, zero overlap

After an initial Yale pilot, three new continuous passages (23:52, 3,583 reference
words) compared zero and one-second overlap twice per model on CPU. Zero overlap
improved all six model/passage comparisons.

| Model | Pooled word error: 1 s → 0 s overlap | Warm batch time: 1 s → 0 s |
|---|---:|---:|
| tiny.en | 12.84% → 8.71% | 66.76 → 53.41 s |
| base.en | 10.41% → 7.51% | 88.46 → 81.11 s |

**Decision:** zero overlap avoids many partial repetitions, but lost eight checked
boundary words that overlap retained. Pause-based cuts had mixed held-out results;
the newer variant worsened base on all three new passages and increased checked
seam deletions from 3 to 13 compared with the earlier variant. Keep fixed cuts
as default and pause variants opt-in. Caption references remain provisional.
[Overlap holdout](../host-validation/evidence/2026-10-01/overlap-holdout/README.md),
[pause holdout](../host-validation/evidence/2026-10-02/pause-refinement/README.md).

## Checkpoint scope

File transcription, selected automatic cleanup, unedited Raw, and separate
formatted study notes are included. Light requests minimal wording changes;
Medium makes more
clarity edits; Summary selects source passages into headings and bullets,
intentionally omitting detail and treating excerpts independently.
A new freeform summary pilot invented details. This checkpoint instead validates
model-selected passage indices and formats the source text itself. A 72-second
lecture produced 101 words of notes from 192 recognition words, preserving source
and cleanup hashes. Summary completeness and accuracy remain unmeasured.
[Checkpoint checks and limits](../host-validation/evidence/2026-10-03/file-cleanup-checkpoint/report.json)
include real CPU/GPU runs, source hashes, and the installed-wheel check.
Microphone capture, hotkeys, insertion, and a current installer are deferred.
[User guide](USER_GUIDE.md), [software checks](../TESTING.md).


## October 3: dependencies and separate formatting

Published `main` at `e26205c` installed into a fresh Windows Python 3.12 environment
with OpenVINO 2026.4.0, GenAI 2026.4.0.0, and PySide6 6.11.2. All 204 existing tests
passed. GitHub CI could not start: repository settings rejected the official
checkout/setup-python actions.

Real CPU/GPU/NPU speech and cleanup paths were exercised on this host. The repeated
72-second CPU speech → GPU cleanup → summary workflow produced identical text to
the earlier checkpoint and preserved source hashes. The short NPU cleanup load
took about 209 seconds, including first compilation. The full device comparison
above used OpenVINO 2026.3; it has not been repeated with 2026.4.

**Decision:** save formatting separately from Raw and AI, with Summary kept as a
separate, intentionally shorter output. Mostly prose uses no model. Mixed and
Mostly structured request layouts from the cleanup model and reuse its loaded
pipeline when chained. The program renders source passages rather than generated
replacement text, verifies complete coverage/order, and falls back to prose on
invalid plans. Tables require explicit comparable source rows; steps require
source step markers. Requests are capped at eight passages after a larger request
pilot omitted passages and fell back to prose.

On the same 72-second transcript, prose formatting took about **0.05 seconds**;
Mixed took **11.88 seconds** over four requests, including model loading; Mostly
structured took **12.96 seconds** with that model already loaded. Mixed accepted
three layouts and fell back on one; Mostly structured accepted two and fell back
on two. Source and cleanup hashes stayed unchanged. Seven of eight additional
short model requests produced valid layouts, including a comparison table and
numbered procedure; one structured comparison returned invalid JSON and became
prose. Layout consistency remains uncertain; headings and grouping need review.
Mostly prose stays the default.

[Dependency, desktop, installed-package, and formatting checks](../host-validation/evidence/2026-10-03/validation-formatting/report.json)
record the inputs, versions, checks, and limits without personal library paths.


## Full class lecture and final cleanup checks

A supplied **47:20 class video** ran through the complete file workflow on the
same host with OpenVINO 2026.4. Browser and other desktop apps stayed open.
Each speech model ran once in a fixed order.

| Stage | Measured time | Worker CPU, mean / peak | Peak private working memory |
|---|---:|---:|---:|
| tiny speech, CPU | 93 s | 21% / 26% | 0.23 GiB |
| base speech, CPU | 146 s | 22% / 28% | 0.28 GiB |
| Final Light cleanup + prose, GPU | 459 s | 10% / 15% | 4.53 GiB |
| Mixed layout on the initial cleanup | 145 s | 11% / 12% | 4.65 GiB |

Speech times include loading and audio preparation. Cleanup includes loading;
Mixed reused its loaded cleanup model. Memory is the sampled peak across worker
processes; GPU/driver allocations are not fully captured. The base workflow took about
**10.1 minutes** in these separate stage runs;
Mostly prose added no model pass and its complete formatting step took less
than 0.1 seconds. Other apps stayed open, but typing and page-loading response
were not measured. GPU counters again exceeded 100% and were unusable.

**Decisions:** keep CPU speech, AUTO cleanup, and Mostly prose. Base improved
several inspected terms and reduced conspicuous repeated text at a cost of
about 52 extra seconds; use it for lectures when the larger download is
acceptable. Without a checked audio reference, the full-lecture error rate
remains unknown. Both models still made recognition errors.

The full run exposed invented sentence endings, an added interpretation/label,
and a lost uncertainty phrase that passed the earlier checks. The final cleanup
prompt and conservative checks cover those observed cases. **9/31 cleanup
blocks retained source text with warnings** in the final run. Cleanup can still
change meaning or retain unclear recognition. Raw stays available. Mixed fell back to prose on **33/78 requests**;
all 45 accepted layouts were paragraphs, so it offered little layout variation
in this lecture despite its added runtime.

Original media and Raw/Balanced hashes were preserved; formatting retained all
cleaned words in order. Raw, AI, and Formatted exports succeeded in text,
Markdown, and JSON. The final software suite passed 233 tests; the rebuilt wheel
passed installed-launcher checks outside the checkout and matched all 25 source
modules. Course text and media remain in ignored local storage, excluded from Git.
[Full lecture measurements and limits](../host-validation/evidence/2026-10-03/full-lecture/report.json).
