# GPU cleanup load estimate

The local Qwen2.5 7B INT4 cleanup pipeline was held resident on explicit GPU.
The owned worker was sampled through Windows GPU engine and process-memory
counters: idle, about 26 seconds continuous generation (28 calls), three short
cleanups at ten-second intervals, and idle again. A separate one-second PDH
probe repeated continuous generation for 20 seconds (22 calls).

The [measurement](measurement.json) records results without owner paths or PIDs.
Windows busiest-engine activity averaged 91.2% in the first sustained probe and
95.5% in the confirmation. However, some individual samples exceeded 100% even
with one-second cooked counters. These observations support a rough high-load
estimate, not a reliable precise peak percentage or a hardware-capacity claim.
The active counter was the GPU Neural engine; model binding was explicitly GPU.

Loaded idle activity was 0%. Three approximately 0.9-second cleanups ten seconds
apart averaged 6.4% over the sampled burst phase. Phase-edge exclusion and sparse
sampling affect that average; use roughly 5-10% for this particular burst pattern.
More frequent updates or longer text change the duty cycle.

GPU-shared memory remained about 4.3 GiB while idle. The process working set was
about 4.5 GiB, overlapping shared allocations; adding them would double count.
No CPU recognizer or live microphone pipeline was running in this experiment.
Raw text/counter/PID-bearing outputs and probe helpers remain ignored locally.
No energy, rendering contention, or end-to-end live dictation measurement is made.

Windows reports its busiest GPU engine as the summary utilization metric;
see [Microsoft's explanation](https://devblogs.microsoft.com/directx/gpus-in-the-task-manager/).
Engine activity does not identify the fraction of peak arithmetic throughput.
