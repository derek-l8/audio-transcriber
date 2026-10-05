# Audio Transcriber 0.1.0 — Windows prerelease

Transcribe English audio/video locally, clean up the text, and export transcripts
or shorter study notes. The Windows app also supports dictation with a
configurable toggle or hold-to-talk shortcut.

## Install

Download `audio-transcriber-0.1.0-windows-x64.exe` and run it. After setup,
double-click the Audio Transcriber desktop shortcut. Python and Git are not
required. Open **Getting started** from the Start menu to download the speech
model and optional cleanup model. For compressed media, select a separate
`ffmpeg.exe`. Processing works offline after setup.

File imports start with Light cleanup and Mostly structured formatting;
dictation starts with Medium cleanup and Mostly prose. Raw text remains available.
Speech starts on CPU; cleanup AUTO tries GPU, then CPU. Device measurements and
reasons for these choices are in [Tested decisions](https://github.com/derek-l8/npu-scribe/blob/main/docs/TESTED_DECISIONS.md).

The installer is unsigned. This prerelease has been checked on one Windows x64
computer; microphone recording and insertion into other apps need broader use.
Review important text because transcription and cleanup can make mistakes.
Close the app before updating. Reinstalling or uninstalling keeps the library
and models in your local application-data folder.

`SHA256SUMS.txt` contains the attachment hashes. Qt/PySide (LGPLv3), FFmpeg
(LGPLv2.1 or later), and other notices are included in the app. Their sources and
build instructions are in `audio-transcriber-0.1.0-library-sources.zip`.
