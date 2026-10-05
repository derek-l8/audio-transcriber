# Frozen Windows review workflow

Executed locally on 2026-10-02 on one Windows host. All new work is outside
OneDrive; changes remain uncommitted and unpushed. [Results](results.json)
record the rebuilt GUI and worker hashes separately from the earlier
[package/installer validation](../package-validation/README.md).

## Fix and checks

The actual frozen GUI exposed a seek defect: changing its audio slider through
Windows accessibility moved the slider without changing the media position.
Playback restarted from zero. The slider now seeks on value changes, including
keyboard changes. Playback-driven slider updates block that signal to avoid
repeated seeks. A source Qt regression checks both value and keyboard seeking.
Eleven controls received accessibility names and object identifiers.

`Test-FrozenReview.py` creates 61 seconds of silent PCM audio and a three-chunk
mock transcript using the frozen worker. `FrozenReviewDriver.ps1` then drives
only windows owned by the launched production GUI through Windows UI Automation
and targeted Windows messages. The production callbacks remain unchanged.
It uses the native Windows Qt platform and a PATH containing only Windows system
directories. No source Qt methods, dialogs or product callbacks are replaced.

The corrected GUI sought to five seconds, displayed the matching position,
advanced playback from there, paused, and sought back to the first segment.
All four dropdowns selected their requested values. Twelve native file-picker
exports covered Raw, Balanced and Edited in text, Markdown, SRT and JSON; each
JSON matched its saved layer. Two native edit dialogs saved separate corrections
with uncertainty flagged.
Search selected the corrected phrase. The read-only history dialog showed two
revisions and previewed both the latest and older correction. Normal close exited with code 0
and removed the library lock. Reopening retained both history entries and the
latest preview, and another normal close also released the lock.

Artifact checks verified both correction texts, the revision parent chain,
unchanged segment timestamps, unchanged Raw/Balanced hashes, and unchanged
original and preserved audio hashes. The default network-free suite passed
160 tests; two tests skipped (Windows symlink privilege and opt-in live network)
in the preceding pass. Product source has not changed during this follow-up.
The expanded helpers passed Ruff lint/format over 61 Python files and parsing
of all three Windows driver scripts; prior strict mypy passed over 23 source files.

Initial harness attempts stopped on argument ordering, asynchronous GUI updates,
modal-close timing and a source-copy path lookup. The final complete run passed.
The earlier failed attempts remain in ignored storage. Product code was changed
only for the confirmed seek defect and accessibility labels.

## Reproduction and limits

From a local checkout outside synced folders, with an existing frozen bundle:

```powershell
.\.venv\Scripts\python.exe host-validation/Test-FrozenReview.py 'dist/Audio Transcriber/Audio Transcriber.exe' --work-dir .scratch/frozen-review-01 --report .scratch/frozen-review-01/results.json
```

Use a fresh work directory for each run. The helper requires Windows PowerShell
5 and the Windows UI Automation assemblies; it installs nothing. Keep the audio,
synthetic text and detailed logs ignored. Publish only reviewed metadata.

The review fixture is synthetic workflow evidence, without speech accuracy,
audible quality or visual/manual usability checks. Early dropdown and picker
attempts were harness failures: Qt popup classes differ from Win32 class names,
and Qt's empty file-dialog wrapper shares the title of the real Windows dialog.
The corrected harness targets the owned popup and Windows dialog. It handles
asynchronous control readiness and normalizes Windows file paths. Both complete
review runs passed; the final run also checked all four dropdowns.

## Close during an active job and GUI resume

[Job-close results](job-close-results.json) use the same frozen executable hashes.
The helper repeated an existing public Yale speech excerpt into a ten-minute
fixture: 20 fixed, zero-overlap chunks, tiny.en on explicit CPU. No additional
recording or model download occurred. This is a repeated speech test, not an
uninterrupted ten-minute lecture, a WER result or a performance benchmark.

Import used the actual Windows file picker. The GUI was busy with one committed
chunk when normal close was requested. It finished its current chunk, safely
stopped at two chunks, exited with code 0, removed its library lock and pause
marker, and left no owned child worker running. Reopening and selecting Resume
completed all 20 ordered, unique chunks on CPU with zero fallback events.
Previously committed segments and original/fixture/preserved audio hashes stayed
unchanged. The second normal close also exited with code 0 and removed the lock.

From the local checkout, with an existing verified tiny model and public excerpt:

```powershell
.\.venv\Scripts\python.exe host-validation/Test-FrozenJobClose.py 'dist/Audio Transcriber/Audio Transcriber.exe' --excerpt 'C:\Lectures\public-clip.mp3' --ffmpeg 'C:\Tools\ffmpeg\bin\ffmpeg.exe' --model-root 'C:\Audio Transcriber Models' --work-dir .scratch/frozen-job-close-01
```

Use a fresh work directory. Results and logs are written there. Two initial
attempts stopped before import because the Open dialog's filename control has a
different ID from Save; inspecting the owned dialog identified its control.
The final complete job-close/resume run passed. No new product defect was found.

## Remaining limits

First-run model-folder/FFmpeg selection, visual/manual usability, another Windows
host, forced bundled fallback and complete redistribution notices remain open.
The new bundle's installer and GPU/NPU checks have not been repeated. No remote
CI run occurred. All changes and test artifacts remain local outside OneDrive;
no commit or push occurred.
