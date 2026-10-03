# Third-party notices (development inventory)

This file is not yet a final redistribution notice. Direct dependencies currently declared:

- platformdirs 4.3.6 — MIT.
- PySide6 6.8.2.1 — LGPL-3.0/GPL-3.0/commercial; dynamic-library LGPL obligations apply.
- OpenVINO 2026.3.0 and OpenVINO GenAI 2026.3.0.0 — Apache-2.0.
- build, Hatchling, pytest, pytest-cov, Hypothesis, Ruff, and mypy are build/test dependencies;
  verify their locked transitive inventory before release.

NumPy may be installed transitively by OpenVINO; inventory the actual frozen build,
including all native/transitive dependencies, before distributing it. sounddevice
is not used by the current application and is no longer a declared dependency.

PyInstaller 6.22.3 is declared in the optional `bundle` extra. The Windows bundle
has one-host smoke evidence; the Inno Setup recipe has an isolated one-host
install/reinstall/uninstall check. The compiler is a build tool, not bundled.
The `ffmpeg.exe` command-line decoder is external. Qt Multimedia also uses FFmpeg
libraries for playback, and the tested frozen bundle includes `avcodec-61.dll`.
These libraries need their own inventory and notices before redistribution;
see [Qt's FFmpeg attribution](https://doc.qt.io/qt-6.8/qtmultimedia-attribution-ffmpeg.html).
That reference is for the Qt 6.8 documentation line, not proof of the exact
FFmpeg patch version or build configuration inside the pinned PySide6 wheel.
The recipe includes this development inventory and the project MIT license;
it does not establish complete redistribution compliance.
Model and dataset licenses never inherit the MIT license.

## Optional cleanup model

The manifest pins `OpenVINO/Qwen2.5-7B-Instruct-int4-ov` at revision
`51f38f02586876c08ca2a604224da20ea61685b8`, with per-file size/SHA-256 verification.
These are INT4 OpenVINO artifacts derived from Qwen2.5-7B-Instruct, licensed
under Apache-2.0. They are explicitly downloaded, not included in the source
package or frozen bundle. See the [artifact model card](https://huggingface.co/OpenVINO/Qwen2.5-7B-Instruct-int4-ov)
and [original model license](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/blob/main/LICENSE).
