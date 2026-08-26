# Model evaluation

Status labels: **verified-sandbox**, **implemented-unverified** (harness ready,
awaiting Windows results), **pending**. No invented numbers.

## Approved manifest (verified-sandbox)

Both entries are English-only OpenVINO IR + OpenVINO Tokenizers exports
(Apache-2.0, no remote code, no pickle). Checksums are recorded per file in
`src/npu_scribe/acquisition.py`; the download verifier enforces them.

| Model | Revision | Role | Download size | License |
|---|---|---|---|---|
| `OpenVINO/whisper-tiny.en-int4-ov` | `2c4a4cb35a33f827f324c55f474d9197c586b485` | development-proof | 41.0 MB | Apache-2.0 |
| `OpenVINO/whisper-base.en-int4-ov` | `b0da25f7e43548df7f35fb69fc7609c08242150a` | candidate | 63.8 MB | Apache-2.0 |

tiny.en checksums were recorded from the sandbox feasibility download and
re-verified by a fresh full download through the real acquisition path.
base.en checksums were recorded during manifest authoring from the pinned
revision at `huggingface.co` (only approved host).

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

## Evaluation harness (implemented-unverified)

`npu-scribe evaluate EVALUATION_MANIFEST --model MODEL_ID --device auto`

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
version, and status (`measured` / `awaiting-windows-validation`).

Selection policy (recorded in every report): reject any model with measured
RTF >= 1.0 on the tested device; prefer RTF <= 0.5; among eligible models choose
the lowest WER; no final default until representative results exist. English-only
and multilingual candidates must be compared on identical material; multilingual
checkpoints are forced to transcribe English. Prioritize engineering,
mathematics, and science lecture material with accented speakers represented.

## Still pending

- Real public lecture evaluation runs (owner machine or network-permitted host).
- GPU/NPU benchmark and accuracy evidence.
- Two-hour bounded-memory endurance evidence.
