[CmdletBinding()]
param([string]$OutputDirectory = "$PSScriptRoot\reports")

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$started = Get-Date
$checks = [System.Collections.Generic.List[object]]::new()

function Add-Check([string]$Id, [string]$Status, [string]$Detail) {
    $checks.Add([ordered]@{ id=$Id; status=$Status; detail=$Detail })
}

function Read-Choice([string]$Prompt) {
    $answer = Read-Host "$Prompt [pass/fail/skip]"
    if ($answer -notin @("pass", "fail", "skip")) { return "unverified" }
    return $answer
}

$os = Get-CimInstance Win32_OperatingSystem
if (-not [Environment]::Is64BitOperatingSystem) { Add-Check "windows-x64" "fail" "64-bit Windows required" }
else { Add-Check "windows-x64" "pass" "$($os.Caption) build $($os.BuildNumber)" }

$pnp = Get-CimInstance Win32_PnPEntity | Where-Object {
    $_.Name -match "Intel.*(NPU|AI Boost|Graphics)|Intel.*Processor"
} | Select-Object Name, Status
Add-Check "intel-hardware" ($(if ($pnp) {"pass"} else {"unverified"})) `
    ($(if ($pnp) {$pnp.Name -join "; "} else {"No matching PnP names; runtime check is authoritative"}))

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Add-Check "openvino-devices" "skip" "python not found"
} else {
    try {
        $devices = & python -c "import json,openvino as ov; print(json.dumps(ov.Core().available_devices))"
        Add-Check "openvino-devices" "pass" $devices
    } catch { Add-Check "openvino-devices" "fail" "OpenVINO enumeration failed" }
}

Write-Host "Complete only ordinary editable-field checks. Never use a password field."
foreach ($app in @("Word", "Notion", "Codex")) {
    Add-Check "insertion-$($app.ToLower())" (Read-Choice "Did insertion, clipboard restoration, and copy fallback work in $app?") "owner-observed ordinary field"
}
Add-Check "microphone" (Read-Choice "Did microphone activation, visible state, stop, and playback work?") "owner-observed"
Add-Check "tray" (Read-Choice "Are tray states and exit behavior correct?") "owner-observed"
Add-Check "startup" (Read-Choice "Can launch-at-sign-in be enabled and disabled?") "owner-observed"
Add-Check "onedrive" (Read-Choice "Does setup warn before a OneDrive-redirected Desktop and offer local storage?") "owner-observed"

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$report = [ordered]@{
    schema_version = 1
    generated_utc = (Get-Date).ToUniversalTime().ToString("o")
    duration_seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 2)
    privacy = "No audio, transcript, clipboard content, username, or absolute personal path included. Review before sharing."
    checks = $checks
}
$jsonPath = Join-Path $OutputDirectory "npu-scribe-validation.json"
$mdPath = Join-Path $OutputDirectory "npu-scribe-validation.md"
$report | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $jsonPath
@("# NPU Scribe Windows validation", "", "Review for private content before returning.", "") +
    ($checks | ForEach-Object { "- **$($_.status)** ``$($_.id)`` — $($_.detail)" }) |
    Set-Content -Encoding UTF8 $mdPath
Write-Host "Reports written. Review them before returning:"
Write-Host $jsonPath
Write-Host $mdPath
