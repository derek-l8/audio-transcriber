# NPU Scribe

Transcribe English audio and video files on your own computer, then optionally
clean up grammar and formatting or produce study notes with a local AI model. Export text, Markdown,
JSON, or SRT subtitles. The optional Windows desktop app adds playback, search,
and manual corrections.

Transcription and cleanup run offline after model download, with no subscription
or API key. This is a working v0.1 source package; AI cleanup and the desktop app
are experimental. A validated installer release is not available yet.

## Install on Windows

Use 64-bit Python 3.12 and PowerShell. Follow
[Windows installation](docs/USER_GUIDE.md#install-on-windows) to get the source,
create its Python environment, and download a speech model. The guide supports
Git and **Code > Download ZIP**, and stores your library separately from the code.

Windows x64 is the locally tested target. Python 3.11 is also supported by the
source package; other devices and operating systems are not fully validated.

## Transcribe and export

From the source folder with its installed `.venv` and downloaded model,
replace the example paths below. For **MP3, M4A, or MP4**, first
[set up FFmpeg](docs/USER_GUIDE.md#cli-transcription-and-export); it is not bundled.

```powershell
$Data = Join-Path $env:LOCALAPPDATA 'npu-scribe'
$InputFile = 'C:\Lectures\lecture.mp4'
$FFmpeg = 'C:\Tools\ffmpeg\bin\ffmpeg.exe'
.\.venv\Scripts\python.exe -m npu_scribe.cli --data-dir "$Data" transcribe "$InputFile" --device CPU --ffmpeg "$FFmpeg"
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

The file is saved under `$Data\lectures\$Session\exports`. Change `--format` to
`markdown`, `json`, or `srt`; an existing export requires `--overwrite`.
WAV files bypass FFmpeg and must already be mono, 16 kHz, 16-bit PCM. The
[user guide](docs/USER_GUIDE.md#cli-transcription-and-export) covers conversion
and pause/resume. No PowerShell activation script is required.

## What you get

Each session preserves the recording and its **Raw** transcript. **Balanced**
applies deterministic cleanup. Manual corrections create a separate **Edited**
version; model cleanup creates **AI** text, and **Summary** holds shorter study notes.
The desktop runs Light cleanup automatically after import when its model is installed;
select Off for unedited text or Medium for more rewriting. Export the version you need.

Speech recognition and AI cleanup have independent device settings. Start speech
recognition on **CPU**. For cleanup, GPU was fastest under moderate graphics
activity in our one-host test; NPU used less CPU but still needed substantial RAM
and slowed a heavier graphics workload. Speech starts on CPU; cleanup defaults to
**AUTO**, which tries an available OpenVINO GPU and falls back to CPU. You can
select either device or NPU explicitly. See
[device choice and resource use](docs/USER_GUIDE.md#choose-devices-and-manage-resource-use).

## Optional AI cleanup

Follow the [cleanup guide](docs/USER_GUIDE.md#local-ai-cleanup) to download the
separate text model and clean a session or an existing UTF-8 text file. The current
Qwen2.5 7B INT4 model needs about **4.5 GB of downloads** and several GiB of RAM.

Lecture mode prioritizes detail; dictation mode attempts spoken corrections and
formatting. The model can change meaning or mishandle formatting commands, so
review important results against the source. These modes process existing text.

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
**Clean selected** reruns cleanup and **Summarize selected** creates formatted notes.
Download the separate cleanup model first, or choose Off. MP4 playback is audio only. See the
[desktop workflow](docs/USER_GUIDE.md#desktop-workflow) for corrections and cleanup.

## Your files and updates

The default library is in your local application-data folder, separate from
the source. It holds recordings, models, transcripts, revisions, and exports.
Keep personal media and transcripts out of the Git checkout. See
[privacy and data locations](PRIVACY.md).

To update, close or pause active jobs, preserve local code changes, and follow
the [Git or ZIP update procedure](docs/USER_GUIDE.md#update-an-existing-checkout).
Reinstall from the updated source and use the same library and custom model folder.

## Limits and troubleshooting

The program accepts local files. Video-link downloading and live microphone
dictation are not implemented. Summaries are excerpt-by-excerpt notes, not a
verified account of the full lecture; check them against the transcript. Transcription can miss words, including
near 30-second chunk cuts. GPU/NPU support depends on drivers and the model;
Speech Auto uses short synthetic audio; cleanup AUTO uses GPU availability and
CPU fallback. Neither measures interference with your other applications.

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
