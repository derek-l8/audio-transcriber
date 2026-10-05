# Architecture decisions

For measured speech, cleanup, device, and audio-cut choices, see
[Tests and decisions](docs/TESTED_DECISIONS.md).

## One Python application

Audio Transcriber uses Python 3.14, PySide6 for the desktop interface and
microphone capture, and OpenVINO GenAI for speech and text models. The desktop
and CLI share transcription, cleanup, formatting, and storage code. The desktop
runs inference in a separate worker process so the interface can stay responsive
and model memory is released when a job ends.

C# with a Python service and Tauri with an inference sidecar were considered,
but would add communication between processes and another runtime to maintain.
C++/Qt would require more native implementation work. These were architecture
options considered during planning; the performance comparisons use the
implemented Python application.

Windows dictation uses configurable toggle or hold shortcuts and Unicode input.
It saves a recoverable copy before checking the target field and inserting text.
Focus changes or an unsupported field leave the text available to copy manually.

## Separate transcript versions

Preserve the imported audio and original recognition text. Deterministic cleanup,
AI cleanup, manual edits, formatting, and summaries have separate versions so a
user can compare results or recover earlier text. Metadata and progress are saved
atomically; interrupted transcription resumes from a validated checkpoint.

Cleanup edits wording. Formatting arranges the resulting passages while preserving
their text and order. Summaries select fewer source passages into study notes.
This separation lets users change the presentation without rerunning speech
recognition or replacing the original transcript.

## Local models and media

Speech starts on CPU. Cleanup uses GPU with CPU fallback, with explicit device
choices available for both stages. Qwen2.5 7B INT4 was retained for cleanup after
the smaller 1.5B candidate lost or added meaning in inspected examples. The
[model comparison](docs/TESTED_DECISIONS.md#dictation-loaded-models-and-alternative-engines)
records its speed and memory cost. Comparisons with other text-model families
have not been recorded.

Models are downloaded explicitly from a pinned manifest, checked against sizes
and SHA-256 hashes, and then installed. Processing uses local model files.
Compatible PCM WAV files are read directly; compressed audio and video use a
separate FFmpeg executable invoked with a fixed argument list.

## Windows packaging

PyInstaller builds a GUI and worker in one application folder. Inno Setup installs
it for the current user and creates a desktop shortcut by default. Keeping the
bundle in a folder avoids extracting it at every launch. Models and FFmpeg are
configured separately.

Install, transcription, cleanup, formatting, desktop use, reinstall, and uninstall
passed local checks on one Windows computer with Python 3.14. See the
[checkpoint evidence](host-validation/evidence/2026-10-04/audio-transcriber-checkpoint/README.md)
and [packaging guide](packaging/README.md).
