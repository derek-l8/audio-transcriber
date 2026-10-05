# Audio Transcriber and Python 3.14 checkpoint

The app, Python package, commands, build files, and guides now use Audio Transcriber.
The Windows installer creates a desktop shortcut by default. That shortcut opened
the installed app without command-line arguments. Startup at sign-in stays optional.
Existing libraries are reused, and the previous data-folder override remains accepted.

On Windows x64 with Python 3.14.6, 284 offline tests passed, along with lint, type,
document-link, package, and installer checks. Installed transcription on CPU and
cleanup/formatting on GPU completed using a 10-second clip of the supplied recording.
GUI playback, editing, search, history, and 12 exports passed. Reinstall and uninstall
preserved validation libraries; uninstall removed the shortcut and installed files.

See [the results](report.json) for versions, hashes, and check details. Private audio,
text, environments, and installers remain outside Git. The earlier
[device comparisons](../../../../docs/TESTED_DECISIONS.md) retain their original
runtime versions; this checkpoint did not repeat those benchmarks.
