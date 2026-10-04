# Testing

Run from the repository root after the [development setup](DEVELOPMENT.md).
The default suite uses synthetic media and no downloaded models or network.

```powershell
.\.venv\Scripts\python.exe -m pytest -m 'not live' --basetemp .pytest-tests
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
```

For coverage, add `--cov=npu_scribe --cov-report=term`. Use a new `--basetemp`
folder for a repeat when the previous run's files are in use.

## Coverage

- Core tests cover media validation, atomic storage/retries, chunk boundaries,
  checkpoints, device ordering, CLI dispatch and fallback, evaluation, and exports.
- Editing tests cover immutable source layers, revision history, locking, stale
  edits, write failures, provenance, and edited exports.
- `test_desktop.py` exercises Qt playback/seeking and real child-process mock
  jobs for import, pause/resume, search, editing, export, and reopen. Install the
  desktop extra to run it; otherwise that module is skipped. Tests set Qt's
  offscreen platform. The CI definition runs these checks on Windows.
- `test_packaging.py` checks source launchers and selection of the sibling frozen
  worker.
- `test_distributions.py` checks rejection of runtime files and unsafe archive
  paths. The CI package job also checks actual generated archives.
- `test_host_validation.py` statically checks the PowerShell harness.

The default fixture blocks sockets. The real-download test needs both the `live`
marker and an explicit environment flag; collection performs no network probes.
Windows decoder stubs run through Python. The symlink test skips when Windows
symlink privilege is unavailable.

## Source milestone and historical builds

The [implementation matrix](REQUIREMENTS.md) separates the current file-based
source v0.1 scope from the historical live-dictation plan. Existing installed-wheel
checks cover path-independent CPU speech and CPU text cleanup on one Windows
host.

The [package/installer](host-validation/evidence/2026-10-02/package-validation/README.md)
and [native frozen review](host-validation/evidence/2026-10-02/frozen-review/README.md)
checks apply to earlier executable hashes. The current AI-cleanup GUI, worker
and installer need a new build and execution checks before binary release.

## Optional live and hardware checks

A live acquisition test downloads the pinned model and requires network access:

```powershell
$env:NPU_SCRIBE_RUN_LIVE = '1'
.\.venv\Scripts\python.exe -m pytest -m live
Remove-Item Env:NPU_SCRIBE_RUN_LIVE
```

Report live results separately from the default suite. The environment flag
disables the suite's socket-denial fixture, so remove it before ordinary tests.

See the [Windows validation guide](host-validation/README.md) for model/device
smoke, FFmpeg, interruption/resume, and long-file endurance commands. Historical
reports specify the host, runtime, inputs, and measured results.

## Package validation

```powershell
.\.venv\Scripts\python.exe -m build
.\.venv\Scripts\python.exe scripts/check_distributions.py dist
```

The checker reads archives without extracting them, checks required source/modules,
and rejects checked runtime artifacts. Follow this with a clean wheel installation
and launcher smoke outside the checkout; the CI package job defines that sequence.
For a separate Windows environment using the current package version:

```powershell
py -3.12 -m venv .scratch/wheel-check
if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed.' }
.\.scratch\wheel-check\Scripts\python.exe -m pip install dist/npu_scribe-0.1.0-py3-none-any.whl
if ($LASTEXITCODE -ne 0) { throw 'Wheel installation failed.' }
.\.scratch\wheel-check\Scripts\python.exe scripts/smoke_installed.py .scratch/wheel-smoke
```

Use new environment/work directories for a repeat. This smoke uses the mock
model, checks installed launchers and eight exports after pause/resume, and
rejects imports from the editable checkout.

Frozen Windows testing is a separate gate in the [packaging guide](packaging/README.md).

## AI cleanup validation

The default suite tests automatic selected cleanup and Off, GPU-to-CPU fallback
with resolved provenance, separate summary output, and refusal of summary SRT.
It also tests publication, retained versions, original-file preservation,
heuristic fallback, cancellation, CLI exports, and a desktop child-process fixture
without network/model inference.

The [one-host real-model pilot](host-validation/evidence/2026-10-02/ai-cleanup/README.md)
records actual CPU/GPU/NPU cleanup on short synthetic statements and real desktop/
installed-wheel workflow checks. Its inputs/outputs are public synthetic text.
For a new host, explicitly download the cleanup model and use the
[user-guide commands](docs/USER_GUIDE.md#local-ai-cleanup) with known reference text;
inspect corrected phrases, names, quantities, negation, lists, and literal commands.

The [matched CPU/GPU/NPU cleanup comparison](host-validation/evidence/2026-10-02/ai-cleanup-comparison/README.md)
uses two ordered passes, fixed content/formatting checks, guard-aware outputs,
and separate warmup/loading measurements. `host-validation/Compare-AiCleanup.py`
and its synthetic fixtures reproduce the comparison without private lecture files.

The [one-host resource comparison](host-validation/evidence/2026-10-02/cleanup-resource-cost/README.md)
measures cleanup alongside a separate hardware graphics workload. It records
CPU, resident RAM, request time, and rendering slowdown for a fixed short request.


## File transcription and cleanup checkpoint

The [October 3 checkpoint report](host-validation/evidence/2026-10-03/file-cleanup-checkpoint/report.json)
records 204 passing offline tests (one skip, one live test deselected), lint,
formatting, typing, and package-content checks. A 72-second lecture exercised
CPU transcription, automatic GPU cleanup, source-selected summary notes and
exports. A separate installed-wheel check exercised real CPU speech, CPU cleanup
and summary outside the source folder. Original transcript hashes stayed intact.
Summary uses selected source passages after freeform candidates invented details.


## Dependency and formatting validation

The [October 3 follow-up report](host-validation/evidence/2026-10-03/validation-formatting/report.json)
records published-main dependency installation, real CPU/GPU/NPU paths and a
real desktop import/cleanup/formatting workflow. It also records layout guard,
cancellation, history, export, and model-reuse checks. Formatting checks enforce
complete passage coverage. Mixed/Structured can fall back to prose.

The [October 3 PR run](https://github.com/derek-l8/npu-scribe/actions/runs/37163191173)
passed packaging but failed Linux type checking and Windows test setup. The local
fixes need a new CI run. See [development](DEVELOPMENT.md#ci-and-dependencies).


## Full class lecture validation

The [full lecture report](host-validation/evidence/2026-10-03/full-lecture/report.json)
records a complete 47-minute supplied video, CPU tiny/base transcription,
GPU cleanup, separate formatting, exports, and sampled process-tree resource use.
Course media, screenshots, and text remain in ignored local storage; public
results contain only measurements and checks. Original media and source layers
are preserved. The cleanup boundary fix has regression tests for invented
endings, lost uncertainty wording, and added uncertainty labels.

## Remaining validation

- Real-device results come from one Windows computer. Other hardware and operating
  systems need their own runs; CI results for the local fixes are pending.
- A current installer still needs build and execution checks.
- Synthetic tests cover program behavior. Full-lecture word error rate needs a
  checked audio reference; cleanup fidelity, summary selection, and layout quality
  still require review.
- Typing and page-loading response were not measured. Invalid GPU counters left
  GPU-capacity usage unresolved.
