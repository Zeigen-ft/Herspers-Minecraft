; Compile with ISCC /DPayload=absolute-package-directory /DOutput=output-directory
#ifndef Payload
  #error Payload must name a verified package folder
#endif
#ifndef Output
  #error Output must name the installer output folder
#endif
[Setup]
AppId=io.herspers.herps-launcher
AppName=Herps Launcher
AppVersion=0.1.0
DefaultDirName={localappdata}\Programs\Herps Launcher
DefaultGroupName=Herps Launcher
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#Output}
OutputBaseFilename=Herps-Launcher-0.1.0-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\Herps Launcher\Herps Launcher.exe
[Tasks]
Name: desktopicon; Description: Create a desktop shortcut; Flags: unchecked
[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Herps Launcher"; Filename: "{app}\Herps Launcher\Herps Launcher.exe"
Name: "{autodesktop}\Herps Launcher"; Filename: "{app}\Herps Launcher\Herps Launcher.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\Herps Launcher\Herps Launcher.exe"; Description: Open Herps Launcher; Flags: nowait postinstall skipifsilent
[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not FileExists(ExpandConstant('{sys}\vcruntime140_1.dll')) then
    Result := 'Install the Microsoft Visual C++ x64 runtime from https://aka.ms/vc14/vc_redist.x64.exe, then run this installer again.';
end;
