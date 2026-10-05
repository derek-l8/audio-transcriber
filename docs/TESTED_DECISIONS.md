# Tests and decisions

These measurements predate the Audio Transcriber rename and Python 3.14 update.

The project began as an attempt to use an NPU for local speech transcription
and cleanup while leaving the computer usable. Tests led to different device
choices: **CPU for speech; GPU with CPU fallback for cleanup**. NPU stays optional.

Measured September 30–October 4, 2026 on one Windows x64 host: Core Ultra 5 335,
Intel integrated graphics, Intel AI Boost NPU, 8 logical processors, 31.51 GiB
usable RAM. Initial runs used OpenVINO 2026.3.0 / GenAI 2026.3.0.0;
October 3–4 runs used 2026.4.0 / 2026.4.0.0. The linked reports contain
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

## October 3: initial file checkpoint

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
At that checkpoint, microphone capture, hotkeys, insertion, and an installer
were deferred. Later dictation and installer checks are linked below.
[User guide](USER_GUIDE.md), [software checks](../TESTING.md).


## October 3: dependencies and separate formatting

The October 3 environment used OpenVINO 2026.4.0, GenAI 2026.4.0.0, and
PySide6 6.11.2.

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
Mostly prose was the default for this comparison.

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

**Decisions from this run:** keep CPU speech and AUTO cleanup. Prose added no
model pass. Base improved
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
Markdown, and JSON. Course text and media remain in ignored local storage, excluded from Git.
[Full lecture measurements and limits](../host-validation/evidence/2026-10-03/full-lecture/report.json).


## Live dictation: latency and idle memory

Dictation reuses CPU speech and GPU-to-CPU cleanup selection. Its worker exits
when each recording finishes, releasing model memory while idle. On a ten-second
clip of a provided speech recording, Off took **2.22 s**. Light cleanup ran twice
per device; the repeat used existing compilation caches:

| Cleanup device | First job | Repeat job |
|---|---:|---:|
| GPU | 19.28 s | 14.47 s |
| CPU | 45.91 s | 53.59 s |
| NPU | 202.50 s | 21.13 s |

These times include conversion, CPU transcription, cleanup setup/generation,
and saving text. NPU's first job spent **190.54 s** in model setup. All six Light
outputs matched. GPU remains the cleanup default with CPU fallback; Off provides
faster dictation when cleanup is unnecessary. The full 266-second file also
completed on CPU: **10.64 s with tiny**, **16.70 s with base**.

These runs used one computer with normal background applications open. WER for
this recording is unmeasured. The
[recording report](../host-validation/evidence/2026-10-03/live-dictation/user-recording-report.json)
contains device timings and insertion checks; the
[initial report](../host-validation/evidence/2026-10-03/live-dictation/report.json)
retains the earlier generated sample and unresolved laptop microphone check.

## Dictation: loaded models and alternative engines

On October 4, three clips (10, 10, and 30 seconds) from the same provided
recording compared fresh workers with workers that kept their models loaded.
Each loaded worker processed the clips three times. Times below cover normalized
audio through CPU tiny transcription and Light cleanup; app startup, recovery
saving, and model checksum checks are excluded. Fresh workers reused compilation
caches. RAM is the worker's working set after its last job.

| Cleanup setup | Fresh worker, 10 s clip | Loaded worker, 10 s clip | Loaded worker, 30 s clip | RAM held | CPU during repeat jobs |
|---|---:|---:|---:|---:|---:|
| Qwen 7B, GPU | 6.79 s | 2.73 s | 6.88 s | 4.77 GiB | 12% |
| Qwen 1.5B, GPU | 3.99 s | 1.15 s | 2.98 s | 1.55 GiB | 15% |
| Qwen 1.5B, CPU | 12.06 s | 2.51 s | 4.66 s | 2.18 GiB | 24% |

These are medians across the relevant clips/calls. Loaded idle CPU was 0–0.1%
over two-second samples. Keeping 7B loaded held about 15% of this computer's
usable RAM. The first job with a new GPU compilation cache took 32.19 s for 7B
and 12.73 s for 1.5B.

The smaller GPU model introduced unsupported interpretations and changed tone
in inspected output. Its CPU run rejected all three versions of one passage
and kept the raw text. The 7B GPU run also retained raw text on two rejected
edits. Repeated GPU cleanup sometimes varied despite identical raw input.
These checks compare edits with the raw text; the recording has no checked
reference for measuring speech accuracy.

For speech alone, loaded OpenVINO tiny INT4 took **0.33 s** on the ten-second
clips and **0.89 s** on the thirty-second clip, holding **0.28 GiB**.
Faster-whisper tiny INT8 with two CPU threads and beam size 1 took **0.49 s**
and **1.09 s**, holding **0.15 GiB**. Beam size 5 took **0.56 s** and **1.44 s**.
Typical worker CPU during repeat jobs was 25% for OpenVINO and 22% for
faster-whisper. Their text differed, so these runs establish no accuracy ranking.
Faster-whisper's file decoder failed with the installed PyAV version; the
comparison used normalized PCM samples for both engines.

The same fixed hardware graphics workload ran twice, with the device order
reversed on the second pass. Its frame rate and the warmed ten-second jobs were:

| Cleanup setup | Graphics before → during jobs | Frame-rate loss | Job time with graphics load |
|---|---:|---:|---:|
| Qwen 7B, GPU | 60.0 → 57.2 fps | 4.6% | 18.36 s |
| Qwen 1.5B, GPU | 59.8 → 58.9 fps | 1.6% | 6.84 s |
| Qwen 1.5B, CPU | 59.6 → 57.2 fps | 4.1% | 4.00 s |

The graphics workload slowed cleanup substantially while losing a few frames
per second itself. Loaded idle workers returned roughly 60 fps. This measures
interference with one graphics workload; it does not give a GPU utilization
percentage or establish responsiveness in other apps.

**Decisions:** retain OpenVINO speech and 7B cleanup. Loaded models offer a
substantial dictation latency reduction, with enough retained RAM to warrant
an explicit option and idle unloading. This benchmark does not change the app's
current per-recording worker behavior. The 1.5B model needs better fidelity
before becoming a default.

[Measurements, model revisions, and method](../host-validation/evidence/2026-10-04/dictation-efficiency/report.json).

## Workflow defaults

File imports now start with Light cleanup and Mostly structured formatting.
Live dictation starts with Medium cleanup and Mostly prose. These defaults
follow the requested lecture and dictation workflows. Performance tables above
retain the settings used in each test. The device policy remains CPU speech
and GPU cleanup with CPU fallback. Existing choices remain
saved, and raw text stays available. The [installed-app checks](../host-validation/evidence/2026-10-04/installer-checkpoint/README.md#defaults-rebuild)
verified both sets of defaults, lecture processing, exports, reinstall, and uninstall.
