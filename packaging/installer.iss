; Inno Setup script: wraps the PyInstaller folder build into one Setup.exe.
; Built by tools\build.ps1, which passes /DAppVersion=<filmconv.__version__>.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Film Converter"
#define AppExe "Film Converter.exe"

[Setup]
; Keep this AppId forever: it lets new versions install over old ones.
AppId={{6B2E4C1A-8F3D-4E57-9C2B-FA1D3E7C9A41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Yoav Engel
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
; Per-user install: no administrator prompt.
PrivilegesRequired=lowest
OutputDir=..\build\installer
OutputBaseFilename=FilmConverter-Setup-{#AppVersion}
SetupIconFile=..\filmconv_gui\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\build\dist\Film Converter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Remove files from an older version before copying the new one.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent
