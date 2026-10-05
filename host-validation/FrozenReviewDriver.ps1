# Internal driver for Test-FrozenReview.py. Save with a UTF-8 BOM for Windows PowerShell 5.
param(
    [Parameter(Mandatory=$true)][string]$Exe,
    [Parameter(Mandatory=$true)][string]$Data,
    [Parameter(Mandatory=$true)][string]$Report
)
. "$PSScriptRoot/WindowsUiAutomation.ps1"
$button=[System.Windows.Automation.ControlType]::Button
$edit=[System.Windows.Automation.ControlType]::Edit
$runs=@()
$playback=$null
$env:QT_QPA_PLATFORM='windows'
for($attempt=0; $attempt -lt 2; $attempt++) {
    $p=Start-Process -FilePath $Exe -ArgumentList @('--data-dir',('"'+$Data+'"')) -WorkingDirectory $Data -PassThru -WindowStyle Hidden
    $h=[IntPtr]::Zero
    try {
        $main=WaitWindow $p.Id 'Audio Transcriber — Lecture library'
        $h=[OwnWindow]::Find($p.Id)
        [OwnWindow]::ShowWindow($h,5) | Out-Null
        if(-not (Test-Path -LiteralPath (Join-Path $Data 'desktop.lock'))) { throw 'Library lock absent' }
        $transcript=FindControl $main 'Transcript' $edit
        if(-not (ValueOf $transcript).Current.IsReadOnly) { throw 'Transcript unexpectedly writable' }
        if($attempt -eq 0) {
            if((ValueOf (FindControl $main 'Cleanup style' ([System.Windows.Automation.ControlType]::ComboBox))).Current.Value -ne 'light') { throw 'Fresh lecture cleanup default differs' }
            if((ValueOf (FindControl $main 'Formatting style' ([System.Windows.Automation.ControlType]::ComboBox))).Current.Value -ne 'Mostly structured') { throw 'Fresh lecture formatting default differs' }
            foreach($model in @('whisper-tiny.en-int4-ov','whisper-base.en-int4-ov','Choose a speech model')) {
                SelectCombo $p.Id $h $main 'Speech model' $model
            }
            foreach($device in @('GPU','NPU','auto','CPU')) {
                SelectCombo $p.Id $h $main 'Transcription device' $device
            }
            foreach($style in @('off','medium','light')) {
                SelectCombo $p.Id $h $main 'Cleanup style' $style
            }
            foreach($layout in @('Mixed','Mostly structured','Mostly prose')) {
                SelectCombo $p.Id $h $main 'Formatting style' $layout
            }
            InvokeControl (FindControl $main 'Live dictation…' $button)
            $dictation=WaitWindow $p.Id 'Audio Transcriber — Live dictation'
            $dictationHandle=[OwnWindow]::Find($p.Id,'Audio Transcriber — Live dictation')
            FindControl $dictation 'Microphone' ([System.Windows.Automation.ControlType]::ComboBox) | Out-Null
            FindControl $dictation 'Record a copy' $button | Out-Null
            if((ValueOf (FindControl $dictation 'Cleanup' ([System.Windows.Automation.ControlType]::ComboBox))).Current.Value -ne 'medium') { throw 'Fresh dictation cleanup default differs' }
            FindControl $dictation 'Mostly prose' ([System.Windows.Automation.ControlType]::Text) | Out-Null
            $shortcut=ValueOf (FindControl $dictation 'Dictation shortcut' $edit)
            $shortcut.SetValue('Ctrl+Shift+F10')
            if($shortcut.Current.Value -ne 'Ctrl+Shift+F10') { throw 'Frozen dictation shortcut was not editable' }
            foreach($mode in @('Hold to talk','Toggle')) {
                SelectCombo $p.Id $dictationHandle $dictation 'Shortcut mode' $mode
            }
            [OwnWindow]::PostMessage($dictationHandle,0x10,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null
            WaitUntil { [OwnWindow]::FindClass($p.Id,'QDialog','Audio Transcriber — Live dictation') -eq [IntPtr]::Zero } 'Idle dictation window did not close'
            $slider=FindControl $main 'Audio position' ([System.Windows.Automation.ControlType]::Slider)
            $range=[System.Windows.Automation.RangeValuePattern]$slider.GetCurrentPattern([System.Windows.Automation.RangeValuePattern]::Pattern)
            $deadline=(Get-Date).AddSeconds(10)
            while($range.Current.Maximum -lt 61000 -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 100 }
            if($range.Current.Maximum -ne 61000) { throw 'Synthetic playback duration differs' }
            $range.SetValue(5000)
            Start-Sleep -Milliseconds 200
            $clock=@($main.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition) | Where-Object {$_.Current.Name -eq '00:00:05 / 00:01:01'})
            if($clock.Count -ne 1) { throw 'Slider value did not seek the actual player' }
            InvokeControl (FindControl $main 'Play' $button)
            Start-Sleep -Milliseconds 1500
            InvokeControl (FindControl $main 'Pause audio' $button)
            $advanced=$range.Current.Value
            if($advanced -lt 5500) { throw 'Playback failed to advance from the seek position' }
            InvokeControl (FindControl $main 'Seek to segment' $button)
            Start-Sleep -Milliseconds 200
            if($range.Current.Value -ne 0) { throw 'First segment seek did not return to zero' }
            $playback=[ordered]@{requested_ms=5000; displayed_position_matches=$true; advanced_ms=$advanced; segment_seek_ms=$range.Current.Value}
            foreach($correction in @('Synthetic native correction one','Synthetic native correction two')) {
                $opening=[OwnWindow]::InvokeAsync((FindControl $main 'Edit selected segment…' $button))
                $dialog=WaitWindow $p.Id 'Edit transcript segment'
                (ValueOf (FindControl $dialog 'Segment text' $edit)).SetValue($correction)
                $flag=FindControl $dialog 'Flag this segment as uncertain' ([System.Windows.Automation.ControlType]::CheckBox)
                $toggle=[System.Windows.Automation.TogglePattern]$flag.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
                if($toggle.Current.ToggleState -ne [System.Windows.Automation.ToggleState]::On) { $toggle.Toggle() }
                InvokeControl (FindControl $dialog 'Save' $button)
                if(-not $opening.Wait(5000)) { throw 'Edit dialog did not close after saving' }
                Start-Sleep -Milliseconds 200
                if(-not (ValueOf $transcript).Current.Value.Contains($correction)) { throw 'Saved text absent from the visible transcript' }
            }
            (ValueOf (FindControl $main 'Find in transcript' $edit)).SetValue('correction two')
            InvokeControl (FindControl $main 'Find next' $button)
            Start-Sleep -Milliseconds 200
            $text=[System.Windows.Automation.TextPattern]$transcript.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
            $selection=@($text.GetSelection())
            if($selection.Count -ne 1 -or $selection[0].GetText(-1) -ne 'correction two') { throw 'Search did not select the edited phrase' }
        }
        $opening=[OwnWindow]::InvokeAsync((FindControl $main 'Revision history…' $button))
        $history=WaitWindow $p.Id 'Edited transcript history'
        Start-Sleep -Milliseconds 200
        $preview=ValueOf (FindControl $history 'Revision transcript' $edit)
        if(-not $preview.Current.IsReadOnly -or -not $preview.Current.Value.Contains('Synthetic native correction two')) { throw 'Newest revision missing or history editable' }
        $list=FindControl $history 'Saved revisions' ([System.Windows.Automation.ControlType]::List)
        $entries=$list.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::ListItem))
        if($entries.Count -ne 2) { throw 'Expected two saved revisions' }
        ClickElement ([OwnWindow]::Find($p.Id,'Edited transcript history')) $entries[1]
        WaitUntil { $preview.Current.Value.Contains('Synthetic native correction one') -and -not $preview.Current.Value.Contains('correction two') } 'Older revision preview did not update'
        InvokeControl (FindControl $history 'Close' $button)
        if(-not $opening.Wait(5000)) { throw 'History dialog did not close' }
        $deadline=(Get-Date).AddSeconds(5)
        while([OwnWindow]::Find($p.Id,'Edited transcript history') -ne [IntPtr]::Zero -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 100 }
        if([OwnWindow]::Find($p.Id,'Edited transcript history') -ne [IntPtr]::Zero) { throw 'History window remained after Close' }
        Start-Sleep -Milliseconds 200
        if($attempt -eq 0) {
            $exports=Join-Path (Split-Path $Data -Parent) 'exports'
            New-Item -ItemType Directory -Path $exports | Out-Null
            foreach($layer in @('Raw','Balanced','Edited')) {
                SelectCombo $p.Id $h $main 'Transcript layer' $layer
                foreach($format in @('text','markdown','srt','json')) {
                    SelectCombo $p.Id $h $main 'Export format' $format
                    $suffix=@{text='txt';markdown='md';srt='srt';json='json'}[$format]
                    $path=Join-Path $exports ($layer.ToLower()+'.'+$suffix)
                    $opening=[OwnWindow]::InvokeAsync((FindControl $main 'Export…' $button))
                    FilePicker $p.Id 'Export transcript' $path
                    WaitUntil { (Test-Path -LiteralPath $path) -and (Get-Item -LiteralPath $path).Length -gt 0 } 'Native export not written'
                    if(-not $opening.Wait(5000)) { throw 'Export invocation did not return' }
                }
            }
        }
        SelectCombo $p.Id $h $main 'Transcript layer' 'Edited'
        WaitUntil { (ValueOf $transcript).Current.Value.Contains('Synthetic native correction two') } 'Reopened Edited layer did not load'
        [OwnWindow]::PostMessage($h,0x10,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null
        if(-not $p.WaitForExit(10000)) { throw 'Normal GUI close timed out' }
        if($p.ExitCode -ne 0 -or (Test-Path -LiteralPath (Join-Path $Data 'desktop.lock'))) { throw 'GUI close failed or left the library locked' }
        $runs += [ordered]@{exit_code=$p.ExitCode; lock_removed=$true; history_revisions=$entries.Count; newest_revision_preview_matches=$true; history_read_only=$true; older_revision_preview_matches=$true; edited_layer_matches=$true}
    } finally {
        if(-not $p.HasExited) {
            if($h -ne [IntPtr]::Zero) { [OwnWindow]::PostMessage($h,0x10,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null }
            if(-not $p.WaitForExit(2000)) { $p.Kill(); $p.WaitForExit() }
        }
        $p.Dispose()
    }
}
[ordered]@{runs=$runs; playback=$playback; edits_saved=2; search_selection_matches=$true; reopened_history_persisted=$true; native_exports=12; dictation_controls=$true; fresh_lecture_defaults='light / structured'; fresh_dictation_defaults='medium / prose'; microphone_recording_started=$false; cleanup_and_formatting_selectors=$true; dropdown_selection=$true; dropdowns=@('Speech model','Transcription device','Transcript layer','Export format')} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Report -Encoding utf8
Write-Output 'Frozen native playback, seek, edits, search, history and close/reopen passed'

