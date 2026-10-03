# Internal driver for Test-FrozenJobClose.py; Windows PowerShell 5, UTF-8 BOM required.
param(
 [Parameter(Mandatory=$true)][string]$Exe,
 [Parameter(Mandatory=$true)][string]$Data,
 [Parameter(Mandatory=$true)][string]$Media,
 [Parameter(Mandatory=$true)][string]$Report
)
. "$PSScriptRoot/WindowsUiAutomation.ps1"
$button=[System.Windows.Automation.ControlType]::Button
$env:QT_QPA_PLATFORM='windows'
$runs=@()
for($attempt=0; $attempt -lt 2; $attempt++) {
 $p=Start-Process -FilePath $Exe -ArgumentList @('--data-dir',('"'+$Data+'"')) -WorkingDirectory $Data -PassThru -WindowStyle Hidden
 $h=[IntPtr]::Zero
 try {
  $main=WaitWindow $p.Id 'NPU Scribe — Lecture library'
  $h=[OwnWindow]::Find($p.Id)
  if($attempt -eq 0) {
   $opening=[OwnWindow]::InvokeAsync((FindControl $main 'Import lecture…' $button))
   FilePicker $p.Id 'Import lecture' $Media 1148
   if(-not $opening.Wait(5000)) { throw 'Import invocation did not return' }
   $script:checkpoint=$null
   WaitUntil {
    $files=@(Get-ChildItem -LiteralPath (Join-Path $Data 'lectures') -Filter checkpoint.json -Recurse -ErrorAction SilentlyContinue)
    if($files.Count -eq 1) {
     try {
      $value=Get-Content -LiteralPath $files[0].FullName -Raw | ConvertFrom-Json
      if($value.completed_chunks.Count -ge 1 -and $value.completed_chunks.Count -lt $value.total_chunks) { $script:checkpoint=$files[0].FullName; return $true }
     } catch { } # A bounded retry handles transient sharing during atomic replacement.
    }
    return $false
   } 'No partially completed checkpoint before close' 90
   if(-not (FindControl $main 'Pause' $button).Current.IsEnabled) { throw 'GUI was not busy when close was requested' }
   $before=Get-Content -LiteralPath $script:checkpoint -Raw | ConvertFrom-Json
   $workers=@(Get-CimInstance Win32_Process -Filter ('ParentProcessId = '+$p.Id) | Select-Object -ExpandProperty ProcessId)
   if($workers.Count -lt 1) { throw 'No owned child worker observed' }
  } else {
   $resume=FindControl $main 'Resume selected' $button
   if(-not $resume.Current.IsEnabled) { throw 'Reopened interrupted lecture cannot resume' }
   InvokeControl $resume
   $session=Join-Path (Split-Path $script:checkpoint -Parent) 'session.json'
   WaitUntil {
    try { return (Get-Content -LiteralPath $session -Raw | ConvertFrom-Json).status -eq 'ready' -and (FindControl $main 'Import lecture…' $button).Current.IsEnabled } catch { return $false }
   } 'GUI resume did not finish successfully' 300
  }
  [OwnWindow]::PostMessage($h,0x10,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null
  if(-not $p.WaitForExit(60000)) { throw 'Normal close did not finish' }
  if($p.ExitCode -ne 0 -or (Test-Path -LiteralPath (Join-Path $Data 'desktop.lock'))) { throw 'Normal close failed or left a lock' }
  if($attempt -eq 0) {
   $paused=Get-Content -LiteralPath $script:checkpoint -Raw | ConvertFrom-Json
   $session=Get-Content -LiteralPath (Join-Path (Split-Path $script:checkpoint -Parent) 'session.json') -Raw | ConvertFrom-Json
   if($session.status -ne 'interrupted' -or $paused.completed_chunks.Count -lt $before.completed_chunks.Count -or $paused.completed_chunks.Count -ge $paused.total_chunks) { throw 'Close did not safely interrupt the active job' }
   foreach($workerId in $workers) { if(Get-Process -Id $workerId -ErrorAction SilentlyContinue) { throw 'Owned worker remained after GUI close' } }
   if(@(Get-ChildItem -LiteralPath (Join-Path $Data 'jobs') -Filter '*.stop').Count -ne 0) { throw 'Completed pause marker remained' }
   Copy-Item -LiteralPath $script:checkpoint -Destination (Join-Path (Split-Path $Data -Parent) 'paused-checkpoint.json')
   $runs += [ordered]@{stage='close_during_job';exit_code=0;lock_removed=$true;busy_when_requested=$true;chunks_before_close=$before.completed_chunks.Count;chunks_after_close=$paused.completed_chunks.Count;total_chunks=$paused.total_chunks;status=$session.status;owned_workers_exited=$true;pause_marker_removed=$true}
   Write-Output ('Closed safely after '+$paused.completed_chunks.Count+' / '+$paused.total_chunks+' chunks')
  } else {
   $runs += [ordered]@{stage='reopen_resume_close';exit_code=0;lock_removed=$true;status='ready'}
   Write-Output 'Reopened GUI resumed the lecture to completion'
  }
 } finally {
  if(-not $p.HasExited) {
   if($h -ne [IntPtr]::Zero) { [OwnWindow]::PostMessage($h,0x10,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null }
   if(-not $p.WaitForExit(10000)) { $p.Kill(); $p.WaitForExit() }
  }
  $p.Dispose()
 }
}
[ordered]@{runs=$runs;native_import_file_picker=$true;native_resume_button=$true} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Report -Encoding utf8
