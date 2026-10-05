# NPU Scribe

Transcribe English audio and video files on your own computer, then optionally
clean up grammar, choose a layout, or produce study notes with a local AI model.
Export text, Markdown, JSON, or SRT subtitles. The optional Windows desktop app adds playback, search,
manual corrections, and live dictation.

Transcription and cleanup run offline after model download, with no subscription
or API key. This is a working v0.1 source package; AI cleanup and the desktop app
are experimental. The Windows installer passed local checks; a prebuilt GitHub
release has not been published.

## Install on Windows

For now, install from source using 64-bit Python 3.12 and PowerShell. The
[installation guide](docs/USER_GUIDE.md#install-on-windows) covers Git or ZIP
download, setup, and model downloads. Windows x64 is the tested platform.
The source package also supports Python 3.11.

The [Windows installer](docs/USER_GUIDE.md#using-the-windows-installer) includes
the app and a setup guide without requiring Python or Git. It is built locally;
a prebuilt release is not yet available. See [installer build and release instructions](packaging/README.md).

## Transcribe and export

From the source folder with its installed `.venv` and downloaded model,
replace the example paths below. For **MP3, M4A, or MP4**, first
[set up FFmpeg](docs/USER_GUIDE.md#cli-transcription-and-export); it is not bundled.

```powershell
$Data = Join-Path $env:LOCALAPPDATA 'npu-scribe'
$InputFile = 'C:\Lectures\lecture.mp4'
$FFmpeg = 'C:\Tools\ffmpeg\bin\ffmpeg.exe'
.\.venv\Scripts\python.exe -m npu_scribe.cli --data-dir "$Data" transcribe "$InputFile" --device CPU --ffmpeg "$FFmpeg" --cleanup off
if ($LASTEXITCODE -ne 0) { throw 'Transcription did not finish; check the message above.' }
```

Successful output includes `session: ...` and `status: ready`. Copy that session
identifier into the export command:

```powershell
$Data = Join-Path $env:LOCALAPPDATA 'npu-scribe'
$Session = 'SESSION_ID_FROM_OUTPUT'
.\.venv\Scripts\python.exe -m npu_scribe.cli --data-dir "$Data" export "$Session" --layer raw --format text
if ($LASTEXITCODE -ne 0) { throw 'Export failed; check the message above.' }
```

Exports go to `$Data\lectures\$Session\exports`. Formats are `text`, `markdown`,
`json`, and `srt`; replacing an export requires `--overwrite`. WAV input must be
mono, 16 kHz, 16-bit PCM. See the
[user guide](docs/USER_GUIDE.md#cli-transcription-and-export) for conversion and
pause/resume.

## What you get

Each session preserves the recording and its **Raw** transcript. **Balanced**
applies fixed text-cleanup rules. Manual corrections create a separate **Edited**
version; model cleanup creates **AI** text. **Formatted** changes the layout while
retaining every source passage; **Summary** holds shorter study notes.
The desktop runs Light cleanup automatically after import when its model is installed;
select Off for unedited text or Medium for more rewriting. Formatting starts with
Mostly structured. Mixed and Mostly structured request headings, lists, or tables;
invalid layouts fall back to prose. These experimental options may add little
variation. Summary creates shorter notes. Export the version you need.

Speech defaults to **CPU**. Cleanup defaults to **AUTO**, which tries an available
OpenVINO GPU and falls back to CPU. GPU gave the best measured balance of cleanup
speed, memory use, and graphics interference on our test computer. Both stages
allow explicit CPU, GPU, or NPU selection. See
[device choice and resource use](docs/USER_GUIDE.md#choose-devices-and-manage-resource-use).

## Optional AI cleanup

Follow the [cleanup guide](docs/USER_GUIDE.md#local-ai-cleanup) to download the
separate text model and clean a session or an existing UTF-8 text file. The current
Qwen2.5 7B INT4 model needs about **4.5 GB of downloads** and several GiB of RAM.

File transcription defaults to Light cleanup and Mostly structured formatting.
Download the text model first, or pass `--cleanup off` for an unedited transcript.
Use `--cleanup medium` or `--formatting prose` to change the result. Export with `--layer formatted` as text, Markdown, or JSON.

Lecture mode asks for minimal edits; dictation mode handles spoken corrections and
formatting commands in existing text. Review important results: cleanup can
change meaning.

## Optional desktop app

From the source folder, install the interface and launch it:

```powershell
.\.venv\Scripts\python.exe -m pip install '.[desktop,inference]'
if ($LASTEXITCODE -ne 0) { throw 'Desktop installation failed; stop here.' }
$Data = Join-Path $env:LOCALAPPDATA 'npu-scribe'
.\.venv\Scripts\python.exe -m npu_scribe.desktop --data-dir "$Data"
```

Choose an installed speech model, use **Choose FFmpeg** for compressed files,
and press **Import lecture**. Review the completed text, play the preserved audio,
and export the selected version. Choose Off, Light, or Medium before importing;
**Clean selected** reruns cleanup, **Format selected** changes the layout, and
**Summarize selected** creates shorter notes.
Download the separate cleanup model first, or choose Off for both cleanup and formatting. MP4 playback is audio only. See the
[desktop workflow](docs/USER_GUIDE.md#desktop-workflow) for corrections and cleanup.

## Live dictation on Windows

Open **Live dictation** in the desktop app. Choose a microphone and installed
speech model, then enable a configurable shortcut (default **Ctrl+Alt+Space**).
Use Toggle to press once to start and again to stop, or Hold to talk to record
until you release it. Wait for **Recording** before speaking.

Focus a text field in another app. After recording stops, the program transcribes,
runs Medium cleanup with Mostly prose formatting by default, saves a copy,
and sends the text to that field. Off and Light remain available.
If focus changes or insertion fails, recover it from the dictation window.
**Record a copy** works without a shortcut. See the
[dictation guide](docs/USER_GUIDE.md#live-dictation) for setup and limits.

## Your files and updates

Recordings, models, transcripts, and exports live in your local application-data
folder. Keep them out of the Git checkout. See [privacy and data locations](PRIVACY.md).

For installer updates, close the app and run the newer installer into the same
folder. Your library and models are preserved. For source updates, the
[Git or ZIP update guide](docs/USER_GUIDE.md#update-an-existing-checkout) covers
preserving code changes and reinstalling while keeping your library.

## Limits and troubleshooting

Video-link downloading is not implemented. Dictation processes recordings after
you stop, rather than displaying words as you speak. Windows app compatibility
and microphone speech capture still need broader checks.
Transcription can miss words, especially near 30-second cuts. Summaries process
excerpts separately and can omit important detail. GPU/NPU support depends on
drivers and the model. Automatic device selection does not measure the load
from your other applications.

See [common problems](docs/USER_GUIDE.md#common-problems) for missing models,
FFmpeg, device errors, slow cleanup, and library locks.

## Development and evidence

The compact [tests and decisions](docs/TESTED_DECISIONS.md) record explains model,
device, and chunking choices with measurements and links to the underlying reports.

See [development](DEVELOPMENT.md) for contributor setup and checks,
[testing](TESTING.md) for evidence and its limits, and
[model evaluation](MODEL_EVALUATION.md) for speech comparisons.
[Architecture](ARCHITECTURE.md), [Windows validation](host-validation/README.md),
and [experimental packaging](packaging/README.md) provide technical details.

Original code is [MIT licensed](LICENSE). See [third-party notices](THIRD_PARTY_NOTICES.md)
for dependencies, models, codecs, and source licenses.
