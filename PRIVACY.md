# Privacy and local data

Ordinary transcription, AI cleanup, playback, editing, and export operate on local files.
The application has no telemetry, analytics, crash upload, or cloud speech API.
Default tests block network sockets, including tests of ordinary CLI commands.

## Library and recordings

The default library is `%LOCALAPPDATA%\npu-scribe` on Windows. Override it with
`--data-dir` or `NPUSCRIBE_DATA_DIR`. Models can use a separate `--model-root`.
The app copies imported recordings into the library and retains transcripts,
manual-edit revisions, AI cleanup history, settings, checkpoints, and exports there.
Cleanup compilation caches are stored under `cache/cleanup` in the library.

Choose a folder outside the repository. The app does not prevent an override
from pointing into Git or a synced directory, and it does not yet warn about
OneDrive redirection. Files in a synced library can be uploaded by the sync
service independently of NPU Scribe. Local files use ordinary filesystem
permissions; the application does not encrypt them.

## Explicit network actions

- `models download` requests approved files from `huggingface.co`. The HTTP
  client can follow redirects to the hosting service's download/CDN endpoints.
  Installed files must match the manifest's checksums and sizes.
- `evaluate` reads a supplied manifest and fetches its declared audio using
  HTTPS or a local `file:` URL. HTTPS evaluation sources are not restricted to
  Hugging Face. Review the manifest and source before running it.

These commands request downloads; they do not intentionally upload your lecture
recordings or transcripts. Remote services receive the normal request metadata,
including the requesting IP address. Ordinary transcription and cleanup do not download
missing models automatically.

## Sharing diagnostics and deleting data

Console messages and operating-system errors can contain local paths or source
filenames. Review them before sharing. Host validation tools sanitize their
published reports, but inspect any report for private paths, audio, transcripts,
and credentials before copying it into Git or an issue.

There is no in-app session deletion yet. Close the desktop and ensure its worker
has stopped before managing or backing up library files. Removing a session
folder removes its preserved recording, transcripts, edit history, and internal
exports; exported copies elsewhere remain separate.
