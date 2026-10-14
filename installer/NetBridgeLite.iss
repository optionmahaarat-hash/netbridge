; Inno Setup script for NetBridge Lite.  Compiled by build_installer.bat  (ISCC /DAppVersion=x.y.z installer\NetBridgeLite.iss)
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppName "NetBridge Lite"
#define AppExe  "NetBridgeLite.exe"

[Setup]
AppId={{8B6F3C52-4E1A-4D0B-9C7A-5E1B2D3F4A60}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=NetBridge
; Per-user install (no admin prompt, folder stays writable -> data\ and the built-in updater keep working)
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\NetBridgeLite
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
OutputDir=..\release
OutputBaseFilename=NetBridgeLite-Setup-{#AppVersion}
SetupIconFile=..\assets\netbridge.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
CloseApplications=force
RestartApplications=no
UsePreviousTasks=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
; everything PyInstaller produced + the Xray core; never user data
Source: "..\dist\NetBridgeLite\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: "data\*,updates\*"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; if the app was running when removed, Windows must not be left pointing at a dead proxy
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "KillApp"
Filename: "{sys}\reg.exe"; Parameters: "add ""HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"" /v ProxyEnable /t REG_DWORD /d 0 /f"; Flags: runhidden; RunOnceId: "ClearProxy"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\data"
Type: filesandordirs; Name: "{app}\updates"
Type: filesandordirs; Name: "{app}\configs"
Type: filesandordirs; Name: "{app}"
