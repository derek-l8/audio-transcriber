# Privacy

NPU Scribe is designed for local inference with no telemetry, analytics, crash
reporting, automatic update check, cloud API, or API key. Network access is
limited to two explicit actions: `npu-scribe models download` and
`npu-scribe evaluate` (which fetches the manifest-declared public evaluation
file). A socket-denial test verifies ordinary transcription performs no network
activity.

## Data locations

User data lives in ordinary files under the platform application data directory
(override with `--data-dir`). Setup must still detect likely OneDrive Desktop
redirection for the future desktop app and offer a clearly non-synced local
directory before storing recordings. The repository is never a data directory;
models, recordings, transcripts, and evaluation datasets are kept out of Git.

## What leaves the machine

Only the explicit model/evaluation downloads described above, from an HTTPS host
allowlist (`huggingface.co`). Nothing else transmits data. There is no telemetry.

## Console vs reports

The CLI prints session identifiers and data-directory-relative locations to the
operator's own console so sessions can be resumed or exported; it does not print
input-file absolute paths in errors. Validation reports (host-validation) never
include transcript content, audio, clipboard contents, usernames, credentials,
or private absolute paths — the PowerShell script sanitizes paths before writing.
Review any report before sharing.

## User control

History is ordinary per-session directories; deletion will enumerate an exact
session directory and require explicit confirmation when implemented. The user
controls failed-audio retention and exports. Insertion features retain text in
history locally only.
