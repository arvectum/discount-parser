#define MyAppName "Discount Parser"
#define MyAppVersion "0.1.0"
#define MyAppExeName "DiscountParser.exe"
#define MyWorkerExeName "DiscountParserWorker.exe"
#define MyDesktopShortcutName "Discount Parser.lnk"

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
; DP-WIN-001: never restart a stale pre-upgrade process after payload replacement.
; Interactive Setup launches the freshly installed UI from [Run] instead.
RestartApplications=no

[InstallDelete]
; DP-WIN-001: the worker is product-owned and must never survive an upgrade as
; a stale binary. Because [InstallDelete] participates in Restart Manager's
; in-use detection, Setup closes a running worker first, deletes the old image,
; and only then processes [Files]. A failure must be surfaced by Setup rather
; than silently leaving an older worker behind.
Type: files; Name: "{app}\{#MyWorkerExeName}"

[Files]
; `notimestamp` is deliberate DP-CI-001 reproducibility policy: source mtimes
; must not change the installer bytes between otherwise identical builds.
Source: "..\..\delivery\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs notimestamp

[Tasks]
; DP-WIN-P0.2: the Desktop shortcut is optional. It is created from [Code]
; so a shell/ACL failure cannot roll back an otherwise valid per-user install.
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные ярлыки:"

[Icons]
; Keep the primary launch path installer-managed and independent from Desktop.
Name: "{group}\Discount Parser"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[Code]
procedure RegisterExtraCloseApplicationsResources();
begin
  // Explicitly register both product executables with Restart Manager. The worker
  // is especially important because it can be a background process with no UI.
  RegisterExtraCloseApplicationsResource(ExpandConstant('{app}\{#MyWorkerExeName}'));
  RegisterExtraCloseApplicationsResource(ExpandConstant('{app}\{#MyAppExeName}'));
end;

function DesktopShortcutPath(): String;
begin
  Result := ExpandConstant('{userdesktop}\{#MyDesktopShortcutName}');
end;

procedure RemoveDesktopShortcutBestEffort();
var
  ShortcutPath: String;
begin
  ShortcutPath := DesktopShortcutPath();

  if FileExists(ShortcutPath) then
  begin
    if DeleteFile(ShortcutPath) then
      Log('DP-WIN-P0.2: removed existing Discount Parser desktop shortcut')
    else
      Log('DP-WIN-P0.2: warning: could not remove existing desktop shortcut; continuing installation');
  end;
end;

procedure CreateDesktopShortcutBestEffort();
var
  TargetPath: String;
  ShortcutPath: String;
  CreatedShortcut: String;
begin
  TargetPath := ExpandConstant('{app}\{#MyAppExeName}');
  ShortcutPath := DesktopShortcutPath();

  RemoveDesktopShortcutBestEffort();

  if not WizardIsTaskSelected('desktopicon') then
  begin
    Log('DP-WIN-P0.2: desktop shortcut task not selected');
    Exit;
  end;

  if not FileExists(TargetPath) then
  begin
    Log('DP-WIN-P0.2: desktop shortcut skipped because installed executable is missing: ' + TargetPath);
    Exit;
  end;

  try
    CreatedShortcut := CreateShellLink(
      ShortcutPath,
      '{#MyAppName}',
      TargetPath,
      '',
      ExpandConstant('{app}'),
      '',
      0,
      SW_SHOWNORMAL);
    Log('DP-WIN-P0.2: created desktop shortcut: ' + CreatedShortcut);
  except
    Log('DP-WIN-P0.2: warning: desktop shortcut creation failed; installation continues: ' + GetExceptionMessage);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    CreateDesktopShortcutBestEffort();
end;

[Run]
Filename: "{app}\{#MyWorkerExeName}"; Parameters: "migrate"; WorkingDir: "{app}"; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "Открыть Discount Parser"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Desktop link is created manually from [Code], therefore it is explicitly
; owned and removed here. `files` intentionally does not remove a directory
; that merely collides with the .lnk name (used by the resilience gate).
Type: files; Name: "{userdesktop}\{#MyDesktopShortcutName}"
Type: filesandordirs; Name: "{app}\_internal"
