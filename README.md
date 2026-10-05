# NPU Scribe

Transcribe English audio and video files locally, clean up the text, and export
transcripts or study notes. The Windows app includes playback, corrections,
search, and dictation with a configurable hotkey.

Processing runs offline after model download, with no subscription or API key.
This is an early Windows x64 version; AI cleanup and dictation are experimental.

## Setup

Use 64-bit Python 3.12 and PowerShell. Follow the
[installation guide](docs/USER_GUIDE.md#install-on-windows) for downloading the
project, creating an environment, and installing a speech model. The source
package also supports Python 3.11.

AI cleanup and Mixed or Mostly structured formatting use a
[separate text model](docs/USER_GUIDE.md#local-ai-cleanup), about 4.5 GB to download
and several GiB of RAM to run. If you skip it, choose **Off** for both cleanup
and formatting. MP3, M4A, and MP4 require a separate
[FFmpeg executable](docs/USER_GUIDE.md#cli-transcription-and-export).

After setup, install and open the desktop app from the project folder:

```powershell
.\.venv\Scripts\python.exe -m pip install '.[desktop,inference]'
if ($LASTEXITCODE -ne 0) { throw 'Desktop installation failed.' }
.\.venv\Scripts\python.exe -m npu_scribe.desktop
```

## Transcribe a file

1. Select your installed speech model. Use **Choose FFmpeg** for compressed files.
2. Choose cleanup and formatting settings, then press **Import lecture**.
3. Review the text. **Raw** keeps the original transcript; cleanup and formatting
   are saved separately. **Summarize selected** creates shorter study notes.
4. Export text, Markdown, JSON, or SRT subtitles.

**Clean selected** and **Format selected** rerun those stages. See the
[desktop guide](docs/USER_GUIDE.md#desktop-workflow) for editing and playback,
or the [CLI guide](docs/USER_GUIDE.md#cli-transcription-and-export) for commands.

## Dictation

Open **Live dictation**, select a microphone and speech model, and enable the
shortcut. The default is **Ctrl+Alt+Space**; choose Toggle or Hold to talk.
Wait for **Recording** before speaking.

Focus a text field in another app. When recording stops, the app transcribes,
cleans up the text, saves a copy, and inserts it into that field. If insertion
fails, recover the text from the dictation window.
[Dictation setup and options](docs/USER_GUIDE.md#live-dictation).

## Cleanup and formatting

| Workflow | Default cleanup | Default formatting |
| --- | --- | --- |
| Imported files | Light | Mostly structured |
| Dictation | Medium | Mostly prose |

Choose **Off**, **Light**, or **Medium** cleanup. Formatting offers **Mostly
prose**, **Mixed**, and **Mostly structured** layouts. Summaries are a separate
option. Review important text: recognition and cleanup can make mistakes, and
summaries can omit detail.

## Devices and measured decisions

Transcription starts on **CPU**. Cleanup uses **AUTO**, which tries an available
OpenVINO GPU, then CPU. Both stages also offer explicit CPU, GPU, and NPU choices.

The [tested decisions](docs/TESTED_DECISIONS.md) document compares speed, accuracy,
memory use, and graphics interference on the test computer, and explains the
chosen defaults. See [device settings](docs/USER_GUIDE.md#choose-devices-and-manage-resource-use)
for configuration and resource limits.

## Files and updates

Recordings, models, transcripts, and exports stay in your local library.
[Privacy and storage](PRIVACY.md) explains the locations.

The [update guide](docs/USER_GUIDE.md#update-an-existing-checkout) covers Git and
ZIP installations. Installer updates keep the library and models. See
[common problems](docs/USER_GUIDE.md#common-problems) for model, FFmpeg, device,
and startup errors.

## Development

[Development](DEVELOPMENT.md) covers contributor setup;
[testing](TESTING.md) records the checks;
[packaging](packaging/README.md) covers building the Windows installer and
preparing a release.

Code is [MIT licensed](LICENSE). See [third-party notices](THIRD_PARTY_NOTICES.md)
for dependencies and models.
