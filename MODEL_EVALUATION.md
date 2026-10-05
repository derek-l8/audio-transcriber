# Model evaluation

The pause-v2 refinement was frozen before a new three-lecture comparison
(21:14 audio, 36 CPU sessions). Fixed/v1/v2 pooled WER: tiny
13.40%/12.90%/12.67%; base 11.49%/8.98%/9.77%. V2 worsens base relative to
v1 on every new passage and raises base seam-deleted words from 3 to 13,
versus 7 with fixed cuts. Keep both pause variants experimental and fixed
zero-overlap default. Published references remain provisional; the regression
inspection does not isolate endpoint acoustics from decoder context.
See [refinement, sources, and independent comparison](host-validation/evidence/2026-10-02/pause-refinement/README.md).

The local pause-boundary experiment on all six Yale passages completed 48 CPU
sessions (two repeats of both conditions for each model/passage). Fixed to
pause-v1 pooled ASCII-normalized WER: tiny 9.68% to 8.71%; base 8.10% to 7.45%.
Aligned seam-deletion word counts fell from 13 to 2 and 23 to 8, respectively.
Nine of 12 passage/model comparisons improved, with three regressions and seven
new seam-deleted reference words that fixed output retained. Pause-v1 remains
opt-in. These published references were not independently audio-checked.
See [results, runtime, implementation, and limits](host-validation/evidence/2026-10-01/pause-pilot/README.md).

Status labels: **verified-sandbox**, **verified-windows-one-host**,
**implemented-unverified**, **pending**. No invented numbers.

## Approved manifest (verified-sandbox)

The two speech-model entries below are English-only OpenVINO IR + OpenVINO Tokenizers exports
(Apache-2.0, no remote code, no pickle). Checksums are recorded per file in
`src/audio_transcriber/acquisition.py`; the download verifier enforces them.

| Model | Revision | Role | Download size | License |
|---|---|---|---|---|
| `OpenVINO/whisper-tiny.en-int4-ov` | `2c4a4cb35a33f827f324c55f474d9197c586b485` | development-proof | 41.0 MB | Apache-2.0 |
| `OpenVINO/whisper-base.en-int4-ov` | `b0da25f7e43548df7f35fb69fc7609c08242150a` | candidate | 63.8 MB | Apache-2.0 |

