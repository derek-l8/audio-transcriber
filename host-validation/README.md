# Owner Windows validation — round 1

Open PowerShell (not Administrator) in this directory and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\Invoke-NpuScribeValidation.ps1
```

Allow 15–30 minutes. Use only synthetic text and ordinary editable fields. The script
does not collect audio, transcript text, clipboard contents, username, or personal paths.
It currently enumerates OpenVINO devices and guides UI checks; identical-device benchmark
automation will be added after the packaged model manifest exists. Review both reports
for private content before returning them. `skip` and `unverified` do not count as passes.
