# Human-reference accuracy pilots (Windows, 2026-09-30)

Two candidate OpenVINO Whisper models were evaluated on the same clips on CPU.
All 14 model/case runs completed on the requested CPU with zero reported
fallbacks. The four AMI clips total 480 seconds; the three TED-LIUM talks total
913.74 seconds. These are local, noncommercial checks, not a product default.

| Corpus | `tiny.en` pooled normalized WER | `base.en` pooled normalized WER | `tiny.en` inference RTF | `base.en` inference RTF |
| --- | ---: | ---: | ---: | ---: |
| AMI test meetings, 2 meetings/4 clips | 38.10% | 28.05% | 0.0247 | 0.0359 |
| TED-LIUM dev/test talks, 3 speakers/3 talks | 14.55% | 12.35% | 0.0223 | 0.0334 |

Pooled WER is total word edits divided by total reference words. The
punctuation-normalized scorer casefolds text and retains ASCII letters,
digits, and internal apostrophes. It does not normalize number words,
contractions, or disfluencies. See [`ami.json`](ami.json) and
[`tedlium.json`](tedlium.json) for per-case counts, WER, device, and timing.
The application's current strict WER includes punctuation; its original
reports are in `*.strict.json`. Inference RTF excludes model loading, media
preparation, and other end-to-end overhead.

## Sources and preparation

- [AMI download](https://groups.inf.ed.ac.uk/ami/download/): manual annotations
  v1.6.2 and `ES2004a`, `ES2014a` headset mixes. AMI describes a second
  human transcription pass. Both meetings are in its scenario-only held-out
  evaluation partition. Four 120-second clips cover 720–960 seconds in each
  meeting; references merge all four speakers' word annotations. License:
  CC BY 4.0. Source SHA-256: annotations
  `b56e5babb2496b8795deeeda7e71178d7fbc9963f94276cf2a3f4b56ebbc9f9d`;
  `ES2004a` audio
  `3e2560b19bee6952c7c7ce041b0f1ea8a7ea9468044c4eea79d2a2c67e24ab0f`;
  `ES2014a` audio
  `9d29e308566b8c7be4c328f4a2998e371e5f506384f111042ec91b465f7f792c`.
  Prepared with `host-validation/Prepare-AmiPilot.py`.
- [TED-LIUM long-form](https://huggingface.co/datasets/distil-whisper/tedlium-long-form)
  revision `ea3a78479fb5337761f359abcd4e883d2d6e3c5b`: validation talks
  by Blaise Agüera y Arcas and Brian Cox, and a test talk by Gary Flake.
  The dataset maintainer concatenated TED-LIUM 3 manually transcribed
  utterances to form each talk, so these recordings are not uninterrupted
  original talk audio. License: CC BY-NC-ND 3.0. Downloaded WAV SHA-256:
  Blaise `e6caebd92860f1675d92a373a56c1402fde96491a310cd90cf2996355a142602`,
  Brian `057cb07096a11bf7c091313312b5a1046aea15e7462662e2ec8d35466069ccc4`,
  Gary `b8cb8f81de8eecb106d072fb26bd87e749fd9fcd28e5cc06949ddb2c542eff3c`.
  Prepared with `host-validation/Prepare-TedliumPilot.py`.

Raw media, text-bearing manifests, and transcript outputs are under the ignored
`.scratch/ami/`, `.scratch/tedlium/` directories and the per-user app data
directory; no corpus audio or reference text is included here.

## Interpretation

`base.en` had lower normalized WER on every case in both pilots, with higher
inference RTF; both models were well below RTF 0.5 in these CPU runs. AMI is
meeting speech with overlap and backchannels, so its scores should not be
compared directly with TED-LIUM. TED-LIUM's concatenated utterances remove
natural pauses and do not test continuous lecture recording. The four MIT OCW
clips are closer to the intended lecture input but still use unverified
captions. A final default requires broader lecture speech with independently
checked references and repeated device performance measurements.
