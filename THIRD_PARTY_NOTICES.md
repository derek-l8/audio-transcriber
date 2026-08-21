# Third-party notices (development inventory)

This file is not yet a final redistribution notice. Direct dependencies currently declared:

- platformdirs 4.3.6 — MIT.
- PySide6 6.8.2.1 — LGPL-3.0/GPL-3.0/commercial; dynamic-library LGPL obligations apply.
- NumPy 2.2.3 — BSD-3-Clause.
- sounddevice 0.5.1 — MIT; PortAudio has an MIT-style license.
- OpenVINO 2026.3.0 and OpenVINO GenAI 2026.3.0.0 — Apache-2.0.
- Hatchling, pytest, pytest-cov, Hypothesis, Ruff, and mypy are build/test dependencies;
  verify their locked transitive inventory before release.

PyInstaller and Inno Setup are planned build tools, not yet declared. FFmpeg is planned for
media decoding; a specific build, configuration, checksum, and LGPL/GPL implications must
be chosen before redistribution. Model and dataset licenses never inherit the MIT license.
