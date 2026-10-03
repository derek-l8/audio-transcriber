# Experimental Windows packaging

The PyInstaller bundle has one-host Windows checks: real CPU/GPU/NPU Whisper
transcription, Auto selection, a source Qt interface driving its frozen worker
through pause/resume and exports, and native frozen GUI idle close/reopen.
The Inno recipe also passed isolated silent install, same-version reinstall,
uninstall, and user-file preservation checks.
See [package validation evidence](../host-validation/evidence/2026-10-02/package-validation/README.md).
These historical bundles predate AI cleanup. Rebuild and exercise the current
cleanup-enabled GUI, worker, and installer before shipping an executable.
The recorded checks do not establish a validated installer release.

## Build a local bundle

Keep the checkout and generated artifacts outside OneDrive or other synced
folders. Run from the repository root on Windows in a virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[desktop,inference,bundle]'
if ($LASTEXITCODE -ne 0) { throw 'Bundle dependency installation failed.' }
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm packaging/npu-scribe.spec
```

The `bundle` extra pins PyInstaller 6.22.3. The recorded build used contrib hooks
2026.8; transitive dependencies are not fully locked. Paths are resolved from
the spec's directory. Absolute package imports in `desktop_entry.py` and
`worker_entry.py` avoid direct-script relative-import failures. The recipe
explicitly collects the native tokenizer extension that GenAI loads dynamically.

The result is `dist/NPU Scribe/`, containing a windowed `NPU Scribe.exe`, a
console `npu-scribe-worker.exe`, and shared `_internal` files. The desktop starts
the worker so stdout/stderr reach its process pipes. Ship the whole directory;
the GUI alone is insufficient. `npu-scribe.iss` copies that directory.

## Repeat the worker workflow check

This helper uses the source Qt UI with the frozen worker. It does not automate
clicks in the frozen GUI. Supply an already downloaded approved model, an
FFmpeg executable, and a multi-chunk recording. Run from the repository root
in the development environment:

```powershell
.\.venv\Scripts\python.exe host-validation/Test-DesktopWorkflow.py 'C:\Lectures\lecture.mp3' --data-dir .scratch/frozen-ui-check/library --model-root 'C:\NPU Scribe Models' --ffmpeg 'C:\Tools\ffmpeg\bin\ffmpeg.exe' --worker-executable 'dist/NPU Scribe/npu-scribe-worker.exe' --report .scratch/frozen-ui-check/results.json
```

Use a new data directory for each run. Audio copies, transcripts, exports, and
screenshots stay in ignored storage; publish only reviewed metadata reports.

## Build and check a local installer

Use the official [Inno Setup compiler](https://jrsoftware.org/isdl.php) on Windows.
The local validation uses version 7.1.0. With the complete bundle in `dist/NPU Scribe`,
run from the repository root, replacing the compiler path with your installation:

```powershell
& 'C:\Tools\Inno Setup\ISCC.exe' packaging/npu-scribe.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
```

Output goes to ignored `dist/installer/`. The compiler rejects bundles missing
either executable. For a different bundle location, pass
`'--define=BundleDir=C:\Builds\NPU Scribe'` before the script argument.
The installer targets Windows x64, installs for the current user, and offers
launch-at-sign-in as an unchecked option. Uninstall removes installed files;
unknown files and libraries placed in the installation folder are preserved.

`Test-WindowsInstaller.py` compiles a separate validation identity and runs silent
install, same-version reinstall, installed CPU inference, native idle GUI
close/reopen, and uninstall. It compares file hashes to check library preservation
both inside and outside the installation folder. It creates no shortcuts and
requires a fresh directory under this checkout's `.scratch`. Run only when local
installer execution is authorized, with an existing model and a short public clip:

```powershell
.\.venv\Scripts\python.exe host-validation/Test-WindowsInstaller.py --compiler 'C:\Tools\Inno Setup\ISCC.exe' --bundle 'dist/NPU Scribe' --validation-dir .scratch/installer-check-01 --media 'C:\Lectures\public-clip.mp3' --model-root 'C:\NPU Scribe Models' --ffmpeg 'C:\Tools\ffmpeg\bin\ffmpeg.exe'
```

Reports and detailed logs remain in that validation directory. A failed run may
leave its isolated installation registered; inspect its logs and use its own
`installed/unins000.exe` before another run. Never substitute the normal app's
installation folder or uninstaller. Success leaves the test libraries intact.

For just the native idle window check, `Test-FrozenWindow.py` takes the GUI
executable, `--data-dir` pointing to a fresh `.scratch` directory, and `--report`.
It requests normal Windows close, checks lock removal, then opens/closes again.
This does not exercise editing, playback, or closing during a job.

## Check the native frozen review workflow

`Test-FrozenReview.py` builds a fresh silent/mock lecture library, then uses
Windows UI Automation and targeted Windows messages against only the launched
GUI's windows. It checks
all four dropdowns, playback, seeking, native edit saves, search, latest/older
history previews, twelve native file-picker exports and normal close/reopen. Original audio/transcript hashes and saved revisions are checked
on disk. It installs no tools and requires a local checkout outside OneDrive:

```powershell
.\.venv\Scripts\python.exe host-validation/Test-FrozenReview.py 'dist/NPU Scribe/NPU Scribe.exe' --work-dir .scratch/frozen-review-01 --report .scratch/frozen-review-01/results.json
```

Use a fresh work directory. The [one-host result](../host-validation/evidence/2026-10-02/frozen-review/README.md)
records the exact rebuilt executables and limits. This is synthetic workflow
validation, without real speech or visual/manual usability checks.

`Test-FrozenJobClose.py` uses an existing public speech excerpt and an installed
approved tiny model. It creates a bounded ten-minute repeated-speech fixture,
imports through the Windows picker, closes while inference is active, and
reopens/resumes through the actual GUI. It checks safe interruption, worker exit,
lock removal, unchanged audio/committed text and ordered completion. No download
or accuracy measurement is performed:

```powershell
.\.venv\Scripts\python.exe host-validation/Test-FrozenJobClose.py 'dist/NPU Scribe/NPU Scribe.exe' --excerpt 'C:\Lectures\public-clip.mp3' --ffmpeg 'C:\Tools\ffmpeg\bin\ffmpeg.exe' --model-root 'C:\NPU Scribe Models' --work-dir .scratch/frozen-job-close-01
```

Use a fresh work directory; reports and detailed logs remain there. Do not use
these helpers with your everyday library. The recorded test preserved its
committed segments and completed twenty chunks after reopening.

## Remaining release checks

- First-run model-folder/FFmpeg selection and visual/manual usability.
- Forced Auto fallback in the frozen worker; current device runs had no failures.
- Another Windows machine without the checkout or development environment.
- Installer wizard interaction, selected startup shortcuts, and upgrades between
  different application versions; the recorded test used a separate identity.
- Complete redistribution inventory and notices for Qt, codec/native libraries,
  Python, and OpenVINO. The included [inventory](../THIRD_PARTY_NOTICES.md) is a draft.

Model weights and the `ffmpeg.exe` command-line decoder are not bundled.
Qt Multimedia's playback backend includes codec libraries such as
`avcodec-61.dll`; those are separate from the configured decoder executable and
must be included in the redistribution review.
