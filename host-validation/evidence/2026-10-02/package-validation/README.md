# Clean installation and Windows bundle checks

Executed locally on 2026-10-02, on one Windows 11 host with Python 3.12.14.
Changes remain uncommitted and unpushed. [Metadata results](results.json) contain
no audio, transcript text, screenshot, usernames, or private absolute paths.

## Installation

A new ignored environment installed the declared dev/desktop/inference extras
and PyInstaller 6.22.3. `pip check` found no broken requirements. The default
suite passed 159 tests, with one symlink-privilege skip and one live deselection;
mypy passed over 23 source files.

A wheel built from the source distribution was installed into a second fresh
environment with only the base dependency. `scripts/smoke_installed.py` refused
editable-source imports and exercised both installed launchers, model listing,
a two-chunk synthetic mock session paused/resumed through the CLI, and eight
nonempty Raw/Balanced exports. This is a clean installation check, not real
speech inference. The CI package job now invokes the same helper.

## Frozen bundle

The initial recipe failed because script paths were resolved relative to the
spec directory. Paths now resolve from `SPECPATH`. A successful initial build
then failed real Whisper inference because the tokenizer extension DLL was
missing. Explicit native-library collection fixed that failure.

The corrected frozen worker enumerated CPU/GPU/NPU and transcribed the existing
72-second public Yale classroom excerpt on CPU using an already verified tiny.en
model and the external FFmpeg executable. No additional media/model download
or accuracy scoring occurred. Launch environment PATH contained only Windows
system directories; Python/virtual-environment paths were removed.

The source Qt UI drove the frozen worker through pause/resume and a second
uninterrupted import. Resumed segments matched the uninterrupted run exactly.
Search, eight exports, muted playback advancement and transcript seeking passed.
This tests a source Qt interface with the packaged worker; it does not establish
those interactions inside the frozen GUI executable.

The frozen GUI separately passed a six-second offscreen startup check with its
library lock present and its process alive. No job was started; the test process
was then terminated. This does not test graceful close or visual interaction.
The final bundle includes the project MIT license and draft third-party inventory;
its executable/tokenizer hashes match the versions exercised above.

## Installer and native window follow-up

Inno Setup 7.1.0 was downloaded from the official site, its Authenticode signature
was valid with publisher Pyrsys B.V., and its compiler was extracted in portable
mode. The recipe compiled and rejected an incomplete bundle missing its worker.
Default preprocessing retained the original application identity.

The uninstall recipe previously deleted the entire installation directory.
It now removes tracked payload files and preserves unknown files. Startup is
unchecked by default, x64 is explicit, and installer output goes to ignored `dist`.

The test used a separate identity and no shortcuts. Silent installation verified
all 1,295 bundled files by SHA-256. The installed worker completed the existing
72-second public excerpt on CPU. Same-version reinstall and uninstall preserved
all five real lecture-library files inside the installation directory, all six
files in a separate copied library, and an unknown file nested under `_internal`.
Uninstall removed the installed payload and its temporary user registration.
Two initial harness attempts stopped at reporting errors (saved-settings encoding
and a session diagnostics lookup); their isolated installations were removed.
The corrected helper subsequently passed the complete workflow.

The actual installed frozen GUI also opened and closed normally twice using the
native Windows platform and minimal PATH. Each close exited with code 0 and
removed its library lock. This was an idle lifecycle test, without editing or
playback interaction.

The frozen worker separately completed three chunks on explicit GPU and NPU,
and Auto completed on CPU, with zero reported fallback events. These are device
binding/completion checks, without WER or comparative performance claims.

After OneDrive deletion prompts from test cleanup, both checkouts and all local
artifacts were copied to a local folder outside OneDrive. All 51,980 original
files matched by SHA-256 before Git/environment paths were repaired. The relocated
suite passed 159 tests with one skip and one deselection; launcher/import and
`pip check` also passed. Validation helpers now reject a known OneDrive checkout. The old folder was
cleared at that checkpoint; Windows retained its empty root because another process had it open. A later read found the old folder populated again. The active checkout and all subsequent generated files remain in the local workspace; no further OneDrive cleanup was performed.

## Reproduction and limits

See [packaging](../../../../packaging/README.md) for the build and frozen-worker
workflow commands, and [Testing](../../../../TESTING.md) for clean wheel smoke.
Build/test artifacts, recordings, exports and screenshots remain ignored.
A later rebuilt bundle passed the [native frozen review checks](../frozen-review/README.md)
for dropdowns, playback, seek, editing, search, history and twelve Windows picker
exports. Native import, close during a real CPU job and GUI resume also passed.
Installer wizard/startup shortcut/version upgrades, forced bundled Auto fallback,
another Windows machine and complete redistribution notices remain unverified.
No remote CI run occurred. Enumeration alone is not an inference check, and
workflow completion is not a speech-accuracy result.
