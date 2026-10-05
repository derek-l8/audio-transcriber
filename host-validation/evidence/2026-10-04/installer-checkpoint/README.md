# Windows installer checkpoint

October 4, 2026; current v0.1 app on one Windows x64 computer.
[Initial check, executable hashes, and runtime versions](report.json).

The installer contains the desktop app, standalone worker, setup guide, and
runtime notices. Python and Git are unnecessary after installation. Models and
the command-line FFmpeg decoder are downloaded separately.

The isolated installer test passed fresh install, same-version reinstall,
versioned reinstall, and uninstall. All 1,304 installed payload files matched
the bundle. Inside/outside library files and an unknown nested file survived;
the test registration and installed payload were removed. Startup stayed off.
The versioned test changed installer metadata from 0.1.0 to 0.1.1 using the same
application payload.

With developer paths removed, the installed worker downloaded and verified tiny,
transcribed a supplied 10-second M4A clip on CPU, cleaned on GPU, formatted prose,
and exported AI/formatted Markdown. The frozen GUI passed playback, seek,
editing, search, revision previews, 12 exports, close/reopen, cleanup/layout
selectors, and dictation controls. Two prerecorded clips also completed the
source dictation interface through the frozen worker with recovery copies.
Microphone capture was not started. Personal audio and transcripts remain private.

Initial builds pulled an incompatible ICU DLL from an unrelated document tool.
Restricting dependency lookup fixed Qt startup. An intermediate unsigned build
was blocked by Windows Application Control; the final build passed with the
policy unchanged.

## Defaults rebuild

A later October 4 rebuild includes Light cleanup with Mostly structured formatting
for lectures, and Medium cleanup with Mostly prose for dictation. The installed
worker completed automatic lecture cleanup/formatting and both Markdown exports.
The installed GUI defaults, playback, editing, exports, and reopening passed.
Reinstall and uninstall preserved library files and the unknown nested file.
[Defaults rebuild hash and results](defaults-rebuild.json).

The installer is unsigned and unpublished. Visual wizard/startup shortcuts,
another computer, and upgrades between different application payloads remain
unchecked. Corresponding sources must accompany the binary release; see
[notices](../../../../THIRD_PARTY_NOTICES.md).

## Prerelease packaging

The next local build starts from merged main `0223cda`. Unused Qt Virtual Keyboard,
PDF, and software OpenGL components are excluded. Eight pinned source archives,
upstream build recipes, and their notices are prepared as a separate release ZIP.
The app and worker passed installed transcription, cleanup, formatting, GUI,
reinstall, and uninstall checks. After refreshing two documentation files, the
executables retained their tested hashes and all 1,296 final installed files
matched the bundle. The isolated installation and registration were removed.
[Final installer hash and results](prerelease.json).

Release attachments and checksums are prepared locally. The installer remains
unsigned and unpublished. No real microphone recording was started in these checks.
