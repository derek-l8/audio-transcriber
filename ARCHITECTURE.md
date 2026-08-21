# Architecture

The selected design is a single packaged Python application with UI-independent core
services and replaceable platform adapters. `DECISIONS.md` contains the comparison.

`SpeechEngine` owns transcription. `OpenVINOWhisperEngine` explicitly compiles for a
requested device; `MockSpeechEngine` makes orchestration deterministic in Linux tests.
`SessionStore` owns ordinary files and atomic/create-once transcript writes. The pipeline
coordinates state transitions without UI dependencies. Cleanup, dictionary, exports,
metrics, and measured device selection are pure modules.

Planned outer adapters are PySide6 multimedia/UI, Win32 global shortcut/focus/insertion,
explicit model acquisition, FFmpeg decoding, and PyInstaller/Inno Setup packaging. These
must depend inward on core protocols. No core operation may silently access the network.

Process isolation was considered but rejected for v1: a Python inference service plus a
native host doubles deployment and introduces IPC recovery without improving OpenVINO
device evidence. Long inference will run on worker threads/processes behind the same
interfaces so the UI event loop remains responsive.
