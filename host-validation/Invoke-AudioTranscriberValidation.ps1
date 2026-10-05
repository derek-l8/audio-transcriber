<#
.SYNOPSIS
    Windows validation for Audio Transcriber Milestone 1 (batch transcription).

.DESCRIPTION
    Non-administrator workflow. The intended one-command novice experience:

        Set-ExecutionPolicy -Scope Process Bypass
        .\Invoke-AudioTranscriberValidation.ps1 -SetupEnvironment -DownloadModels

    Parameters:
        -DataDirectory PATH        validation data root (default: per-user app data,
                                   never inside this repository)
        -OutputDirectory PATH      sanitized reports (default: reports\ beside script)
        -SetupEnvironment          opt-in network step: create/update a dedicated
                                   per-user virtual environment outside the repository
                                   and install the project plus pinned inference deps
        -DownloadModels            opt-in network step: download manifest-approved models
        -EvaluationManifest PATH   evaluate a candidate model on prepared public material
        -LongFile PATH             continuous ~60-minute media file for the automated
                                   interruption/resume exercise and endurance run
        -IncludeLegacyUiChecks     append round-1 owner-observed UI prompts

    Report guarantees: only measured fields are reported. Transcript text, audio,
    clipboard contents, usernames, credentials, and private absolute paths are
    never written. A silent/tone fixture is a runtime/device smoke test only —
    never an accuracy measurement.

.NOTES
    Every step executes on the local Windows host. Reports must be reviewed
    before sharing; a prior run on one host does not verify another host.
#>
[CmdletBinding()]
param(
    [string]$DataDirectory,
    [string]$OutputDirectory = "$PSScriptRoot\reports",
    [switch]$SetupEnvironment,
    [switch]$DownloadModels,
    [string]$EvaluationManifest,
    [string]$LongFile,
    [string]$FfmpegPath,
    [switch]$IncludeLegacyUiChecks
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$started = Get-Date
$checks = [System.Collections.Generic.List[object]]::new()
$metrics = [ordered]@{}

# --------------------------------------------------------------- environment resolution
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$appRoot = Join-Path $env:LOCALAPPDATA "audio-transcriber"
if (-not $DataDirectory) { $DataDirectory = Join-Path $appRoot "validation-data" }
$venvPath = Join-Path $appRoot "validation-venv"
New-Item -ItemType Directory -Force -Path $DataDirectory | Out-Null
$ffmpegArgs = @()
if ($FfmpegPath) { $ffmpegArgs = @("--ffmpeg", $FfmpegPath) }

function Add-Check([string]$Id, [string]$Status, [string]$Detail) {
    $checks.Add([ordered]@{ id = $Id; status = $Status; detail = $Detail })
}

function Sanitize([string]$Text) {
    # Strip absolute paths that could contain the username or private layout.
    return ($Text -replace "[A-Za-z]:\\[^\s:""]+", "<path>")
}

function New-TemporaryOutputFile {
    return [System.IO.Path]::GetTempFileName()
}

<#
.SYNOPSIS
    Runs a process with enforced timeout, capturing stdout, stderr, and exit code
    without risking pipe deadlocks (asynchronous reads drain both pipes).
#>
function Start-TrackedProcess {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [int]$TimeoutSeconds = 7200,
        [string]$WorkingDirectory = $repoRoot
    )
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $FilePath
    foreach ($arg in $ArgumentList) { [void]$psi.ArgumentList.Add($arg) }
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $process = [System.Diagnostics.Process]::Start($psi)
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $timedOut = $false
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        $timedOut = $true
        # Kill the whole process tree; fall back to a direct kill.
        & taskkill /PID $process.Id /T /F 2>$null | Out-Null
        try {
            if (-not $process.HasExited) { $process.Kill() }
        } catch { }
        $process.WaitForExit(10000) | Out-Null
    }
    return [pscustomobject]@{
        exit     = $(if ($timedOut) { $null } else { $process.ExitCode })
        timedOut = $timedOut
        stdout   = $stdoutTask.GetAwaiter().GetResult()
        stderr   = $stderrTask.GetAwaiter().GetResult()
    }
}

