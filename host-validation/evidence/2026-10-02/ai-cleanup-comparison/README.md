# Matched AI cleanup quality and speed comparison

Qwen2.5 7B INT4, the pinned model and unchanged cleanup-v2 prompt, was run on
explicit CPU, GPU, and NPU through the actual product `LocalCleanupModel` on one
Windows host (Core Ultra 5 335, 8 logical processors). The [machine-readable
report](comparison.json) contains measured times, synthetic inputs/outputs,
checks, warnings, and model/runtime identifiers. Text from the existing public
lecture ASR fixture is replaced with hashes; full review outputs remain ignored.

## Method

- 25 fixed case configurations: 24 synthetic configurations covering technical
  content, quantities, negation, uncertainty, names, emphasis, quotations,
  corrections, grammar, lists, and spoken/literal formatting, plus one 952-character
  existing lecture ASR passage. Four configurations repeat a source under Medium
  rather than Light. These are not 25 independent lectures.
- Two passes per device: CPU/GPU/NPU, then NPU/GPU/CPU. The case order is also
  reversed. One inference worker runs at a time; fresh workers free model/device
  state between passes. Six main workers produce 150 measured requests.
- One unscored identical warmup per worker. Loading and startup/warmup times are
  recorded separately. Existing compilation caches are reused; this is not a
  cold-cache startup benchmark. No downloads occur during inference.
- Greedy decoding, identical weights, prompts, generation limits, source text,
  and block/guard logic. The model and production code were not tuned mid-test.
- Predeclared regex checks evaluate required content and requested formatting.
  Candidate and final (after fallback) are scored separately. Unique outputs and
  cross-device/repeat differences were inspected against the inputs.
- Main case D01 says “move the meeting from Thursday actually Friday,” which is
  ambiguous. It stays in timing totals but is excluded from quality headline
  counts. An unambiguous “schedule ... Thursday actually Friday” follow-up passed
  on every device in both repeats (six further requests), reported separately.
- Windows Balanced power scheme and AC/charging at 100 percent were observed
  before testing. Ordinary OS/application activity and thermals were not controlled.
  The CPU batch varied substantially between repeats; two repeats are insufficient
  for a population estimate or confidence interval.

## Speeds

Warmed request times include generation and the guard check. Batch time is the
sum of the same 25 request times, averaged over two passes; loading/warmup excluded.

| Device | Median request | Mean 25-case batch | Batch repeats | Loading | Startup + warmup |
|---|---:|---:|---:|---:|---:|
| CPU | 3.78 s | 194.05 s | 224.70 / 163.39 s | 12.24 / 9.80 s | 36.39 / 29.93 s |
| GPU | 1.09 s | 49.55 s | 50.26 / 48.85 s | 3.63 / 1.67 s | 5.33 / 3.06 s |
| NPU | 2.99 s | 106.48 s | 106.56 / 106.41 s | 7.34 / 6.62 s | 10.68 / 9.88 s |

GPU was about 3.9 times faster than CPU and 2.1 times faster than NPU by mean
batch time. NPU was about 1.8 times faster than CPU. These conclusions apply to
this text-cleanup model/workload; they do not supersede Whisper transcription
measurements. CPU request times vary with OS/runtime activity and source length.

The desktop currently launches a new worker for each cleanup action, so a
single short cleanup also incurs startup. A long session reuses its pipeline
across blocks. The earlier [initial NPU pilot](../ai-cleanup/README.md) spent
169.7 seconds loading/compiling before caches were available; current cached
startup figures do not represent that first-ever compilation.

Worker process CPU time divided by warmed wall time and 8 logical processors
was **25.6% for CPU, 11.3% for GPU, and 1.0% for NPU**. This is average CPU
capacity consumed by that worker, excluding loading; it is not total system CPU
usage, accelerator utilization, memory consumption, electricity, or a measurement
of responsiveness while doing other work.

## Quality

One ambiguous case is excluded: 24 case configurations x 2 repeats = 48 scored
requests per device. These counts describe the targeted checks, not an accuracy
percentage for arbitrary text.

| Device | All requested checks passed | Final content checks passed | Source fallback | Exact outputs stable across repeats |
|---|---:|---:|---:|---:|
| CPU | 40/48 | 46/48 | 6/48 | 25/25 cases |
| GPU | 42/48 | 46/48 | 4/48 | 22/25 cases |
| NPU | 40/48 | 46/48 | 6/48 | 25/25 cases |

- Clear name/value corrections, grammar, bullet lists, paragraph breaks,
  meaningful “actually/like,” and the tested numeric/negation/uncertainty cases
  passed across devices. The separate unambiguous date follow-up also passed.
- All devices retained an unwanted **literal** marker in an escape-command case.
  This escaped the app guard and accounts for the two final content-check failures
  per device. It is a command-handling defect, not a hallucinated numeric fact.
- All devices converted spoken math into equivalent LaTeX. The digit guard
  rejected the new exponent digits, retaining the raw text. The lexical checks
  therefore must not be interpreted as incorrect mathematics. Cleanup completion
  failed because the fallback retained the filler and lacked final punctuation.
- All devices removed repeated lecture emphasis and one duplicated negation;
  the negation guard retained the source, preserving the words but leaving cleanup
  incomplete. Removing emphasis alone could still escape that count-based guard.
- CPU and NPU omitted a quoted instruction from the lecture test. The size guard
  retained the source. GPU preserved the quotation and completed cleanup in both
  repeats, giving it one additional passing case per repeat.
- CPU and NPU outputs were identical on 24/25 configurations; the remaining
  difference was commas in a Medium lecture paragraph. GPU differed in some
  punctuation, paragraphing, wording, and quotation handling. Three GPU outputs
  changed between repeats, without a clear factual change in those inspected
  variants; even greedy generation is not a guarantee of identical text here.
- In the actual ASR fixture, all devices changed the apparent recognition error
  “micro-revolution” to “microevolution.” That is an inferred repair, not verified
  against audio in this cleanup test. Some awkward ASR sentences remained.

The guards preserve some source content at the cost of incomplete cleanup; they
cannot establish semantic fidelity. This test does not establish broad lecture
accuracy, support for all languages, hardware portability, or Wispr Flow parity.

## Reproduce with synthetic cases

Use the installed inference runtime and explicitly downloaded pinned cleanup
model. Keep all output/cache directories local and outside cloud sync.

```powershell
python host-validation/Compare-AiCleanup.py --cases host-validation/ai-cleanup-cases.json --model-root 'PATH_TO_MODELS' --cache-root 'LOCAL_CACHE_FOLDER' --output 'LOCAL_RESULT_FOLDER'
python host-validation/Compare-AiCleanup.py --cases host-validation/ai-cleanup-followup-cases.json --model-root 'PATH_TO_MODELS' --cache-root 'LOCAL_CACHE_FOLDER' --output 'NEW_FOLLOWUP_FOLDER'
```

The public main fixture has 24 synthetic configurations; the extra real ASR
passage used here remains in ignored storage. Outputs include source text and
should be inspected before sharing. Test outcomes and timings may vary by host.
Product defaults and cleanup code were left unchanged by this comparison.
