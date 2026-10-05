# Windows installer

The installer targets Windows x64 and installs for the current user without
administrator access. It includes the desktop app, CLI worker, setup guide,
and runtime notices. A desktop shortcut is selected by default; startup at
sign-in remains optional. Model weights and the `ffmpeg.exe` decoder are separate
downloads. See the [installed-app setup guide](../docs/USER_GUIDE.md#using-the-windows-installer).

The [current local check](../host-validation/evidence/2026-10-04/audio-transcriber-checkpoint/README.md)
passed installed transcription/cleanup, model download, GUI workflows,
reinstall, and uninstall on one Windows host. No binary release is published.

## Build

Use a local checkout outside cloud-synced folders. From its root, create a
64-bit Python 3.14 environment and install the build dependencies:

```powershell
py -3.14 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed.' }
.\.venv\Scripts\python.exe -m pip install '.[desktop,inference,bundle]'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
.\.venv\Scripts\python.exe packaging/collect_sources.py
if ($LASTEXITCODE -ne 0) { throw 'Library source preparation failed.' }
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm packaging/audio-transcriber.spec
if ($LASTEXITCODE -ne 0) { throw 'Bundle build failed.' }
```

This produces `dist/Audio Transcriber/`. Keep both executables and `_internal` together.
The spec collects native OpenVINO libraries, installed package notices, and a
version inventory. The source collector verifies pinned upstream archives and
prepares their attribution files before bundling. It downloads about 102 MB once
into ignored storage and creates the corresponding library-source ZIP.

Install the official [Inno Setup compiler](https://jrsoftware.org/isdl.php).
Replace the compiler path below with yours:

```powershell
& 'C:\Tools\Inno Setup\ISCC.exe' packaging/audio-transcriber.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
```

The output is `dist/installer/audio-transcriber-0.1.0-windows-x64.exe`.
For another bundle location, pass `--define=BundleDir=FULL_PATH` before the script.
`--define=AppVersion=VERSION` overrides the installer version; it should match
`pyproject.toml` for a release. Builds are unsigned.

## Validate

`host-validation/Test-WindowsInstaller.py` uses a separate validation identity.
It checks silent install, same-version reinstall, a versioned reinstall with the
same payload, installed CPU transcription, GUI workflows, and uninstall.
Library hashes must survive both reinstalls and uninstall. Startup stays off,
and the desktop shortcut is tested inside ignored validation storage.

With an existing approved speech/cleanup model folder and a short recording:

```powershell
.\.venv\Scripts\python.exe host-validation/Test-WindowsInstaller.py --compiler 'C:\Tools\Inno Setup\ISCC.exe' --bundle 'dist/Audio Transcriber' --validation-dir .scratch/installer-check-01 --media 'C:\Lectures\clip.m4a' --model-root 'C:\Models\audio-transcriber' --ffmpeg 'C:\Tools\ffmpeg\bin\ffmpeg.exe' --check-cleanup --download-model
```

`--check-cleanup` checks automatic Light cleanup, Mostly structured formatting, and exports.
The installed GUI also checks fresh lecture and dictation defaults.
`--download-model` checks a fresh tiny-model download through the installed worker.
Omit these options for the smaller transcription-only test. Use a fresh validation
directory. Detailed logs, recordings, and transcripts stay in ignored storage.
A failed run may leave its isolated installation registered; inspect the logs
and use that validation directory's own `installed/unins000.exe` before rerunning.

Native review helpers and earlier results are in
[host validation](../host-validation/README.md). Before publishing a binary,
include the [corresponding library sources](LIBRARY_BUILD.md).

## Prepare a GitHub prerelease

After the bundle and installer checks pass, build the app's source/wheel files
and assemble the attachments:

```powershell
.\.venv\Scripts\python.exe -m pip install '.[dev]'
if ($LASTEXITCODE -ne 0) { throw 'Build tools installation failed.' }
.\.venv\Scripts\python.exe -m build --no-isolation --outdir dist/release
if ($LASTEXITCODE -ne 0) { throw 'Source/wheel build failed.' }
.\.venv\Scripts\python.exe scripts/check_distributions.py dist/release
if ($LASTEXITCODE -ne 0) { throw 'Archive check failed.' }
.\.venv\Scripts\python.exe packaging/prepare_release.py
if ($LASTEXITCODE -ne 0) { throw 'Release preparation failed.' }
```

`dist/release/` holds the installer, app source/wheel, library sources,
`SHA256SUMS.txt`, and `release-manifest.json`. Use `RELEASE_NOTES.md` as the
release description. The manifest records the local base revision and source
hashes; a dirty tree needs committing before choosing the release tag's target.

Once those changes are merged and CI passes, create a GitHub prerelease tagged
`v0.1.0` at that revision and attach all six files listed in the manifest.
After publication, change the README's installation section to lead with that
release's installer link. Until then, source installation remains the available
public route. Do not put generated release attachments in Git.
