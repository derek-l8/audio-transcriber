# Using NPU Scribe

This guide covers Windows installation, transcription, cleanup, the optional
desktop interface, and updates. Run the examples from the source folder containing
your installed `.venv`. In a new PowerShell window, recreate the variables used
by the example. Ordinary transcription and cleanup are offline after model download.

## Install on Windows

Use [64-bit Python 3.12](https://www.python.org/downloads/windows/) and PowerShell.
Check that the requested Python is available with `py -3.12 --version`. Python 3.11 is also supported by the source
package. Windows x64 is the locally tested target; other devices and operating
systems are not fully validated.

1. Get the source using **Code > Download ZIP** on GitHub, or clone it with Git.
   Extract or clone into a normal local folder outside OneDrive or other cloud
   sync. Open PowerShell in the folder containing `pyproject.toml`.

   If you have Git, this creates the checkout under your local Projects folder:

   ```powershell
   $Projects = Join-Path $env:USERPROFILE 'Projects'
   New-Item -ItemType Directory -Force -Path $Projects -ErrorAction Stop | Out-Null
   Set-Location $Projects -ErrorAction Stop
   git clone https://github.com/derek-l8/npu-scribe.git
   if ($LASTEXITCODE -ne 0) { throw 'Clone failed; stop here.' }
   Set-Location npu-scribe -ErrorAction Stop
   ```

2. Install the engine in its own Python environment:

   ```powershell
   py -3.12 -m venv .venv
   if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed; stop here.' }
   .\.venv\Scripts\python.exe -m pip install '.[inference]'
   if ($LASTEXITCODE -ne 0) { throw 'Installation failed; stop here.' }
   ```

3. Download a speech model. This step needs internet access:

   ```powershell
   $Data = Join-Path $env:LOCALAPPDATA 'npu-scribe'
   .\.venv\Scripts\python.exe -m npu_scribe.cli --data-dir "$Data" models download whisper-tiny.en-int4-ov
   if ($LASTEXITCODE -ne 0) { throw 'Model download failed; stop here.' }
   ```

   The default library is your local application-data folder. Recordings, models,
   and transcripts are stored there, separately from the code. `tiny.en` is a
   small first-use model. Run `.\.venv\Scripts\python.exe -m npu_scribe.cli models list`
   to see other approved choices.

Run each step only after the previous one succeeds. The commands below use the
environment in the source folder; no PowerShell activation script is required.
Keep using the same library when downloading models and processing files.

## CLI transcription and export

The examples use the environment under the source folder. If you run from
another directory, use the full path to its Python executable followed by
`-m npu_scribe.cli`. Activating the environment is optional.

For MP3, M4A, or MP4, get a Windows executable build through the
[FFmpeg download page](https://www.ffmpeg.org/download.html), extract it to a
local folder, and locate `bin\ffmpeg.exe`. The decoder is not bundled. For a WAV file, change the input path below to an existing mono,
16 kHz, 16-bit PCM recording:

```powershell
$Data = Join-Path $env:LOCALAPPDATA 'npu-scribe'
$Model = 'whisper-tiny.en-int4-ov'
$InputFile = 'C:\Lectures\lecture.wav'
.\.venv\Scripts\python.exe -m npu_scribe.cli --data-dir "$Data" transcribe "$InputFile" --model "$Model" --device CPU
if ($LASTEXITCODE -ne 0) { throw 'Transcription did not finish; check the message above.' }
```

The output contains `session: ...` and `status: ready` on completion. Copy the
session identifier into `$Session` below. Choose `raw`, `balanced`, `edited`,
or `ai` (which require a saved revision or completed cleanup). Use `summary` for
saved study notes in text, Markdown, or JSON:

```powershell
$Data = Join-Path $env:LOCALAPPDATA 'npu-scribe'
$Session = 'SESSION_ID_FROM_OUTPUT'
.\.venv\Scripts\python.exe -m npu_scribe.cli --data-dir "$Data" export "$Session" --format srt --layer balanced
if ($LASTEXITCODE -ne 0) { throw 'Export failed; check the message above.' }
```

The export is stored under `$Data\lectures\$Session\exports`. Existing exports
are refused unless you explicitly add `--overwrite`. Available formats are
`json`, `markdown`, `text`, and `srt`.

For MP3/M4A/MP4, FFmpeg is discovered on PATH. To select another executable,
set its path and add `--ffmpeg` to the run:

```powershell
$Data = Join-Path $env:LOCALAPPDATA 'npu-scribe'
$Model = 'whisper-tiny.en-int4-ov'
$FFmpeg = 'C:\Tools\ffmpeg\bin\ffmpeg.exe'
$InputFile = 'C:\Lectures\lecture.mp4'
.\.venv\Scripts\python.exe -m npu_scribe.cli --data-dir "$Data" transcribe "$InputFile" --model "$Model" --device CPU --ffmpeg "$FFmpeg"
```

Nonconforming WAV files need conversion before import; passing `--ffmpeg`
does not change the direct WAV decoder's requirements. To create a new compatible
file, replace these paths with your source and FFmpeg executable:

```powershell
$FFmpeg = 'C:\Tools\ffmpeg\bin\ffmpeg.exe'
$InputFile = 'C:\Lectures\original.wav'
& "$FFmpeg" -n -i "$InputFile" -ac 1 -ar 16000 -c:a pcm_s16le 'converted.wav'
if ($LASTEXITCODE -ne 0) { throw 'Conversion failed; check the message above.' }
```

Use `converted.wav` as the transcription input. The `-n` option refuses to
overwrite an existing file.

### Pause and resume from the CLI

Add `--stop-file PATH` when starting a run. Creating that file requests a safe
pause; use a second PowerShell window to create it. Remove the marker before
resuming. Exit code 130 indicates a safe pause, 1 an operational error, and 2
invalid arguments.

Resume a paused/failed session with the **same model** and library. For compressed
media, supply its FFmpeg executable again. The saved chunk plan is reused:

```powershell
$Data = Join-Path $env:LOCALAPPDATA 'npu-scribe'
$Session = 'SESSION_ID_FROM_OUTPUT'
$Model = 'whisper-tiny.en-int4-ov' # Replace with the model originally used.
.\.venv\Scripts\python.exe -m npu_scribe.cli --data-dir "$Data" resume "$Session" --model "$Model" --device CPU
```

If the desktop was forcibly terminated, confirm its worker has stopped before
using CLI resume on a session still marked `processing`. Resume refuses changed
preserved audio or mismatched model identity. Completed sessions cannot resume;
start a new import to transcribe again.

## Desktop workflow

Install and launch the optional interface with the
[README desktop commands](../README.md#optional-desktop-app).

Choose an installed model and import WAV, MP3, M4A, or MP4. CPU is initially
selected. Auto benchmarks available devices and can try other successful
benchmark devices after inference fails; manual selection stays on that device.
For compressed media, install FFmpeg on PATH or use **Choose FFmpeg** to select
its executable. A command-line path or saved selection overrides PATH discovery.
Restart the app after changing the machine's PATH.

Pause and window close request a safe stop after preparation or the current
chunk. Wait for the worker to finish; forced termination can leave the session
marked `processing`. Resume a paused/failed session with **Resume**. The app
uses its saved model and chunk strategy. Keep that model installed.

Only one desktop window can open a given library. Avoid using the CLI on the
same session while its worker is active.

### Review, correct, and export

**Raw** is the model output. **Balanced** applies deterministic cleanup.
Search either layer, play the preserved recording, and use **Seek to segment**
to jump to selected text without starting playback. Changing layers keeps the
playback position. MP4 playback is audio only.

**Edit selected segment** saves a separate **Edited** version. Later edits build
on Edited, and **Revision history** displays retained earlier versions.
Raw/Balanced stay unchanged. Timestamps stay fixed for subtitles and playback.
You can change the uncertainty flag; the edited segment's original model
confidence is cleared. Empty text retains its interval but omits that SRT cue.

Save failures keep the draft open, and stale editors cannot overwrite a newer
revision. Unsaved drafts are lost if the process is forcibly closed. JSON
exports include manual-edit attribution, revision ID, and source layer/hash.
Text, Markdown, and SRT exports contain the selected layer's text.

## Local AI cleanup

Cleanup uses an independent local text model. It is optional and requires the
`inference` extra already used for real transcription. Download the pinned model
explicitly into the same library/model root used by the app:

```powershell
$Data = Join-Path $env:LOCALAPPDATA 'npu-scribe'
.\.venv\Scripts\python.exe -m npu_scribe.cli --data-dir "$Data" models download qwen2.5-7b-instruct-int4-ov
if ($LASTEXITCODE -ne 0) { throw 'Cleanup model download failed; stop here.' }
```

The verified download is about 4.5 GB; leave room for staging, runtime caches,
and model memory. No model weights are committed or bundled with the program.
After downloading, ordinary cleanup uses local files without an API key or
network connection.

In the desktop, choose **Off**, **Light**, or **Medium** before importing. Light is
the initial setting. A completed import or resume automatically runs the selected
cleanup; Off skips the model. If cleanup fails or its model is missing, the
transcript stays ready and can be exported. Download the model and use **Clean
selected** to retry or change the level. Cleanup has its own AUTO/CPU/GPU/NPU setting.
The completed result appears in **AI**. Cleanup always reads **Raw**, even if another layer is
visible. Export the AI layer to keep its formatting. AI text is not editable in
the manual segment editor; use the exported text or the Edited layer for manual
corrections. Search and playback remain available; **Seek to segment** is disabled
for AI because its paragraphs do not have word alignment.

- **Lecture** prioritizes retaining detail, technical wording, corrections, and
  uncertainty. Words such as “period” are treated as content.
- **Dictation** attempts to remove false starts, resolve explicit self-corrections,
  and interpret spoken punctuation, “new paragraph,” and list commands. These
  edits can be imperfect. The requested “literal” escape has failed a targeted
  test, so review any wording that resembles a formatting command.
- **Off** skips AI cleanup; **Raw** always remains available as unedited text.
- **Light** makes minimal grammar and formatting edits. **Medium** also improves
  clarity and reduces redundant dictation phrasing; it does not generate a summary.

For one CLI job that transcribes and then cleans, add `--cleanup light` or
`--cleanup medium` to `transcribe` or `resume`. CLI transcription defaults to
`--cleanup off`; the desktop defaults to Light. Cleanup defaults to AUTO (GPU,
then CPU). Use `--cleanup-device CPU`, `GPU`, or `NPU` to require that device.
Cleanup failure returns exit 1 while leaving a ready, exportable transcription.

```powershell
$Data = Join-Path $env:LOCALAPPDATA 'npu-scribe'
.\.venv\Scripts\python.exe -m npu_scribe.cli --data-dir "$Data" transcribe 'lecture.wav' --device CPU --cleanup light
```

To clean an existing session and export it:

```powershell
$Data = Join-Path $env:LOCALAPPDATA 'npu-scribe'
$Session = 'SESSION_ID_FROM_OUTPUT'
.\.venv\Scripts\python.exe -m npu_scribe.cli --data-dir "$Data" cleanup "$Session" --device AUTO --mode lecture --style light
if ($LASTEXITCODE -ne 0) { throw 'Cleanup did not finish; check the message above.' }
.\.venv\Scripts\python.exe -m npu_scribe.cli --data-dir "$Data" export "$Session" --layer ai --format markdown
```

For an existing UTF-8 text file, run from the source folder and replace the
input path. This uses the same downloaded model and library:

```powershell
$Data = Join-Path $env:LOCALAPPDATA 'npu-scribe'
.\.venv\Scripts\python.exe -m npu_scribe.cli --data-dir "$Data" cleanup-text 'draft.txt' --output 'cleaned.txt' --mode dictation --style light --device CPU
```

Use `--format json` for settings, source hash, and per-block warnings. Existing
outputs require `--overwrite`, and the input file cannot be the output. Global
`--data-dir` / `--model-root` options go before the subcommand. No transcription
session or audio decoder is required for text cleanup.

Raw, Balanced, Edited, and the recording remain unchanged. Each completed
cleanup retains a snapshot in `ai-cleanup-history`; `ai-transcript.json` selects
the latest result. JSON exports record the raw hash, speech provenance, pinned
cleanup model, mode/style, and block warnings. History is currently available
as files, not through the manual **Revision history** dialog.

**Limits:** the model can still change meaning, names, or dates. Heuristic checks
compare digit quantities, negation, and large text-size changes; a failed block
retains its source text and receives an uncertainty flag. Passing checks is not
proof of fidelity. Corrections across input blocks (up to 1,200 characters) may
not resolve. Review important text against Raw/audio. AI SRT uses coarse source
block intervals, not newly aligned sentence/word timings; use Raw/Edited for
precise source cues. This is batch cleanup, without microphone capture, hotkeys,
or insertion into another application's text field.

AUTO tries a GPU exposed by OpenVINO; if GPU loading or generation fails, it
retries the current block on CPU and stays there for the job. JSON records the
requested and successful devices, per-block devices, and any fallback reason.
Explicit CPU/GPU/NPU selections fail rather than switching; driver/model support varies. First use includes compilation and can be slow. Stop/Pause requests are checked between blocks and during token generation;
compilation must finish first. Cancelled/failed runs retain the previous complete
AI version and do not resume partial output: rerun cleanup to start again.

## Summaries and formatted study notes

Press **Summarize selected** for a completed session. The same downloaded text
model selects important source passages and groups them under headings. The
program formats the selected passages into bullets with conservative rule cleanup;
it does not let the model write replacement claims. It reads Raw, saves a separate
**Summary**, and leaves AI cleanup and the
full transcript intact. Summary works even when cleanup is Off.

CLI equivalent:

```powershell
$Data = Join-Path $env:LOCALAPPDATA 'npu-scribe'
$Session = 'SESSION_ID_FROM_OUTPUT'
.\.venv\Scripts\python.exe -m npu_scribe.cli --data-dir "$Data" summarize "$Session"
if ($LASTEXITCODE -ne 0) { throw 'Summary did not finish; check the message above.' }
.\.venv\Scripts\python.exe -m npu_scribe.cli --data-dir "$Data" export "$Session" --layer summary --format markdown
```

Export Summary as text, Markdown, or JSON; summaries cannot become SRT subtitles.
Each excerpt is processed independently (up to 1,200 source characters), so a
long lecture can have repeated headings or miss links between sections. There is
no second pass combining the whole lecture. Invalid passage selections or output
trigger source fallback. Notes retain recognition errors in the selected passages;
selection and headings can still omit or misrepresent context. Review against Raw/audio. Completed versions are
retained in `summary-history`; failure/cancellation keeps the prior version.
Very short excerpts can grow because headings add words. The new summary prompt
is not covered by the repeated device cleanup quality study.

## Choose devices and manage resource use

Speech recognition and AI cleanup have separate device settings. Speech starts
on CPU; cleanup starts on AUTO (GPU, then CPU). These are starting policies based
on one host, not a benchmark or resource limit for your computer. Saved choices
are restored, including explicit devices. See the compact
[tests and decisions](TESTED_DECISIONS.md) record for the comparisons.

- **Speech:** start with CPU. `tiny.en` is a small first-use model; `base.en`
  scored better on several lecture comparisons but took longer. Those published
  references are provisional. Use `models list` to find approved model IDs.
- **Cleanup on GPU:** fastest under moderate graphics activity in our one-host
  test, with less resident RAM than CPU or NPU cleanup.
- **Cleanup on NPU:** consumed the least CPU, but still needed several GiB of
  RAM and slowed a heavier graphics workload. It is not guaranteed to leave
  other applications unaffected.
- **Cleanup on CPU:** works without a compatible accelerator. The 7B cleanup
  model used more CPU and RAM in that comparison.

The [one-host resource comparison](../host-validation/evidence/2026-10-02/cleanup-resource-cost/README.md)
records actual speed, RAM, and graphics interference. Its short requests and
synthetic graphics workloads do not predict every app or device.

Check resource use with your normal applications open. Cleanup keeps its model
loaded throughout a job, and a new desktop cleanup action loads it again.
First use may compile the model before producing text. Stop/Pause can wait for
compilation to finish. There is no automatic resource cap or idle scheduling;
stop or defer cleanup when you need the headroom. Audio device Auto benchmarking
does not measure cleanup or the effect on your other applications.

## Alternate model folder

Both launchers accept `--model-root`. That folder contains model-ID subfolders,
not a single model's files. Use the same location for download and launch:

```powershell
$Data = Join-Path $env:LOCALAPPDATA 'npu-scribe'
$Models = 'D:\NPU Scribe Models'
.\.venv\Scripts\python.exe -m npu_scribe.cli --data-dir "$Data" --model-root "$Models" models download whisper-tiny.en-int4-ov
if ($LASTEXITCODE -ne 0) { throw 'Model download failed; stop here.' }
.\.venv\Scripts\python.exe -m npu_scribe.desktop --data-dir "$Data" --model-root "$Models"
```

The desktop saves its model-folder and FFmpeg settings in the library when a
job starts. Command-line paths override those saved settings.

## Update an existing checkout


Close the desktop and finish or pause its worker first. Keep the library
separate from the source folder and back it up before an update.

For a **Git checkout**, run `git status --short` from the repository folder.
Preserve local edits before updating. When it is clean and on your tracking
branch, run:

```powershell
git pull --ff-only
if ($LASTEXITCODE -ne 0) { throw 'Update failed; resolve the Git error before reinstalling.' }
```

If Git reports detached HEAD or divergent history, stop and resolve that state
before reinstalling; do not discard local work to bypass the error.

For a **ZIP installation**, download and extract the new source ZIP into a
new local folder. Keep the old folder if it contains your own code changes;
do not copy its virtual environment into the new folder.

In either case, install from the updated source folder:

```powershell
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Environment setup failed; stop here.' }
.\.venv\Scripts\python.exe -m pip install --upgrade '.[inference]'
if ($LASTEXITCODE -ne 0) { throw 'Reinstallation failed; stop here.' }
```

Desktop users should use `'.[desktop,inference]'` in the install command.
Reinstallation is required to refresh the installed program and dependencies.
Your existing models and sessions remain in the separate library; reopen with
the same `--data-dir` and any custom `--model-root`.

## Common problems

| Message or symptom | Check |
|---|---|
| `py -3.12` unavailable | Install 64-bit Python 3.12 or make that version available to the Python launcher. |
| Python module missing | Run from the source folder with its `.venv\Scripts\python.exe`, or use the full executable path. Install the extras shown in the README. |
| Model not installed | Download the approved model explicitly into the same library/model root used for the job. A speech model and a cleanup model are separate downloads. |
| Resume model mismatch | Supply the original `--model`; the CLI default is `whisper-tiny.en-int4-ov`. |
| Compressed media needs FFmpeg | Follow [FFmpeg setup](#cli-transcription-and-export), choose its executable in the app, or pass `--ffmpeg` in the CLI. |
| WAV normalization error | Use the conversion example in [CLI transcription](#cli-transcription-and-export). |
| GPU/NPU fails | Try CPU. An explicit device request will not silently switch. |
| Library already open | Close the other desktop window using that library. |
| Transcript misses words | Review the audio; model errors and chunk-boundary losses remain possible. |
| Cleanup is slow or uses too much RAM | Check [device/resource guidance](#choose-devices-and-manage-resource-use); compilation and a resident 7B model can be costly. |
| AI text contains unchanged or incorrect passages | Compare with Raw/audio. A rejected block retains its source; passing the checks does not guarantee correct edits. |

For updates, use the [update procedure](#update-an-existing-checkout).
For data handling and report sharing, see [Privacy](../PRIVACY.md). Advanced
evaluation and hardware checks are described in [Testing](../TESTING.md) and
[Windows validation](../host-validation/README.md).
