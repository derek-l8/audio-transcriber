# Third-party notices

Audio Transcriber source is MIT-licensed. The Windows bundle includes these runtime
components from the build environment:

- Python 3.14.6 — PSF license and notices.
- platformdirs 4.12.2 — MIT.
- PySide6 / Qt for Python and Shiboken 6.11.2 — LGPL-3.0 or the alternative
  licenses supplied by Qt. Qt libraries remain separate, replaceable DLLs.
- OpenVINO 2026.4.0, GenAI and Tokenizers 2026.4.0.0 — Apache-2.0.
- OpenVINO Telemetry 2025.2.0 — Apache-2.0; installed as an upstream dependency.
  This application does not use its telemetry API.
- NumPy 2.5.3 — BSD and included component notices.
- Qt Multimedia's FFmpeg 7.1.5 playback libraries — LGPL-2.1 or later.
  Their reported configuration uses shared libraries, zlib 1.3.1, and does not
  enable GPL or nonfree components.

The bundle's `_internal/licenses/` folder contains Python's license, package
license files and notices, GPL/LGPL texts, and `runtime-inventory.json` with exact
package versions and notice hashes. OpenVINO's native component notices and
NumPy's bundled component licenses are copied from their installed packages.
PyInstaller 6.22.3 and hooks 2026.8 build the app; the
[bootloader license exception](https://pyinstaller.org/en/stable/license.html)
permits distributing the generated application under its own license.
Inno Setup 7.1.0 is a build tool, not an installed runtime dependency.

Binary releases are accompanied by `audio-transcriber-0.1.0-library-sources.zip`, with
pinned Qt/PySide, FFmpeg and zlib sources, upstream build recipes, and
[rebuild instructions](packaging/LIBRARY_BUILD.md). The installer includes those
instructions, the source manifest, and upstream attribution/license files in
`_internal/licenses/`. You may replace the shared libraries with compatible
modified builds and reverse-engineer the app to debug those modifications.
Audio Transcriber makes no local changes to the upstream libraries.

The bundle excludes the unused Qt Virtual Keyboard and PDF plugins and the
software OpenGL renderer. It uses the Widgets interface and native media plugins.
See [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html) and
[FFmpeg's distribution guidance](https://ffmpeg.org/legal.html).

## Separately downloaded files

The `ffmpeg.exe` decoder is selected separately by the user and is not bundled.
Its license depends on the chosen build. Model weights are also downloaded
separately and do not inherit the application's MIT license.

The cleanup manifest pins `OpenVINO/Qwen2.5-7B-Instruct-int4-ov` at revision
`51f38f02586876c08ca2a604224da20ea61685b8`, derived from Qwen2.5-7B-Instruct
under Apache-2.0. See the [artifact model card](https://huggingface.co/OpenVINO/Qwen2.5-7B-Instruct-int4-ov)
and [original model license](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/blob/main/LICENSE).
