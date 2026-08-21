#define AppName "NPU Scribe"
#define AppVersion "0.1.0"

[Setup]
AppId={{3E0FB1F0-E39B-47B2-86F8-A99EB0495727}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\NPU Scribe
DefaultGroupName=NPU Scribe
PrivilegesRequired=lowest
OutputBaseFilename=npu-scribe-{#AppVersion}-windows-x64
UninstallDisplayIcon={app}\NPU Scribe.exe
Compression=lzma2
SolidCompression=yes

[Tasks]
Name: startup; Description: "Launch NPU Scribe when I sign in"; Flags: checkedonce

[Files]
Source: "..\dist\NPU Scribe\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\NPU Scribe"; Filename: "{app}\NPU Scribe.exe"
Name: "{userstartup}\NPU Scribe"; Filename: "{app}\NPU Scribe.exe"; Tasks: startup

[Run]
Filename: "{app}\NPU Scribe.exe"; Description: "Launch NPU Scribe"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; User data is deliberately not deleted. A future in-app action may delete it explicitly.
Type: filesandordirs; Name: "{app}"
