# Cleanup speed and resource cost on one Windows host

Measured October 2, 2026, using the actual project engines: Whisper tiny.en on
CPU and pinned Qwen2.5 7B INT4 cleanup on each device. The host had a Core Ultra
5 335, eight logical processors, and 31.51 GiB usable physical RAM.
[Measurements and limits](measurement.json) contain the numerical results.

## Moderate graphics activity

A separate hardware accelerated browser workload stayed near 60 frames per
second with all three cleanup devices.

| Cleanup device | Median short request | Worker CPU during continuous cleanup | Resident worker RAM |
|---|---:|---:|---:|
| GPU | 1.14 s | 10.1% | 4.67 GiB |
| NPU | 3.06 s | 0.96% | 5.46 GiB |
| CPU | 2.64 s | 27.9% | 8.48 GiB |

RAM includes the same resident CPU speech pipeline plus the cleanup model.
The table excludes loading and the separate browser. A new desktop cleanup
action starts a new worker and also pays loading costs. CPU percentages refer
to the whole CPU's capacity. Shared accelerator allocations overlap the full
working set; do not add them to this RAM figure.

## Heavier graphics activity

The fixed, memory intensive graphics workload was measured with each model
loaded but idle, then during two continuous cleanup windows.

| Cleanup device | Idle graphics | Graphics during cleanup | Median cleanup request |
|---|---:|---:|---:|
| GPU | 59.3 fps | 55.4 fps | 7.78 s |
| NPU | 58.6 fps | 38.9 fps | 5.25 s |
| CPU | 59.1 fps | 53.4 fps | 7.30 s |

GPU offered the best overall balance for ordinary use in this comparison.
NPU minimized CPU use but did not isolate the heavier graphics workload.
The precise cause of interference was not measured. Deferring cleanup gives
the foreground workload more headroom than any simultaneous configuration.

## Method and limits

- Same fixed short dictation sentence, model weights, cleanup-v2 prompt, and
  greedy generation across devices; existing compilation caches reused.
- One fresh inference worker per device and graphics workload, with idle
  windows bracketing two sustained cleanup windows and three spaced requests.
  Moderate order: GPU/NPU/CPU; heavier order: NPU/GPU/CPU.
- The independent browser used verified Intel Direct3D11 hardware rendering,
  a 1280x720 canvas, animated DOM cards, and per-frame GPU readback to wait for
  rendering completion. The moderate shader used arithmetic; the heavier
  shader sampled a 64 MiB texture. Settings stayed fixed within each comparison.
- These are synthetic hardware graphics tests, without physical display,
  gaming, video-editing, network page-load, or human input-latency measurements.
  The 60 fps ceiling hides smaller differences. Background apps and thermals
  were uncontrolled; results do not establish other machines' behavior.
- Windows GPU Neural counters returned impossible values above 100%.
  They are excluded from exact capacity claims. Windows GPU-named counters
  also expose NPU allocations; these are not graphics-GPU execution.
- The heavier comparison had only four to six sustained requests per device.
  Use the [larger matched comparison](../ai-cleanup-comparison/README.md) for
  varied-input throughput and targeted quality checks. This one sentence is
  not an accuracy study or a live dictation benchmark.
- Six inference workers and their browser drivers completed and exited.
  Detailed local frames/logs remain outside the public source tree; no
  personal recordings, transcripts, machine paths, or assistant tooling are
  included here.