function Get-ProcessTreeWorkingSetBytes {
    param([int]$RootProcessId)
    # A Windows venv python.exe can be a small launcher for the real worker.
    # Sample its descendants too, or the report can understate memory severely.
    $pending = [System.Collections.Generic.Queue[int]]::new()
    $seen = [System.Collections.Generic.HashSet[int]]::new()
    $pending.Enqueue($RootProcessId)
    [long]$total = 0
    try {
        while ($pending.Count -gt 0) {
            $currentProcessId = $pending.Dequeue()
            if (-not $seen.Add($currentProcessId)) { continue }
            $process = Get-Process -Id $currentProcessId -ErrorAction SilentlyContinue
            if ($process) { $total += $process.WorkingSet64 }
            $children = @(Get-CimInstance Win32_Process `
                -Filter "ParentProcessId=$currentProcessId" -ErrorAction Stop)
            foreach ($child in $children) { $pending.Enqueue([int]$child.ProcessId) }
        }
        return $total
    } catch {
        return $null
    }
}

function Invoke-CliStep {
    param(
        [string]$Id,
        [string[]]$CliArguments,
        [int]$TimeoutSeconds = 3600,
        [string[]]$ParsePrefixes = @()
    )
    $tracked = Start-TrackedProcess -FilePath $PythonExe `
        -ArgumentList (@("-m", "audio_transcriber.cli") + $CliArguments) `
        -TimeoutSeconds $TimeoutSeconds
    $combined = ($tracked.stdout + "`n" + $tracked.stderr)
    $values = [ordered]@{}
    foreach ($prefix in $ParsePrefixes) {
        $match = [regex]::Match($combined, "(?m)^\s*$prefix`:\s*(.+)$")
        if ($match.Success) { $values[$prefix] = $match.Groups[1].Value.Trim() }
    }
    if ($tracked.timedOut) {
        Add-Check $Id "timeout" "exceeded ${TimeoutSeconds}s limit"
    } elseif ($tracked.exit -eq 0) {
        Add-Check $Id "pass" ($(Sanitize ($values.Values -join "; ")))
    } else {
        $lastLine = (Sanitize $combined).Trim() -split "`n" |
            Where-Object { $_ -match "\S" } | Select-Object -Last 1
        Add-Check $Id "fail" $lastLine
    }
    return [pscustomobject]@{
        exit     = $tracked.exit
        timedOut = $tracked.timedOut
        values   = $values
        raw      = $combined
    }
}

# ------------------------------------------------------------------- 0. python runtime
$systemPython = Get-Command python -ErrorAction SilentlyContinue
$venvPython = Join-Path $venvPath "Scripts\python.exe"
if (-not $systemPython) {
    Add-Check "python" "fail" "python not found on PATH; install Python 3.14 from python.org (per-user install is sufficient)"
    Write-Host "Python is required. Install it, reopen PowerShell, and rerun."
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    $earlyReport = [ordered]@{ schema_version = 3; checks = $checks; metrics = $metrics }
    $earlyReport | ConvertTo-Json -Depth 8 |
        Set-Content -Encoding UTF8 (Join-Path $OutputDirectory "audio-transcriber-validation.json")
    return
}
if ($SetupEnvironment -or (Test-Path $venvPython)) {
    if (-not (Test-Path $venvPython)) {
        New-Item -ItemType Directory -Force -Path $appRoot | Out-Null
        & $systemPython.Source -m venv $venvPath
        if ($LASTEXITCODE -ne 0) {
            Add-Check "python" "fail" "virtual-environment creation failed"
        }
    }
    $pythonExeCandidate = $venvPython
} else {
    $pythonExeCandidate = $systemPython.Source
}
if (-not (Test-Path $pythonExeCandidate)) {
    Add-Check "python" "fail" "resolved interpreter not found: $pythonExeCandidate"
    Write-Host "Run again with -SetupEnvironment to create the validation environment."
    return
}
$PythonExe = $pythonExeCandidate

$pyVersion = (& $PythonExe --version 2>&1 | Out-String).Trim()
if ("$pyVersion" -match "^Python 3\.14\.") {
    Add-Check "python-version" "pass" $pyVersion
} else {
    Add-Check "python-version" "fail" "$pyVersion; Python 3.14 is required"
}

# ------------------------------------------------- 1. optional environment setup first
# Setup runs before import verification so a freshly created per-user venv is
# populated; without -SetupEnvironment nothing network-dependent ever happens.
if ($SetupEnvironment) {
    [void](Start-TrackedProcess -FilePath $PythonExe -ArgumentList @(
        "-m", "pip", "install", "--quiet", "--upgrade", "pip"
    ) -TimeoutSeconds 600)
    $install = Start-TrackedProcess -FilePath $PythonExe -ArgumentList @(
        "-m", "pip", "install", "--quiet",
        "--editable", $repoRoot,
        "openvino==2026.4.0", "openvino-genai==2026.4.0.0"
    ) -TimeoutSeconds 1800
    if ($install.timedOut) {
        Add-Check "setup-environment" "timeout" "dependency installation exceeded 1800 s"
    } elseif ($install.exit -eq 0) {
        Add-Check "setup-environment" "pass" "project and pinned inference deps installed"
    } else {
        $lastSetupLines = (($install.stderr -split "`n") | Select-Object -Last 2) -join " "
        Add-Check "setup-environment" "fail" (Sanitize $lastSetupLines)
    }
} else {
    Add-Check "setup-environment" "skip" "-SetupEnvironment not supplied; no changes made"
}

# ------------------------------------------------------- 2. package/import verification
$importProbeScript = @'
import json
mods = {}
for m in ("audio_transcriber", "openvino", "openvino_genai"):
    try:
        mods[m] = getattr(__import__(m), "__version__", "installed")
    except Exception:
        mods[m] = None
print(json.dumps(mods))
'@
$importProbe = Start-TrackedProcess -FilePath $PythonExe `
    -ArgumentList @("-c", $importProbeScript) -TimeoutSeconds 120
$mods = $null
try { $mods = $importProbe.stdout | ConvertFrom-Json } catch { }
if ($null -eq $mods) {
    $missing = @("audio_transcriber", "openvino", "openvino_genai")
    Add-Check "imports" "fail" (
        "Could not verify imports. Recovery: rerun with -SetupEnvironment " +
        "(creates a per-user environment at <LocalAppData>\audio-transcriber\validation-venv " +
        "and installs '.[inference]'). No Administrator rights are needed."
    )
    Write-Host "Recovery: .\Invoke-AudioTranscriberValidation.ps1 -SetupEnvironment -DownloadModels"
} else {
    $missing = @($mods.PSObject.Properties | Where-Object { $null -eq $_.Value })
    if ($missing.Count -eq 0) {
        Add-Check "imports" "pass" (
            "audio_transcriber $($mods.audio_transcriber); openvino $($mods.openvino); " +
            "openvino_genai $($mods.openvino_genai)"
        )
        $metrics["python"] = "$pyVersion"
        $metrics["package_versions"] = [ordered]@{
            audio_transcriber      = "$($mods.audio_transcriber)"
            openvino        = "$($mods.openvino)"
            openvino_genai  = "$($mods.openvino_genai)"
        }
    } elseif ($SetupEnvironment) {
        Add-Check "imports" "fail" (
            "still missing after setup: " + (($missing | ForEach-Object Name) -join ", ")
        )
    } else {
        Add-Check "imports" "fail" (
            "missing: " + (($missing | ForEach-Object Name) -join ", ") +
            ". Recovery: rerun with -SetupEnvironment."
        )
        Write-Host "Recovery: .\Invoke-AudioTranscriberValidation.ps1 -SetupEnvironment -DownloadModels"
    }
}
$environmentReady = (Test-Path variable:mods) -and ($null -ne $mods) -and ($missing.Count -eq 0)

# ------------------------------------------------------------------ 3. device inventory
$deviceProbe = Start-TrackedProcess -FilePath $PythonExe -ArgumentList @(
    "-c", "import json,openvino as ov;print(json.dumps(sorted(set(d.split('.')[0] for d in ov.Core().available_devices))))"
) -TimeoutSeconds 120
$devices = @()
try { $devices = @(($deviceProbe.stdout | ConvertFrom-Json)) } catch { }
$devices = @($devices | Where-Object { $_ })
if ($devices.Count -eq 0) {
    Add-Check "openvino-devices" "fail" "no OpenVINO devices enumerated; install the 'inference' extra (-SetupEnvironment) and check drivers"
} else {
    Add-Check "openvino-devices" "pass" ("enumerated: " + ($devices -join ", "))
}
foreach ($optional in @("GPU", "NPU")) {
    if ($devices -notcontains $optional) {
        Add-Check "device-$optional" "unavailable" "not enumerated by OpenVINO on this machine"
    }
}
if (($devices -notcontains "CPU") -and ($devices.Count -gt 0)) {
    Add-Check "device-cpu" "unavailable" "CPU not enumerated; relying on other devices"
}

# ------------------------------------------------------------ 4. model integrity/download
if ($DownloadModels) {
    $list = Invoke-CliStep -Id "models-list" -CliArguments @("models", "list") -TimeoutSeconds 120
    foreach ($modelId in @("whisper-tiny.en-int4-ov", "whisper-base.en-int4-ov")) {
        [void](Invoke-CliStep -Id "model-$modelId" `
            -CliArguments @("--data-dir", $DataDirectory, "models", "download", $modelId) `
            -TimeoutSeconds 3600)
    }
    $revisionProbeScript = @'
import json
from audio_transcriber.acquisition import MANIFEST
print(json.dumps({k: v.revision for k, v in MANIFEST.items()}))
'@
    $revisionProbe = Start-TrackedProcess -FilePath $PythonExe `
        -ArgumentList @("-c", $revisionProbeScript) -TimeoutSeconds 120
    try {
        $metrics["model_revisions"] = $revisionProbe.stdout | ConvertFrom-Json
    } catch { }
} else {
    Add-Check "model-download" "skip" "-DownloadModels not supplied; no network action taken"
}
$verifyTinyScript = @'
import sys
from pathlib import Path
from audio_transcriber.acquisition import get_spec, verify_installed
model = get_spec("whisper-tiny.en-int4-ov")
raise SystemExit(0 if verify_installed(Path(sys.argv[1]) / "models", model) else 1)
'@
$tinyProbe = Start-TrackedProcess -FilePath $PythonExe `
    -ArgumentList @("-c", $verifyTinyScript, $DataDirectory) -TimeoutSeconds 120
$tinyReady = (-not $tinyProbe.timedOut) -and ($tinyProbe.exit -eq 0)
if ($tinyReady) {
    Add-Check "model-tiny-integrity" "pass" "installed files match pinned sizes and SHA-256 hashes"
} elseif ($DownloadModels) {
    Add-Check "model-tiny-integrity" "fail" "downloaded tiny model failed verification"
} else {
    Add-Check "model-tiny-integrity" "skip" "tiny model is not installed or verified"
}

# ------------------------------------- 5. valid-fixture device smoke tests (runtime only)
$fixture = Join-Path $DataDirectory "fixture-smoke.wav"
$fixtureScript = @'
import wave
from pathlib import Path

path = r"__FIXTURE__"
with wave.open(path, "wb") as handle:
    handle.setnchannels(1)
    handle.setsampwidth(2)
    handle.setframerate(16000)
    handle.writeframes(b"\x00\x00" * 160000)
from audio_transcriber.media import inspect_pcm_wav
rate, channels, frames = inspect_pcm_wav(Path(path))
assert (rate, channels, frames) == (16000, 1, 160000), (rate, channels, frames)
print("fixture-ok")
'@.Replace("__FIXTURE__", $fixture)
$fixtureProbe = Start-TrackedProcess -FilePath $PythonExe `
    -ArgumentList @("-c", $fixtureScript) -TimeoutSeconds 120
if ($fixtureProbe.timedOut -or $fixtureProbe.exit -ne 0 -or $fixtureProbe.stdout -notmatch "fixture-ok") {
    Add-Check "smoke-fixture" "fail" "valid mono 16 kHz WAV could not be created/inspected"
    Write-Host "Fixture generation failed; aborting device smoke tests."
} else {
    Add-Check "smoke-fixture" "pass" "RIFF/WAVE fixture validated through inspect_pcm_wav (silence: runtime/device smoke only, NOT accuracy)"
    foreach ($device in $devices) {
        $stepId = "transcribe-$device"
        if ($tinyReady) {
            $run = Invoke-CliStep -Id $stepId -ParsePrefixes @("session", "status",
                "actual_device", "requested_device", "chunks_completed", "fallback_events") `
                -CliArguments (@("--data-dir", $DataDirectory, "transcribe", "--cleanup", "off", "--formatting", "off", $fixture,
                    "--model", "whisper-tiny.en-int4-ov", "--device", $device,
                    "--chunk-seconds", "30", "--overlap-seconds", "1") + $ffmpegArgs) `
                -TimeoutSeconds 900
            $requested = $run.values["requested_device"]
            $actual = $run.values["actual_device"]
            if ($run.exit -eq 0 -and $requested -eq $device -and $actual -eq $device -and
                $run.values["status"] -eq "ready" -and $run.values["fallback_events"] -eq "0") {
                $metrics["device_smoke_$device"] = [ordered]@{
                    requested = $requested; actual = $actual
                    status = $run.values["status"]
                }
                Add-Check "$stepId-verified" "pass" "requested device binding completed; reported device: $actual"
            } elseif ($run.exit -eq 0) {
                Add-Check "$stepId-verified" "fail" "requested=$device but session reports requested=$requested actual=$actual status=$($run.values['status']) fallback_events=$($run.values['fallback_events'])"
            }
        } else {
            Add-Check $stepId "skip" "verified tiny model is unavailable"
        }
    }
}

# ------------------------------- 6. automated interruption + explicit resume (+ endurance)
if ($LongFile) {
    if (-not (Test-Path $LongFile)) {
        Add-Check "resume-test" "fail" "supplied long file was not found"
        Add-Check "endurance-60min" "fail" "supplied long file was not found"
    } else {
        $before = @(Get-ChildItem -Directory (Join-Path $DataDirectory "lectures") -ErrorAction SilentlyContinue |
            ForEach-Object Name)
        $outFile = New-TemporaryOutputFile
        $errFile = New-TemporaryOutputFile
        $proc = Start-Process -FilePath $PythonExe `
            -ArgumentList (@("-m","audio_transcriber.cli","--data-dir",$DataDirectory,
                "transcribe", "--cleanup", "off", "--formatting", "off",$LongFile,"--model","whisper-base.en-int4-ov",
                "--device","auto","--chunk-seconds","30","--overlap-seconds","1") + $ffmpegArgs) `
            -RedirectStandardOutput $outFile -RedirectStandardError $errFile `
            -WorkingDirectory $repoRoot -PassThru -NoNewWindow

        # Bounded wait for a NEW session's first durable checkpoint.
        $deadline = (Get-Date).AddMinutes(15)
        $newSession = $null
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 5
            $now = @(Get-ChildItem -Directory (Join-Path $DataDirectory "lectures") -ErrorAction SilentlyContinue |
                ForEach-Object Name)
            $candidates = @($now | Where-Object { $before -notcontains $_ })
            foreach ($candidate in $candidates) {
                $checkpointPath = Join-Path $DataDirectory "lectures\$candidate\checkpoint.json"
                if ((Test-Path $checkpointPath) -and
                    ((Get-Content $checkpointPath -Raw | ConvertFrom-Json).completed_chunks.Count -ge 1)) {
                    $newSession = $candidate
                    break
                }
            }
            if ($newSession) { break }
            if ($proc.HasExited) { break }
        }

        if (-not $newSession) {
            if (-not $proc.HasExited) {
                & taskkill /PID $proc.Id /T /F 2>$null | Out-Null
            }
            Add-Check "resume-test" "fail" "no durable checkpoint appeared within 15 minutes"
        } else {
            # Terminate mid-run, leaving the durable checkpoint behind.
            if (-not $proc.HasExited) {
                & taskkill /PID $proc.Id /T /F 2>$null | Out-Null
                $proc.WaitForExit(30000) | Out-Null
                Start-Sleep -Seconds 2
            }
            $checkpointPath = Join-Path $DataDirectory "lectures\$newSession\checkpoint.json"
            $preKillCompleted = @()
            if (Test-Path $checkpointPath) {
                $preKillCompleted = @((Get-Content $checkpointPath -Raw |
                    ConvertFrom-Json).completed_chunks)
            }
            if ($preKillCompleted.Count -eq 0) {
                Add-Check "resume-test" "fail" "checkpoint did not survive termination"
            } else {
                $resume = Invoke-CliStep -Id "resume-test" -ParsePrefixes @(
                    "session", "status", "actual_device", "chunks_completed") `
                    -CliArguments (@("--data-dir", $DataDirectory,
                        "resume", "--cleanup", "off", "--formatting", "off", $newSession,
                        "--model", "whisper-base.en-int4-ov", "--device", "auto",
                        "--chunk-seconds", "30", "--overlap-seconds", "1") + $ffmpegArgs) `
                    -TimeoutSeconds 21600
                $resumedStatus = $resume.values["status"]
                $metrics["interruption_resume"] = [ordered]@{
                    session_id            = $newSession
                    completed_before_kill = $preKillCompleted.Count
                    resumed_status        = "$resumedStatus"
                    actual_device         = "$($resume.values['actual_device'])"
                }
                if ($resume.exit -eq 0 -and "$resumedStatus" -eq "ready") {
                    Add-Check "resume-completed-chunks-once" "pass" (
                        "resumed session reached ready; pre-kill completed chunks: " +
                        "$($preKillCompleted.Count) (chunk_records unique/monotonic checked below)"
                    )
                    # Verify no chunk was processed twice after resume.
                    $recordsScript = @'
import json
from pathlib import Path
session = json.loads(Path(r"__SESSION_JSON__").read_text(encoding="utf-8"))
indexes = [record["index"] for record in session["diagnostics"]["chunk_records"]]
assert indexes == sorted(set(indexes)), indexes
print("unique", len(indexes))
'@.Replace("__SESSION_JSON__", (Join-Path $DataDirectory "lectures\$newSession\session.json"))
                    $recordsProbe = Start-TrackedProcess -FilePath $PythonExe `
                        -ArgumentList @("-c", $recordsScript) -TimeoutSeconds 120
                    if ("$($recordsProbe.stdout)" -match "unique") {
                        Add-Check "chunks-not-repeated" "pass" "chunk indexes are unique and ordered"
                    } else {
                        Add-Check "chunks-not-repeated" "fail" "duplicate or unordered chunk records"
                    }
                }
            }
        }

        # Endurance: one continuous pass over the same long file.
        $enduranceOut = New-TemporaryOutputFile
        $enduranceErr = New-TemporaryOutputFile
        $enduranceStart = Get-Date
        $enduranceProc = Start-Process -FilePath $PythonExe `
            -ArgumentList (@("-m","audio_transcriber.cli","--data-dir",$DataDirectory,
                "transcribe", "--cleanup", "off", "--formatting", "off",$LongFile,"--model","whisper-base.en-int4-ov",
                "--device","auto","--chunk-seconds","30","--overlap-seconds","1") + $ffmpegArgs) `
            -RedirectStandardOutput $enduranceOut -RedirectStandardError $enduranceErr `
            -WorkingDirectory $repoRoot -PassThru -NoNewWindow
        [long]$peakTreeWsBytes = 0
        $memorySamples = 0
        $deadline = $enduranceStart.AddHours(6)
        while (-not $enduranceProc.HasExited -and (Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 10
            $sample = Get-ProcessTreeWorkingSetBytes -RootProcessId $enduranceProc.Id
            if ($null -ne $sample -and $sample -gt 0) {
                $memorySamples++
                if ($sample -gt $peakTreeWsBytes) { $peakTreeWsBytes = $sample }
            }
        }
        $timedOutEndurance = -not $enduranceProc.HasExited
        if ($timedOutEndurance) {
            & taskkill /PID $enduranceProc.Id /T /F 2>$null | Out-Null
        }
        $minutes = [math]::Round(((Get-Date) - $enduranceStart).TotalMinutes, 1)
        if ($timedOutEndurance) {
            Add-Check "endurance-60min" "timeout" "exceeded the 6-hour limit"
        } elseif ($enduranceProc.ExitCode -eq 0) {
            $summary = (Get-Content $enduranceOut -Raw)
            $actualDev = [regex]::Match($summary, "(?m)^actual_device:\s*(.+)$").Groups[1].Value.Trim()
            $chunks = [regex]::Match($summary, "(?m)^chunks_completed:\s*(\d+)\s*$").Groups[1].Value.Trim()
            $metrics["endurance"] = [ordered]@{
                wall_minutes = $minutes
                chunks_completed = $chunks
                actual_device = $actualDev
                sampled_peak_working_set_mb = $(
                    if ($memorySamples -gt 0) {
                        [math]::Round($peakTreeWsBytes / 1MB, 1)
                    } else { $null }
                )
                memory_scope = $(
                    if ($memorySamples -gt 0) { "process tree, sampled every 10 seconds" }
                    else { "unverified: process tree could not be sampled" }
                )
            }
            Add-Check "endurance-60min" "pass" "completed in $minutes min; $chunks chunks"
            if ($memorySamples -eq 0) {
                Add-Check "endurance-memory" "unverified" "process tree could not be sampled"
            }
        } else {
            Add-Check "endurance-60min" "fail" "exit $($enduranceProc.ExitCode) after $minutes min"
        }
        Remove-Item $outFile, $errFile, $enduranceOut, $enduranceErr -Force -ErrorAction SilentlyContinue
    }
} else {
    Add-Check "resume-test" "skip" "-LongFile not supplied"
    Add-Check "endurance-60min" "skip" "-LongFile not supplied"
}

# ------------------------------------------------------------------ 7. evaluation manifest
if ($EvaluationManifest) {
    if (-not (Test-Path $EvaluationManifest)) {
        Add-Check "evaluation" "fail" "manifest not found"
    } else {
        $eval = Invoke-CliStep -Id "evaluation" `
            -CliArguments @("--data-dir", $DataDirectory, "evaluate",
                $EvaluationManifest, "--model", "whisper-base.en-int4-ov", "--device", "auto") `
            -TimeoutSeconds 14400
        if ($eval.exit -eq 0) {
            $latestReport = Get-ChildItem (Join-Path $DataDirectory "evaluation\reports") `
                -Filter *.report.json -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime | Select-Object -Last 1
            if ($latestReport) {
                $evalReport = Get-Content $latestReport.FullName -Raw | ConvertFrom-Json
                $werRows = @($evalReport.results | Where-Object { $null -ne $_.wer })
                if ($werRows.Count -gt 0) {
                    $metrics["evaluation_wer_cer"] = @(
                        $werRows | ForEach-Object {
                            [ordered]@{ case = $_.case_id; wer = $_.wer; cer = $_.cer; rtf = $_.rtf }
                        }
                    )
                }
                $metrics["selection"] = $evalReport.selection
            }
        }
    }
} else {
    Add-Check "evaluation" "skip" "-EvaluationManifest not supplied; no WER/CER claimed"
}

