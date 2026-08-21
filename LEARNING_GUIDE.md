# Learning guide

Exercises tied to the implementation:

1. Add a VTT exporter beside `export.srt`, then write a timestamp rollover test.
2. Add a schema migration fixture without permitting raw transcript replacement.
3. Extend `_negation_changed` with contractions and demonstrate a golden regression.
4. Add a fake engine failure between raw and cleaned writes and verify recovery.

Interview prompts: Why must `actual_device == requested_device` before a benchmark selects
NPU? Why are raw and cleaned files create-once while session metadata is replaceable? Why
does Windows focus need revalidation immediately before `SendInput`? What deployment risks
would a C# host plus Python service add, and when would those become worthwhile?
