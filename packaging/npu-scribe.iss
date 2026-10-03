#ifndef AppName
  #define AppName "NPU Scribe"
#endif
#define AppVersion "0.1.0"
#ifndef AppId
  #define AppId "{{3E0FB1F0-E39B-47B2-86F8-A99EB0495727}"
#endif
#ifndef BundleDir
  #define BundleDir "..\dist\NPU Scribe"
#endif
#if !FileExists(BundleDir + "\NPU Scribe.exe") || !FileExists(BundleDir + "\npu-scribe-worker.exe")
  #error Build the complete PyInstaller bundle before compiling the installer.
#endif

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
OutputDir=..\dist\installer
OutputBaseFilename=npu-scribe-{#AppVersion}-windows-x64
UninstallDisplayIcon={app}\NPU Scribe.exe
Compression=lzma2
SolidCompression=yes

[Tasks]
Name: startup; Description: "Launch NPU Scribe when I sign in"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\NPU Scribe.exe"
Name: "{userstartup}\{#AppName}"; Filename: "{app}\NPU Scribe.exe"; Tasks: startup

[Run]
Filename: "{app}\NPU Scribe.exe"; Description: "Launch NPU Scribe"; Flags: postinstall nowait skipifsilent

; Uninstall removes tracked installation files only. Do not recursively delete
; {app}: a user may have placed a library or other personal files there.
