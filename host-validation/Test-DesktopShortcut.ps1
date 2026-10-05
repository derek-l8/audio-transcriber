param([Parameter(Mandatory=$true)][string]$Shortcut,[Parameter(Mandatory=$true)][string]$Library)
. "$PSScriptRoot/WindowsUiAutomation.ps1"
$env:AUDIO_TRANSCRIBER_DATA_DIR = $Library
$env:QT_QPA_PLATFORM = 'windows'
$launch = $null
try {
    $launch = Start-Process -FilePath $Shortcut -PassThru -WindowStyle Hidden
    if (-not $launch) { throw 'Windows did not return the shortcut process.' }
    $window = WaitWindow $launch.Id 'Audio Transcriber — Lecture library'
    if (-not (Test-Path -LiteralPath (Join-Path $Library 'desktop.lock'))) { throw 'Shortcut did not open its isolated library.' }
    $handle = [OwnWindow]::Find($launch.Id)
    [OwnWindow]::PostMessage($handle,0x10,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null
    if (-not $launch.WaitForExit(10000)) { throw 'Shortcut-launched app did not close.' }
    if ($launch.ExitCode -ne 0) { throw 'Shortcut-launched app exited with an error.' }
    'Desktop shortcut opened the renamed app without CLI arguments.'
} finally {
    if ($launch -and -not $launch.HasExited) { $launch.Kill(); $launch.WaitForExit(10000) | Out-Null }
}
