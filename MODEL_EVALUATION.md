# Model evaluation

No production model has been selected. A feasibility proof used an explicitly
downloaded `OpenVINO/whisper-tiny.en-int4-ov` at revision
`2c4a4cb35a33f827f324c55f474d9197c586b485` (Apache-2.0 model card) with a synthetic
one-second silent PCM WAV. OpenVINO 2026.3.0 enumerated only CPU, compiled the pipeline,
and returned `you` (a silence hallucination, so this is a loading/execution proof—not an
accuracy result). Load was 0.611 s, inference 0.334 s, and total wall time 1.016 s in this
single un-warmed run. The WAV SHA-256 was
`643f8a8dc8bd9c19225afffad2becfec5426180b3749cb208abdf1a6c8354efc`.

The first evaluation candidate is an explicitly
acquired OpenVINO `whisper-base` INT8 export, compared fairly with tiny and small using
identical 16 kHz inputs, warmup, and repetitions. Report model identity/checksum/license,
runtime, requested and actual device, load/first/steady latency, RTF, peak memory, WER/CER,
and timestamp proxy. Separate development and untouched holdout sets are mandatory.

NPU, GPU, accuracy, representative latency, and memory results remain unverified. A local rewrite model
will not be enabled by default until high-risk negation, number, name, uncertainty, quote,
and reversal cases demonstrate acceptable meaning preservation within the model budget.
