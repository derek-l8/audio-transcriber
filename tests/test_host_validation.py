"""Static contract tests for the owner-run Windows PowerShell harness.

PowerShell cannot execute in this Linux sandbox, so these tests pin the
harness's structure and safety properties by source inspection. Actual Windows
execution remains pending and must come from an owner-run report.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

HARNESS = Path(__file__).parent.parent / "host-validation" / "Invoke-NpuScribeValidation.ps1"


@pytest.fixture(scope="module")
def script() -> str:
    return HARNESS.read_text(encoding="utf-8")


def test_harness_declares_required_parameters(script: str) -> None:
    for name in (
        "DataDirectory",
        "OutputDirectory",
        "SetupEnvironment",
        "DownloadModels",
        "EvaluationManifest",
        "LongFile",
        "FfmpegPath",
    ):
        assert re.search(rf"\[switch\]\${name}|\[string\]\${name}", script), name


def test_ffmpeg_path_threads_through_every_media_run(script: str) -> None:
    assert 'if ($FfmpegPath) { $ffmpegArgs = @("--ffmpeg", $FfmpegPath) }' in script
    # transcribe (smoke + endurance) and resume must all append the same args.
    assert script.count("+ $ffmpegArgs") >= 3


def test_no_undefined_environment_variable_for_data_dir(script: str) -> None:
    # The old bug: --data-dir received $env:NPUSCRIBE_VALIDATION_DATA, never set.
    assert "NPUSCRIBE_VALIDATION_DATA" not in script
    assert "$DataDirectory = Join-Path $appRoot" in script


def test_data_lives_outside_the_repository(script: str) -> None:
    assert "LOCALAPPDATA" in script
    assert 'Join-Path $appRoot "validation-data"' in script


def test_repo_root_resolved_from_script_location(script: str) -> None:
    assert '$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path' in script


def test_single_resolved_python_executable(script: str) -> None:
    assert "$PythonExe = $pythonExeCandidate" in script
    # Every CLI invocation must go through Start-TrackedProcess with $PythonExe.
    bare_invocations = re.findall(r"&\s+python\b", script)
    assert not bare_invocations, f"bare python invocations remain: {len(bare_invocations)}"
    assert script.count("-FilePath $PythonExe") >= 3


def test_supported_python_version_check(script: str) -> None:
    assert re.search(r'-match "3\\\.\(11\|12\)"', script), "version gate missing"


def test_import_checks_before_validation(script: str) -> None:
    for module in ("npu_scribe", "openvino", "openvino_genai"):
        assert f'"{module}"' in script
    assert "Recovery: rerun with -SetupEnvironment" in script or (
        "Recovery:" in script and "-SetupEnvironment" in script
    )


def test_setup_environment_is_the_only_network_install_path(script: str) -> None:
    start = script.index("1. optional environment setup")
    end = script.index("2. package/import verification")
    pip_section = script[start:end]
    assert "pip" in pip_section
    assert "-SetupEnvironment" in pip_section
    # Setup must run BEFORE import verification so a fresh venv is populated.
    assert start < script.index("2. package/import verification")
    before_branch = script[:start]
    assert "pip install" not in before_branch.replace("install the project plus pinned", "")


def test_run_cli_enforces_timeout_via_process_wait(script: str) -> None:
    assert "WaitForExit($TimeoutSeconds * 1000)" in script
    assert "taskkill /PID $process.Id /T /F" in script
    assert "RedirectStandardOutput = $true" in script
    assert "ReadToEndAsync()" in script, "async pipe drains prevent deadlocks"
    assert '"timeout"' in script, "timeouts must be reported distinctly"
    # Timeouts are actually threaded through to every long-running step.
    for usage in ("TimeoutSeconds 3600", "TimeoutSeconds 21600", "TimeoutSeconds 14400"):
        assert usage in script


def test_fixture_is_valid_wav_validated_through_media_boundary(script: str) -> None:
    fixture_section = script[
        script.index("5. valid-fixture") : script.index("6. automated interruption")
    ]
    assert "wave.open" in fixture_section
    assert "setnchannels(1)" in fixture_section
    assert "setframerate(16000)" in fixture_section
    assert "inspect_pcm_wav" in fixture_section
    assert "WriteAllBytes" not in fixture_section, "raw zero bytes without a header are invalid"
    assert "NOT accuracy" in fixture_section or "never accuracy" in script.lower()


def test_devices_come_from_openvino_enumeration(script: str) -> None:
    device_section = script[
        script.index("3. device inventory") : script.index("4. model integrity")
    ]
    assert "available_devices" in device_section
    assert 'foreach ($device in @("CPU", "GPU", "NPU"))' not in script
    assert "-notcontains $optional" in script or "unavailable" in device_section


def test_actual_device_provenance_is_parsed_not_inferred(script: str) -> None:
    assert '"actual_device"' in script
    assert "requested=$device but provenance reports actual=" in script or (
        "provenance reports actual" in script
    )
    # NPU success requires provenance equality; no unconditional pass on exit code alone.


def test_interruption_and_resume_are_automated(script: str) -> None:
    resume_section = script[
        script.index("6. automated interruption") : script.index("7. evaluation manifest")
    ]
    assert "resume" in resume_section
    assert 'Invoke-CliStep -Id "resume-test"' in resume_section
    assert "completed_chunks.Count -ge 1" in resume_section, "bounded checkpoint wait"
    assert "AddMinutes(15)" in resume_section, "no unconditional sleeps as waits"
    assert "Locate the printed session id" not in resume_section


def test_report_records_only_measured_metrics(script: str) -> None:
    report_section = script[script.index("9. report") :]
    assert re.search(r"metrics\s*=\s*\$metrics", report_section)
    # WER/CER only from a real evaluation report file.
    assert "evaluation_wer_cer" in script
    assert "wer_rows" in script.lower() or "werRows" in script


def test_peak_working_set_sampled_during_endurance(script: str) -> None:
    assert "WorkingSet64" in script
    assert "sampled_peak_working_set_mb" in script
