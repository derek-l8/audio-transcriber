# NPTEL lecture-clip reference pilot and device repeat

## Human-annotated reference check

The [AI4Bharat NPTEL2020 Pure Set](https://github.com/AI4Bharat/NPTEL2020-Indian-English-Speech-Dataset)
provides a 1,000-clip sample that its authors report manually annotating.
`Prepare-NptelPilot.py` pinned the v0.1 archive by SHA-256
(`cad8b68cce78adb4af2b432a2112d43c4c4425b0762564db20a03c3263bc051e`)
and selected 100 clips from 100 distinct lecture videos. Selection used an
explicit Creative Commons Attribution license in the source metadata, 5–16 s
duration, at least eight reference words, and technical terms in the title or
description. The clips total 838.42 s and 1,889 scored reference words. The
sample is deterministic but metadata filtering does not verify every subject
classification or every reference word by listening.

Both pinned OpenVINO models ran the same 100 clips on one Windows host with an
explicit CPU request. All 200 case runs completed on reported CPU with no
reported fallback. The application uses 30 s chunks with 1 s overlap; every
selected clip fit in one chunk.

| Model | Word edits / reference words | Pooled normalized WER | Mean clip WER | Total recorded chunk seconds / audio seconds |
| --- | ---: | ---: | ---: | ---: |
| `tiny.en` | 455 / 1,889 | 24.09% | 24.82% | 0.1355 |
| `base.en` | 373 / 1,889 | 19.75% | 18.64% | 0.1803 |

Pooled WER is total word edits divided by total reference words. The separate
scorer casefolds, ignores punctuation, and retains digits and internal
apostrophes; it does not normalize spoken numbers or correct the published
reference. On the 100 paired clips, base had lower WER on 45, tiny on 24, and
they tied on 31. Base had 5 clips above 50% WER; tiny had 11. One base output
collapsed to two words while tiny captured most of that clip. Another
reference appears to omit spoken words in an equation, so the scores are
best treated as corpus-relative measurements. The references are published
human annotations, not independently audited by us clip by clip.

The 100 clips come from many videos but are short isolated excerpts. They do
not establish accuracy on uninterrupted hour-long lectures, sustained device
performance, or broader accents and subjects. The observed CPU RTF includes
model construction within each case's first chunk, but excludes application
startup, acquisition, and export. See [`nptel.json`](nptel.json) for per-case
numeric scores and [`tiny.strict.json`](tiny.strict.json) and
[`base.strict.json`](base.strict.json) for the application's original reports.
The latter use punctuation-sensitive WER. Audio, text-bearing manifests, and
transcripts stay in ignored local directories outside this evidence folder.

## Matched lecture device repeat

The 118.76 s MIT OCW Op-Amps lecture clip from the earlier four-clip device
check was repeated once with each model and explicit CPU, GPU, and NPU
requests. These are two runs per model/device on one host, separated in time;
they are not a controlled thermal or power experiment. All six repeat cases
completed on their reported requested device with zero reported fallback.

| Model | CPU RTF, initial / repeat | GPU RTF, initial / repeat | NPU RTF, initial / repeat |
| --- | ---: | ---: | ---: |
| `tiny.en` | 0.0509 / 0.0206 | 0.1273 / 0.1135 | 0.4712 / 0.6255 |
| `base.en` | 0.0330 / 0.0320 | 0.0583 / 0.1174 | 1.1788 / 1.5591 |

The current NPU path rebuilds its Whisper pipeline for each chunk to prevent
stale truncated text observed when a pipeline was reused. Both base NPU runs
took longer than the clip's duration, while both models were below real time
on CPU and GPU. Timing variation is material even across these two runs. The
application's device field records successful explicit generation on the
requested OpenVINO device, not independent hardware utilization. See
[`device-repeat.json`](device-repeat.json) for paired seconds and RTF, and the
[initial device report](../device-lecture-evaluation/README.md) for runtime
details. The MIT captions remain unaudited; this repeat is a timing check.

## Reproduce

Prepare the locally downloaded pinned Pure Set archive with
`host-validation/Prepare-NptelPilot.py`, run `npu_scribe evaluate` separately
for each model using the generated manifest, then run
`host-validation/Score-ManualPilot.py` on the manifest and application data
directory. The source archive and text-bearing manifest are intentionally
ignored by Git. `host-validation/Summarize-DeviceRepeats.py` compares the six
single-clip repeat reports in the app data directory with the earlier device
reports in this repository.
