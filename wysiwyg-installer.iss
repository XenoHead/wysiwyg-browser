; Inno Setup Script for WYSIWYG
; Installs the compiled EXE, static assets, and sub-components.

#define MyAppName "WYSIWYG"
#define MyAppVersion "1.13.0.0"
#define MyAppPublisher "XenoHead"
#define MyAppExeName "WYSIWYG.exe"

[Setup]
AppId={{C349C35F-55AA-466D-B029-6D39D55C0E28}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName=C:\FYRTOOLS\WYSIWYG
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=INSTALL_WYSIWYG
SetupIconFile=fyrlogo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
CloseApplications=force

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Run at Windows Startup"; GroupDescription: "Additional options:"; Flags: unchecked

[Files]
; Main Executable
Source: "dist\WYSIWYG\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Root Configuration & Assets (only copy data.json if it doesn't already exist to preserve local profiles)
Source: "index.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "editor.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "admin.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "search.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "data.json"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist
Source: "fyrlogo.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "fyrlogo.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "media_formats.json"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist
Source: "version.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "changelog.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "styles.css"; DestDir: "{app}"; Flags: ignoreversion
Source: "style_guide.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "walmart.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "app.js"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\Scott\FYR_LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

; Subfolders
; NOTE: The compiled EXE is a PyInstaller onefile build that bundles Uberpaste,
; WysiScan and WalmartSheet internally (via --add-data / sys._MEIPASS). At runtime
; main.py and scanner_server.py read those assets from the bundle, not from on-disk
; folders, and the scanner self-creates its writable data dirs (WysiScan\scans,
; WysiScan\temp, config.json) next to the EXE on first launch. So we deliberately do
; NOT copy these source folders to {app} — that keeps client installs clean (no raw
; source code visible under C:\FYRTOOLS\WYSIWYG).

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\*.log"
Type: files; Name: "{app}\*.json"
Type: files; Name: "{app}\*.txt"
Type: files; Name: "{app}\*.PNG"
Type: files; Name: "{app}\*.ico"
Type: filesandordirs; Name: "{app}\WalmartSheet"
Type: filesandordirs; Name: "{app}\Uberpaste"
Type: filesandordirs; Name: "{app}\WysiScan"

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  KillBat, KillCmds: string;
begin
  // Kill any running instance BEFORE any files are copied, so a locked/open
  // WYSIWYG.exe cannot block the install. We write a small batch file to {tmp}
  // and run it through cmd.exe -- this terminates the whole process tree
  // (including child processes like the scanner subprocess) more reliably than
  // an in-process Exec call. /F=force, /T=kill tree.
  KillCmds :=
    '@echo off' + #13#10 +
    'taskkill /F /T /IM WYSIWYG.exe >nul 2>&1' + #13#10 +
    'taskkill /F /T /IM WysiScan.exe >nul 2>&1' + #13#10 +
    'taskkill /F /T /IM XDevHubX.exe >nul 2>&1' + #13#10 +
    'timeout /t 3 /nobreak >nul' + #13#10 +
    'taskkill /F /T /IM WYSIWYG.exe >nul 2>&1' + #13#10 +
    'timeout /t 2 /nobreak >nul' + #13#10;
  KillBat := ExpandConstant('{tmp}\kill_wysiwyg.bat');
  SaveStringToFile(KillBat, KillCmds, False);
  Exec('cmd.exe', '/C "' + KillBat + '"', ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
  // Belt-and-suspenders: inline kill in case the batch step was blocked.
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM WYSIWYG.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;

procedure AddDefenderExclusion(Path: string);
var
  ResultCode: Integer;
begin
  Exec('powershell.exe', '-NoProfile -Command "Add-MpPreference -ExclusionPath ''' + Path + '''"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure RemoveDefenderExclusion(Path: string);
var
  ResultCode: Integer;
begin
  Exec('powershell.exe', '-NoProfile -Command "Remove-MpPreference -ExclusionPath ''' + Path + '''"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    // Configure network sharing for C:\FYRTOOLS (Read access for Everyone)
    Exec('cmd.exe', '/c net share FYRTOOLS="C:\FYRTOOLS" /GRANT:Everyone,READ', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    // Add Microsoft Defender exclusions. Defender false-positives on the bundled
    // Python/cv2/PySide6 as Trojan:Win32/Bearfoos.A!ml and quarantines the app
    // (this also caused the earlier "decompression -1" and _MEI temp-dir errors).
    // Exclude the install dir AND every shortcut location Defender scans.
    AddDefenderExclusion(ExpandConstant('{app}'));
    AddDefenderExclusion(ExpandConstant('{userstartup}'));
    AddDefenderExclusion(ExpandConstant('{commonstartup}'));
    AddDefenderExclusion(ExpandConstant('{group}'));
    AddDefenderExclusion(ExpandConstant('{autodesktop}'));
    AddDefenderExclusion(ExpandConstant('{userdesktop}'));
    AddDefenderExclusion(ExpandConstant('{tmp}'));
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // Terminate processes before deleting files so they are not locked
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM WYSIWYG.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM WysiScan.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM XDevHubX.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    // Remove the Microsoft Defender exclusions we added at install time.
    RemoveDefenderExclusion(ExpandConstant('{app}'));
    RemoveDefenderExclusion(ExpandConstant('{userstartup}'));
    RemoveDefenderExclusion(ExpandConstant('{commonstartup}'));
    RemoveDefenderExclusion(ExpandConstant('{group}'));
    RemoveDefenderExclusion(ExpandConstant('{autodesktop}'));
    RemoveDefenderExclusion(ExpandConstant('{userdesktop}'));
    RemoveDefenderExclusion(ExpandConstant('{tmp}'));
    Sleep(1500); // Give the OS time to release file handles
  end;
end;
