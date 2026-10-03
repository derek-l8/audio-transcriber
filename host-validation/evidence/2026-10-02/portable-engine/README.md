# Installed standalone engine validation

Validated locally on Windows x64, 2026-10-02. Built the wheel from the source
archive, checked both archives for runtime/private/assistant artifacts, and
installed it in an isolated environment. No commit, push, or published release.

The installed launchers passed the synthetic pause/resume and eight-export
smoke check. A separate real inference check used a new working directory
outside the checkout, a fresh library, relocated verified model files, copied
FFmpeg on a minimal PATH, and a public 72-second Yale speech fixture. Input,
library, and tool paths contained spaces. PYTHONPATH, PYTHONHOME, and VIRTUAL_ENV
were removed; Python was absent from PATH. No saved desktop settings were used.

The CLI was invoked with only `transcribe` and the relative MP3 path. Its default
real tiny.en model and CPU completed all three chunks, with nonempty text and
all four export formats. FFmpeg was discovered without `--ffmpeg`.

This verifies installation, path independence, decoder discovery, and real CPU
execution on one host. It does not establish accuracy, performance across devices,
or compatibility with every OS. See [results](results.json).
