# Real-lecture device check — 2026-09-30

The same four MIT OpenCourseWare clips used in the [lecture pilot](../lecture-evaluation/README.md)
(461.77 seconds total) were evaluated with explicit CPU, GPU, and NPU requests
on one Intel Core Ultra 5 335 Windows host. OpenVINO enumerated `CPU` (Intel Core
Ultra 5 335), `GPU` (Intel Graphics iGPU), and `NPU` (Intel AI Boost). The pinned
tiny.en and base.en INT4 OpenVINO models used the product's 30-second batch
chunks with 1-second overlap. OpenVINO was 2026.3.0 and openvino-genai was
2026.3.0.0. Each cell below is one run of all four clips, done sequentially.

| Model | Requested and reported device | Mean clip WER | Recorded chunk seconds | Aggregate RTF |
|---|---|---:|---:|---:|
| tiny.en | CPU | 0.1346 | 20.075 | 0.0435 |
| tiny.en | GPU | 0.1323 | 56.806 | 0.1230 |
| tiny.en | NPU, refreshed pipeline | 0.1290 | 194.664 | 0.4216 |
| base.en | CPU | 0.1335 | 16.620 | 0.0360 |
| base.en | GPU | 0.1410 | 31.280 | 0.0677 |
| base.en | NPU, refreshed pipeline | 0.1501 | 477.490 | 1.0340 |

All 24 final cases report `measured`. Their saved sessions reached `ready` with
zero reported fallback events. The base NPU run had RTF above 1.0 on the
Op-Amps and Circuit Abstraction clips. Recorded chunk seconds include first-use
pipeline loading. NPU also reloads the pipeline for **every chunk** after the
bug described below, whereas CPU/GPU reuse it within a clip. These one-run
timings show the cost of the currently correct path on this host, not a stable
hardware speed comparison. Published captions have not been checked against
the audio, so WER remains caption-relative.

The initial tiny NPU batch reused a `WhisperPipeline` across chunks. It produced
only 87–102 words per roughly two-minute clip and mean caption-relative WER
0.7540, despite all cases reporting success. A direct reproduction transcribed
the first 30-second window correctly, then returned only three stale words for
the next window on the same NPU pipeline. Constructing a fresh pipeline for
that next window returned 89 words of the correct lecture content, close to
the CPU output. The adapter
now constructs a fresh NPU pipeline for each chunk; the corrected four-clip
tiny NPU result is above. The [original faulty report](tiny-npu-stale-pipeline.report.json)
is retained as diagnostic evidence, separate from the six final reports.

The application's `actual_device` field follows a successful generation on
the requested device. It is not an independent query of where every operation
ran. The tests establish successful explicit runtime binding and transcript
completeness on this host. They do not prove physical NPU utilization, energy
efficiency, broad Windows compatibility, or gold accuracy. The source audio,
captions, and text-bearing manifest remain outside Git; these reports contain
no media, transcript text, or private paths.
