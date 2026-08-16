#define MyAppName "Discount Parser"
#define MyAppVersion "0.1.0"
#define MyAppExeName "DiscountParser.exe"
#define MyWorkerExeName "DiscountParserWorker.exe"

[Setup]
AppId={{E9D2A6B6-4F2B-4C7A-90EE-44C33AC43FD2}
AppMutex=DiscountParserMutex_{{E9D2A6B6-4F2B-4C7A-90EE-44C33AC43FD2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\DiscountParser
DefaultGroupName={#MyAppName}
OutputDir=output
OutputBaseFilename=DiscountParser-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=yes

[Files]
Source: "..\..\delivery\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\Discount Parser"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Discount Parser"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  Res: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    // Attempt to create the shortcut via shell if Inno's [Icons] fails in some environments.
    // However, Inno's [Icons] is usually best-effort unless specified otherwise.
    // The customer error 0x80070005 (Access Denied) on IPersistFile::Save suggests 
    // a locking or permission issue on the .lnk file itself.
  end;
end;

// Make desktop icon optional and non-fatal
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

[Run]
Filename: "{app}\{#MyWorkerExeName}"; Parameters: "migrate"; WorkingDir: "{app}"; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "Открыть Discount Parser"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
