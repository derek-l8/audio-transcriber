# Local AI cleanup pilot

Pinned Qwen2.5 7B INT4 was executed through OpenVINO GenAI on explicit CPU,
GPU, and NPU on one Windows host. Each pipeline used a fresh chat history per
block; the GPU/NPU pilots made two distinct sequential calls on one pipeline.
Successful explicit device binding is runtime execution evidence, not independent
hardware utilization or power measurement. The [report](pilot.json) contains
synthetic inputs, outputs, settings, and measured wall times without owner paths.

The final five CPU examples resolved a color correction, resolved Friday to
Monday while keeping a 12 volt measurement, retained 5 versus 50 volts and
negation in lecture mode, honored a literal command, and resolved Tuesday to
Thursday with paragraph/list formatting. These outputs were inspected against
the supplied synthetic source statements. The earlier 1.5B candidate lost a
corrected date without triggering heuristics and was rejected as the default.
This is a small implementation pilot, not representative semantic accuracy.

NPU first use took 173.5 seconds, including 169.7 seconds of loading/compilation.
Its second example took 3.4 seconds. GPU first use took 16.7 seconds including
15.2 seconds loading, and the second example took 1.4 seconds. Other checks were
running during portions of these pilots. Do not use these observations to rank
devices; no repeated, isolated timing or power comparison was performed.

The desktop exercised its actual CLI child and model on CPU, then exported
text, Markdown, JSON, and SRT. Source/raw/Balanced hashes stayed unchanged.
An installed wheel executed real CPU text cleanup from another working directory
containing spaces. Automated tests cover cancellation/failure without replacing
a previous AI result, retained versions, source fallback, UI controls, and exports.
Native Windows Qt rendering was inspected; the frozen bundle/installer has not
been rebuilt with this feature. Private fixtures/screenshots/models remain in
ignored local storage outside OneDrive.
