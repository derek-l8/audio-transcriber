#Requires -Version 7.0
<#
.SYNOPSIS
    Run a continuous long-file CPU transcription and record process-tree memory.

.DESCRIPTION
    This is a host-only endurance measurement. It writes a path-free JSON report
    under host-validation/reports by default. It does not measure speech accuracy.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$LongFile,
    [string]$DataDirectory = (Join-Path $env:LOCALAPPDATA "npu-scribe\validation-data"),
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "reports"),
    [string]$PythonExe,
    [string]$Model = "whisper-base.en-int4-ov",
    [int]$TimeoutMinutes = 30,
    [int]$SampleSeconds = 10
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $PythonExe) { $PythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe" }
$source = (Resolve-Path -LiteralPath $LongFile).Path
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python interpreter not found"
}
if ($TimeoutMinutes -le 0 -or $SampleSeconds -le 0) {
    throw "TimeoutMinutes and SampleSeconds must be positive"
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

function Get-TreeWorkingSetBytes([int]$RootProcessId) {
    $pending = [System.Collections.Generic.Queue[int]]::new()
    $seen = [System.Collections.Generic.HashSet[int]]::new()
    $pending.Enqueue($RootProcessId)
    [long]$total = 0
    [int]$count = 0
    while ($pending.Count -gt 0) {
        $currentProcessId = $pending.Dequeue()
        if (-not $seen.Add($currentProcessId)) { continue }
        $process = Get-Process -Id $currentProcessId -ErrorAction SilentlyContinue
        if ($process) {
            $total += $process.WorkingSet64
            $count++
        }
        $children = @(Get-CimInstance Win32_Process `
            -Filter "ParentProcessId=$currentProcessId" -ErrorAction Stop)
        foreach ($child in $children) { $pending.Enqueue([int]$child.ProcessId) }
    }
    return [pscustomobject]@{ bytes = $total; process_count = $count }
}

function Median([double[]]$Values) {
    if ($Values.Count -eq 0) { return $null }
    $ordered = @($Values | Sort-Object)
    $middle = [int][math]::Floor($ordered.Count / 2)
    if ($ordered.Count % 2) { return [double]$ordered[$middle] }
    return ([double]$ordered[$middle - 1] + [double]$ordered[$middle]) / 2
}

$stream = [System.IO.File]::OpenRead($source)
try {
    $reader = [System.IO.BinaryReader]::new($stream)
    $ascii = [System.Text.Encoding]::ASCII
    $riff = $ascii.GetString($reader.ReadBytes(4))
    [void]$reader.ReadUInt32()
    $wave = $ascii.GetString($reader.ReadBytes(4))
    $fmt = $ascii.GetString($reader.ReadBytes(4))
    $fmtSize = $reader.ReadUInt32()
    $format = $reader.ReadUInt16()
    $channels = $reader.ReadUInt16()
    $sampleRate = $reader.ReadUInt32()
    [void]$reader.ReadUInt32()
    [void]$reader.ReadUInt16()
    $bits = $reader.ReadUInt16()
    $data = $ascii.GetString($reader.ReadBytes(4))
    $dataBytes = $reader.ReadUInt32()
    if ($riff -ne "RIFF" -or $wave -ne "WAVE" -or $fmt -ne "fmt " -or
        $fmtSize -ne 16 -or $format -ne 1 -or $channels -ne 1 -or
        $sampleRate -ne 16000 -or $bits -ne 16 -or $data -ne "data" -or
        $dataBytes -ne ($stream.Length - 44)) {
        throw "Expected canonical mono 16 kHz 16-bit PCM WAV"
    }
    $durationSeconds = $dataBytes / ($sampleRate * $channels * ($bits / 8))
} finally {
    $stream.Dispose()
}
$sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()

$existing = @{}
Get-ChildItem -Directory (Join-Path $DataDirectory "lectures") `
    -ErrorAction SilentlyContinue | ForEach-Object { $existing[$_.Name] = $true }
$argsList = @(
    "-m", "npu_scribe.cli", "--data-dir", $DataDirectory,
    "transcribe", "--cleanup", "off", "--formatting", "off", $source, "--model", $Model, "--device", "CPU",
    "--chunk-seconds", "30", "--overlap-seconds", "1"
)
$startInfo = [System.Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $PythonExe
$startInfo.WorkingDirectory = $repoRoot
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
foreach ($argument in $argsList) { [void]$startInfo.ArgumentList.Add($argument) }
$started = Get-Date
$worker = [System.Diagnostics.Process]::Start($startInfo)
$stdoutTask = $worker.StandardOutput.ReadToEndAsync()
$stderrTask = $worker.StandardError.ReadToEndAsync()
$samples = [System.Collections.Generic.List[object]]::new()
$checkpointSeen = $false
$deadline = $started.AddMinutes($TimeoutMinutes)
$sessionId = $null
while (-not $worker.HasExited -and (Get-Date) -lt $deadline) {
    Start-Sleep -Seconds $SampleSeconds
    try {
        $treeMemory = Get-TreeWorkingSetBytes -RootProcessId $worker.Id
    } catch {
        $treeMemory = $null
    }
    $newSessions = @(Get-ChildItem -Directory (Join-Path $DataDirectory "lectures") `
        -ErrorAction SilentlyContinue | Where-Object { -not $existing.ContainsKey($_.Name) })
    if ($newSessions.Count -eq 1) { $sessionId = $newSessions[0].Name }
    $completed = $null
    if ($sessionId) {
        $checkpointPath = Join-Path $DataDirectory "lectures\$sessionId\checkpoint.json"
        if (Test-Path -LiteralPath $checkpointPath) {
            $checkpointSeen = $true
            try {
                $checkpoint = Get-Content -LiteralPath $checkpointPath -Raw | ConvertFrom-Json
                $completed = @($checkpoint.completed_chunks).Count
            } catch { }
        }
    }
    if ($null -ne $treeMemory -and $treeMemory.bytes -gt 0) {
        $samples.Add([ordered]@{
            elapsed_seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
            tree_working_set_mb = [math]::Round($treeMemory.bytes / 1MB, 1)
            process_count = $treeMemory.process_count
            completed_chunks = $completed
        })
    }
}
$timedOut = -not $worker.HasExited
if ($timedOut) {
    & taskkill /PID $worker.Id /T /F 2>$null | Out-Null
    $worker.WaitForExit(10000) | Out-Null
}
$stdout = $stdoutTask.GetAwaiter().GetResult()
$stderr = $stderrTask.GetAwaiter().GetResult()
$elapsed = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
$parsedId = [regex]::Match($stdout, "(?m)^session:\s*([a-zA-Z0-9_-]+)\s*$")
if ($parsedId.Success) { $sessionId = $parsedId.Groups[1].Value }
$ready = $false
$chunks = $null
$fallbacks = $null
$sourcePreserved = $false
$layersSaved = $false
if ($sessionId) {
    $sessionRoot = Join-Path $DataDirectory "lectures\$sessionId"
    $sessionPath = Join-Path $sessionRoot "session.json"
    if (Test-Path -LiteralPath $sessionPath) {
        $session = Get-Content -LiteralPath $sessionPath -Raw | ConvertFrom-Json
        $ready = $session.status -eq "ready"
        if ($session.diagnostics.PSObject.Properties["chunk_records"]) {
            $chunks = @($session.diagnostics.chunk_records).Count
        }
        if ($session.diagnostics.PSObject.Properties["fallback_events"]) {
            $fallbacks = @($session.diagnostics.fallback_events).Count
        }
        $sourceRecord = Join-Path $sessionRoot "source\source.json"
        if (Test-Path -LiteralPath $sourceRecord) {
            $record = Get-Content -LiteralPath $sourceRecord -Raw | ConvertFrom-Json
            $sourcePreserved = $record.sha256 -eq $sourceHash
        }
        $layersSaved = (Test-Path -LiteralPath (Join-Path $sessionRoot "raw-transcript.json")) `
            -and (Test-Path -LiteralPath (Join-Path $sessionRoot "balanced-transcript.json"))
    }
}
$valid = @($samples | Where-Object { $_["elapsed_seconds"] -ge 30 })
$quarter = [int][math]::Floor($valid.Count / 4)
$firstMedian = $null
$lastMedian = $null
if ($quarter -ge 1) {
    $firstMedian = Median @($valid | Select-Object -First $quarter |
        ForEach-Object { [double]$_["tree_working_set_mb"] })
    $lastMedian = Median @($valid | Select-Object -Last $quarter |
        ForEach-Object { [double]$_["tree_working_set_mb"] })
}
$peak = $null
if ($samples.Count -gt 0) {
    $peak = [math]::Round(($samples | ForEach-Object { [double]$_["tree_working_set_mb"] } |
        Measure-Object -Maximum).Maximum, 1)
}
$report = [ordered]@{
    schema_version = 1
    source_duration_seconds = $durationSeconds
    source_sha256 = $sourceHash
    model_id = $Model
    requested_device = "CPU"
    session_id = $sessionId
    completed = (-not $timedOut) -and ($worker.ExitCode -eq 0) -and $ready
    exit_code = $(if ($timedOut) { $null } else { $worker.ExitCode })
    wall_seconds = $elapsed
    chunks_completed = $chunks
    fallback_events = $fallbacks
    checkpoint_observed = $checkpointSeen
    source_copy_hash_matches = $sourcePreserved
    raw_and_balanced_saved = $layersSaved
    sample_interval_seconds = $SampleSeconds
    memory_scope = "root process and descendants; working set"
    sample_count = $samples.Count
    sampled_peak_mb = $peak
    post_warmup_first_quarter_median_mb = $firstMedian
    post_warmup_last_quarter_median_mb = $lastMedian
    samples = $samples
    stderr_category = $(if ($stderr -match "(?i)warning") { "warning" }
        elseif ($stderr -match "\S") { "other" } else { "none" })
}
$reportPath = Join-Path $OutputDirectory "endurance-120min.json"
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
Write-Output "report: $reportPath"
Write-Output "completed: $($report.completed); chunks: $chunks; sampled_peak_mb: $peak"
if (-not $report.completed -or -not $sourcePreserved -or -not $layersSaved -or
    -not $checkpointSeen -or $samples.Count -eq 0 -or $fallbacks -ne 0) {
    exit 1
}