# ------------------------------------------------------------ 8. optional legacy UI prompts
if ($IncludeLegacyUiChecks) {
    function Read-Choice([string]$Prompt) {
        $answer = Read-Host "$Prompt [pass/fail/skip]"
        if ($answer -notin @("pass", "fail", "skip")) { return "unverified" }
        return $answer
    }
    foreach ($app in @("Word", "Notion", "Codex")) {
        Add-Check "insertion-$($app.ToLower())" `
            (Read-Choice "Did insertion, clipboard restoration, and copy fallback work in $app?") `
            "owner-observed ordinary field"
    }
    Add-Check "microphone" (Read-Choice "Did microphone activation, visible state, stop, and playback work?") "owner-observed"
    Add-Check "tray" (Read-Choice "Are tray states and exit behavior correct?") "owner-observed"
}

# ---------------------------------------------------------------------------- 9. report
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$report = [ordered]@{
    schema_version       = 3
    generated_utc        = (Get-Date).ToUniversalTime().ToString("o")
    duration_seconds     = [math]::Round(((Get-Date) - $started).TotalSeconds, 2)
    scope_note           = "Silence fixtures prove runtime/device execution only; never accuracy."
    privacy              = "No audio, transcript text, clipboard content, username, credential, or absolute personal path is included. Review before sharing."
    metrics              = $metrics
    checks               = $checks
}
$jsonPath = Join-Path $OutputDirectory "audio-transcriber-validation.json"
$mdPath = Join-Path $OutputDirectory "audio-transcriber-validation.md"
$report | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $jsonPath
@("# Audio Transcriber Windows validation", "",
    "Review for private content before returning.", "") +
($checks | ForEach-Object { "- **$($_.status)** ``$($_.id)`` - $($_.detail)" }) |
Set-Content -Encoding UTF8 $mdPath
Write-Host "Reports written. Review them before returning:"
Write-Host $jsonPath
Write-Host $mdPath
