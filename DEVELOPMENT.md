# Development

Use Python 3.11 or 3.12. The main reader setup is in the [README](README.md).
For development, run from the repository root in a virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev,desktop,inference]'
```

The desktop extra supplies Qt. The inference extra supplies OpenVINO and GenAI;
NumPy may be installed transitively by those runtimes. Microphone recording is
not implemented, so sounddevice is not a desktop dependency.

## Local quality checks

```powershell
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -m 'not live' --basetemp .scratch/dev-tests
.\.venv\Scripts\python.exe -m build
.\.venv\Scripts\python.exe scripts/check_distributions.py dist
```

Use a fresh output directory for repeated builds, since the archive checker
expects exactly one wheel and one source archive. `build` and the pinned Hatchling
backend are included in the dev extra. Missing tooling is an environment failure;
a successful build still needs archive inspection and installation checks.

On Linux, use `python3 -m venv .venv` and `.venv/bin/python` in place of the
Windows launcher. See [testing](TESTING.md) for Qt and live-test boundaries.

## CI and dependencies

The local workflow definition runs quality checks on Linux Python 3.11/3.12 and
Windows Python 3.12. Qt workflow tests run on Windows with an offscreen platform.
Linux checks core tests and types; it does not establish desktop compatibility.
The package job builds a wheel from the source distribution, checks contents,
and installs the wheel into a fresh environment outside the checkout.
The installed smoke helper also checks both launchers, synthetic pause/resume,
and eight Raw/Balanced exports. It refuses an import from an editable checkout.

The workflow has read-only repository permissions and uses pinned commits for
[checkout](https://github.com/actions/checkout) and
[setup-python](https://github.com/actions/setup-python). Dependabot is configured
for weekly package/action updates, with OpenVINO and GenAI updates grouped.
These files do not establish a successful remote run or enable branch status
requirements. Repository settings need to be configured after real checks exist.

Keep recordings, transcripts, models, logs, and generated build output outside
publication candidates. Tests use synthetic media. New device behavior needs
both deterministic failure coverage and a bounded check on the intended hardware.

## Packaging

Wheels/source distributions are separate from the experimental Windows bundle.
See [packaging](packaging/README.md) for the GUI/worker recipe, one-host bundle
checks, and outstanding Windows/redistribution checks. The optional `bundle`
extra pins PyInstaller; build a Windows application on Windows.
No validated installer is currently provided.

## Standalone distribution boundary

The repository contains the application, tests, packaging, and documentation.
Local assistant instructions, skills, settings, and reports are ignored and
rejected by the distribution checker. Neither an assistant account nor a
particular coding environment is needed to install or use the application.

The [installed engine check](host-validation/evidence/2026-10-02/portable-engine/README.md)
ran a real CPU transcription from another directory, with a fresh library and
relocated model/tool files. It is one Windows host's evidence, not a guarantee
for every device or an accuracy result.
