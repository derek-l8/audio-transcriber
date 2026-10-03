# Tests and decisions

The project began as an attempt to use an NPU for local speech transcription
and cleanup while leaving the computer usable. Tests led to different device
choices: **CPU for speech; GPU with CPU fallback for cleanup**. NPU stays optional.

Measured September 30–October 2, 2026 on one Windows x64 host: Core Ultra 5 335,
Intel integrated graphics, Intel AI Boost NPU, 8 logical processors, 31.51 GiB
usable RAM. OpenVINO 2026.3.0 / GenAI 2026.3.0.0. The linked reports contain
methods, pinned models, and numerical results. These are one-host observations,
not universal hardware rankings, energy measurements, or resource guarantees.

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
Published human annotations were not independently checked word by word, and
short clips do not establish full-lecture accuracy.
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
text. This makes base on NPU slower than real time here; it does not prove every
NPU or speech model is slower. Explicit runtime binding succeeded on all devices,
but the reported device is not an independent hardware-utilization query.
[Repeat results](../host-validation/evidence/2026-09-30/lecture-gold-pilot/README.md#matched-lecture-device-repeat),
[four-clip check and NPU defect](../host-validation/evidence/2026-09-30/device-lecture-evaluation/README.md).

## Cleanup: quality, speed, and resource cost

An initial 1.5B model lost a corrected date without triggering the checks. The
chosen Qwen2.5 7B INT4 model handled targeted pilot examples better, at about
4.5 GB of downloads and several GiB of RAM. This was a small candidate check,
not a controlled model-size accuracy study. [Pilot](../host-validation/evidence/2026-10-02/ai-cleanup/README.md).

The 7B model ran 25 matched configurations twice per device. One ambiguous case
was excluded from quality counts. Warmed timing excludes loading and warmup.

| Device | Median request | Mean 25-request batch | All targeted checks passed | Final content checks passed |
|---|---:|---:|---:|---:|
| CPU | 3.78 s | 194.05 s | 40/48 | 46/48 |
| GPU | 1.09 s | 49.55 s | 42/48 | 46/48 |
| NPU | 2.99 s | 106.48 s | 40/48 | 46/48 |

GPU was faster with no observed loss on these final-content checks. These counts
are not general accuracy percentages. Literal commands failed on all devices;
some outputs retained source text after warnings instead of completing cleanup.
[Inputs, outputs, startup times, and limitations](../host-validation/evidence/2026-10-02/ai-cleanup-comparison/README.md).

A separate fixed short request ran alongside moderate hardware graphics activity:

| Cleanup device | Warmed request | Worker CPU capacity used | Resident worker RAM |
|---|---:|---:|---:|
| GPU | 1.14 s | 10.1% | 4.67 GiB |
| NPU | 3.06 s | 0.96% | 5.46 GiB |
| CPU | 2.64 s | 27.9% | 8.48 GiB |

CPU is the worker's share of the whole CPU, not total system usage. RAM includes
the same resident CPU speech pipeline plus cleanup, excluding the browser and
loading. The desktop now exits the speech worker before cleanup, so this table
is not its exact peak. With a heavier fixed graphics workload:

| Cleanup device | Idle → cleanup graphics | Approximate slowdown | Cleanup request |
|---|---:|---:|---:|
| GPU | 59.3 → 55.4 fps | 7% | 7.78 s |
| NPU | 58.6 → 38.9 fps | 34% | 5.25 s |
| CPU | 59.1 → 53.4 fps | 10% | 7.30 s |

**Decision:** cleanup AUTO tries an available OpenVINO GPU, then CPU if it fails;
explicit device choices remain strict. GPU offered the measured balance of speed,
RAM, and graphics interference. NPU used least CPU but caused most graphics
slowdown; the cause was not isolated. These synthetic browser tests do not prove
responsiveness in games, editing, page loading, or typing. Invalid Windows GPU
Neural counters above 100% were excluded; no exact GPU-capacity percentage is
claimed. [Resource measurements and method](../host-validation/evidence/2026-10-02/cleanup-resource-cost/README.md).

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
formatted study notes are included. Light keeps wording; Medium makes more
clarity edits; Summary selects source passages into headings and bullets,
intentionally omitting detail and treating excerpts independently.
A new freeform summary pilot invented details. This checkpoint instead validates
model-selected passage indices and formats the source text itself. A 72-second
lecture produced 101 words of notes from 192 recognition words, preserving source
and cleanup hashes. This is execution evidence, not summary completeness or
accuracy validation; the new prompt is not covered by the device quality counts above.
[Checkpoint checks and limits](../host-validation/evidence/2026-10-03/file-cleanup-checkpoint/report.json)
include real CPU/GPU runs, source hashes, and the installed-wheel check.
Microphone capture, hotkeys, insertion, and a current installer are deferred.
[User guide](USER_GUIDE.md), [software checks](../TESTING.md).