tiny.en checksums were recorded from the sandbox feasibility download and
re-verified by a fresh full download through the real acquisition path.
base.en checksums were recorded during manifest authoring from the pinned
revision at `huggingface.co` (only approved host). The separate text-cleanup
model and its comparisons are described in [AI cleanup validation](TESTING.md#ai-cleanup-validation).

## Sandbox measurements (verified-sandbox, CPU only)

Sandbox: Linux container, Python 3.11.2, OpenVINO 2026.3.0 / openvino-genai
2026.3.0.0, CPU device only (no GPU/NPU enumerated).

- Pinned tiny.en loaded via `WhisperPipeline(dir, "CPU")`: load ≈ 0.44 s
  (single un-warmed run).
- Real end-to-end batch run on a synthetic 95 s mono WAV, 30 s chunks with 1 s
  overlap: 4 chunks completed, total inference 1.36–1.73 s across runs,
  RTF ≈ 0.014–0.018 against the 95 s source, peak RSS < ~300 MB for the whole
  process. This is a speed/loading proof on synthetic audio — **not** an
  accuracy result and not representative lecture content.
- Interruption after chunk 1 then explicit resume produced segment-identical
  raw output to the uninterrupted run.

## Windows runtime smoke (verified-windows-one-host)

The pinned tiny.en model constructed a `WhisperPipeline` and generated from
synthetic silence with explicit CPU, GPU, and NPU requests on one Windows host
using OpenVINO 2026.3.0 / openvino-genai 2026.3.0.0. Each session reached
ready with no reported fallback. The application's `actual_device` field is
set from the requested device after successful construction and generation;
it is not an independent query of internal hardware execution. This is a
runtime binding check, not an accuracy or NPU performance comparison. See
`host-validation/evidence/2026-09-30/device-smoke.json`.

## Evaluation harness (verified-windows-one-host)

`audio-transcriber evaluate EVALUATION_MANIFEST --model MODEL_ID --device auto`

The CLI evaluates through the same chunked batch path as transcription. It has
been run on the Windows host with MIT, AMI, TED-LIUM, and NPTEL material.
It reuses a loaded engine within a run, records the resolved requested device,
and returns a nonzero exit code when any case fails. A single-model report
does not make a model selection; `select_model` requires at least two models
on identical measured cases and one device.

The manifest is JSON, schema version 1:

```json
{
  "schema_version": 1,
  "name": "engineering-lecture-set",
  "cases": [
    {
      "id": "lecture-01",
      "audio_url": "https://official-source.example/lecture.wav",
      "audio_sha256": "<64 hex>",
      "expected_size_bytes": 123456789,
      "license": "CC-BY-4.0 or equivalent permitted use",
      "official_source": "https://...",
      "reference_text": "...",
      "reference_provenance": "official transcript, lightly normalized",
      "preparation": "decode to mono 16 kHz; strip speaker labels",
      "audio_seconds": 3600
    }
  ]
}
```

Media is fetched only by this explicit command, verified against checksum and
size, cached under `<data>/evaluation/media`, never bundled in Git. The report
(JSON + Markdown under `<data>/evaluation/reports`) records per case: WER, CER,
RTF, load time, inference time, peak memory, requested vs actual device, runtime
version, and status (`measured` / `failed`). On Windows, per-case peak memory
is unmeasured (`null`); the separate host harness samples process-tree memory.
The current WER/CER compare casefolded words/characters without stripping
punctuation or normalizing numbers.

Selection policy (recorded in every report): reject any model with measured
RTF >= 1.0 on any matched case; prefer models with RTF <= 0.5 on every case;
among eligible models choose the lowest mean case WER. No final default follows
until reference quality and coverage are sufficient. English-only
and multilingual candidates must be compared on identical material; multilingual
checkpoints are forced to transcribe English. Prioritize engineering,
mathematics, and science lecture material with accented speakers represented.

## Two-hour synthetic CPU endurance (verified-windows-one-host)

Two continuous two-hour synthetic CPU passes completed with preserved source
and transcript layers. The [memory series](host-validation/evidence/2026-09-30/two-hour-endurance/README.md)
showed no sustained post-warmup growth on this host; shorter spikes and
real-lecture endurance remain unmeasured.

## Human-reference pilots (verified-windows-one-host)

Four clips from two AMI held-out meetings (8 minutes) and three technical
TED-LIUM dev/test talks (15.23 minutes) were evaluated on CPU with both
candidate models. These corpora provide human-produced reference transcripts,
unlike the earlier MIT caption-relative check. With punctuation-normalized
scoring, pooled WER was 38.10% (`tiny.en`) versus 28.05% (`base.en`) on AMI,
and 14.55% versus 12.35% on TED-LIUM. All 14 case runs completed with zero
reported fallbacks. The talk set is composed of concatenated utterances, and
AMI is multi-speaker meeting speech; neither substitutes for uninterrupted
engineering lectures. See the [numeric evidence and provenance](host-validation/evidence/2026-09-30/manual-reference-pilots/README.md).

## Continuous classroom lecture pilot (verified-windows-one-host)

Three passages from three [Open Yale Courses lectures](host-validation/evidence/2026-10-01/yale-continuous-pilot/README.md)
provide 25:14 of continuous physics, astronomy, and chemistry speech. Against
Yale's published chapter transcripts, pooled punctuation-normalized CPU WER
was 11.77% for tiny.en and 10.49% for base.en over 4,145 reference words. All
six case runs completed without reported fallback. Base had fewer word edits
on two passages, tiny on one. The Yale transcripts are official but were not
independently audited by listening; one chemistry chapter timestamp disagreed
with its MP3 and required an ASR-assisted boundary. These are provisional
transcript-relative scores, not verified gold WER.

A matched 0-second-overlap CPU pass reduced pooled WER to 10.52% tiny.en and
8.61% base.en, improving all six case results. The prior 1-second merger
left repeated words at seams and dropped no whole segments. The application
now defaults to zero overlap for 30-second chunks; positive overlap remains
an explicit option. This is a three-passage transcript-relative comparison,
not an audio-audited general accuracy guarantee. See the [A/B counts](host-validation/evidence/2026-10-01/yale-continuous-pilot/README.md#chunk-overlap-comparison).

A [held-out overlap comparison](host-validation/evidence/2026-10-01/overlap-holdout/README.md)
then used three new Yale lecturers and subjects (23:52, 3,583 reference words).
Both models ran each 0/1-second condition twice in reversed order, producing
24 ready CPU sessions with no reported fallback and identical repeated text.
Pooled WER fell from 12.84% to 8.71% for tiny and from 10.41% to 7.51% for
base; all six case comparisons improved. Warm batch wall totals fell from
66.76 to 53.41 seconds for tiny and 88.46 to 81.11 for base, using summed
case medians. Zero overlap still omitted eight single reference words at
seams that the 1-second outputs retained. Overall base deletions rose by two,
while insertions fell by 105. The current zero-overlap default is retained;
boundary handling and audio-checked gold WER remain incomplete. All sources
are still Yale; two chapters required ASR-assisted boundary alignment before
measurement. One metadata-save attempt failed before inference and the final
two measurements completed after restarting the harness.

An [OpenVINO NPU state issue](https://github.com/openvinotoolkit/openvino/issues/37937)
matches the stale reuse symptom seen on this host with OpenVINO 2026.3.0.
The current rebuild-per-chunk workaround remains. The installed Python API
has no public state-reset method, and no safe local reuse change was applied.
The application's current cached `auto` device decision is CPU for both
models on this host; it uses a one-second silence benchmark, not a continuous
lecture workload.

## Still pending

- A larger, diverse set of uninterrupted engineering/science lectures with
  independently checked word-for-word references. The three-passage Yale set
  adds continuous classroom speech but does not resolve reference certainty.
  The four-clip MIT OCW pilot
  in `host-validation/evidence/2026-09-30/lecture-evaluation/` still measures
  caption-relative error and cannot establish gold lecture accuracy. A
  [100-clip NPTEL pilot](host-validation/evidence/2026-09-30/lecture-gold-pilot/README.md)
  now adds published human-annotated technical lecture excerpts: pooled
  punctuation-normalized CPU WER is 24.09% for tiny.en and 19.75% for base.en.
  These are isolated 5–16 s clips, and individual references have not been
  audited by listening.
- More repeated GPU/NPU performance measurements on longer continuous
  lectures. The [four-clip device comparison](host-validation/evidence/2026-09-30/device-lecture-evaluation/README.md)
  now has a [matched repeat](host-validation/evidence/2026-09-30/lecture-gold-pilot/README.md)
  on one clip. Both base.en NPU runs exceeded real time on that clip. On this
  runtime, NPU Whisper pipelines must be refreshed between chunks to avoid
  stale text. Device labels are based on successful requested-device
  generation, not independent hardware counters.

## Windows host evidence summary


On one Intel Core Ultra 5 335 host, the pinned tiny.en model completed a
synthetic-silence transcription with explicit CPU, GPU, and NPU binding and no
reported fallback. The application records the requested OpenVINO device after
successful pipeline construction and generation; it does not independently
inspect internal hardware execution. A synthetic one-hour WAV completed on CPU
in 125 chunks after a separate interruption/resume check. Sampled peak
process-tree working set was 1211.8 MB (10-second sampling). A real FFmpeg
binary also decoded synthetic MP3, M4A, and MP4 inputs for successful CPU runs.
See [device smoke](host-validation/evidence/2026-09-30/device-smoke.json) and
the [initial one-hour endurance](host-validation/evidence/2026-09-30/endurance.json).

Four public MIT OCW lecture clips were compared with tiny and base on CPU,
GPU, and NPU through the batch path. Reusing a Whisper pipeline across NPU
chunks produced truncated transcripts on this host; the adapter now refreshes
the NPU pipeline for each chunk. That restores transcript completeness but
adds substantial load time. The published captions have not been checked
against audio; results are [provisional](host-validation/evidence/2026-09-30/device-lecture-evaluation/README.md).

Two continuous 7,200-second synthetic CPU inputs subsequently completed in
249 chunks each. Process-tree samples stayed near 390 MB after warmup in those
runs; an earlier one-hour pass had a higher sampled peak, so a stable memory
ceiling is not claimed. See the [two-hour evidence](host-validation/evidence/2026-09-30/two-hour-endurance/README.md).

Human-reference pilots used held-out AMI meetings and three technical TED-LIUM
talks. `base.en` had lower punctuation-normalized WER on every case, though
these sources do not yet establish representative uninterrupted lecture
accuracy. See the [local pilot evidence](host-validation/evidence/2026-09-30/manual-reference-pilots/README.md).

The default zero-overlap chunking was compared with one second of overlap on
three new Yale classroom passages. All six model/passage results improved,
and 24 completed CPU runs supplied repeated accuracy and timing checks.
Zero overlap still omitted some reference words at seams; see the
[held-out comparison and limits](host-validation/evidence/2026-10-01/overlap-holdout/README.md).
