; Inno Setup Script for WYSIWYG
; Installs the compiled EXE, static assets, and sub-components.

#define MyAppName "WYSIWYG"
#define MyAppVersion "1.20.16.0"
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
OutputDir=dist_install
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
; Main application; user data files are installed separately below.
Source: "dist\WYSIWYG\*"; DestDir: "{app}"; Excludes: "data.json,media_formats.json,Conditions.json,Conditions - Copy.json,mainconditions.json,clipboard_history.json,Uberpaste\.venv\*,Uberpaste\dist\*,Uberpaste\build\*,Uberpaste\__pycache__\*,.venv\*,__pycache__\*,*.pyc,_internal\Adds\discogs_*,_internal\Adds\Discogs ADD*.txt,_internal\Adds\__pycache__\discogs_add*"; Flags: ignoreversion recursesubdirs createallsubdirs

; Root Configuration & Assets (data/media/conditions ship with the build so
; every install gets the latest versions; clipboard history is never touched)
Source: "index.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "editor.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "admin.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "search.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "data.json"; DestDir: "{app}"; Flags: ignoreversion uninsneveruninstall
Source: "fyrlogo.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "fyrlogo.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "media_formats.json"; DestDir: "{app}"; Flags: ignoreversion uninsneveruninstall
Source: "dist\WYSIWYG\Conditions.json"; DestDir: "{app}"; Flags: ignoreversion uninsneveruninstall
Source: "colourmap.json"; DestDir: "{app}"; Flags: ignoreversion uninsneveruninstall
; Colour-engine noise/fencing rules (vinyl Colored (...) template). Shipped and
; refreshed on upgrade; uninstall leaves it behind like colourmap.json.
Source: "colourrules.json"; DestDir: "{app}"; Flags: ignoreversion uninsneveruninstall
Source: "version.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "changelog.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "styles.css"; DestDir: "{app}"; Flags: ignoreversion
Source: "style_guide.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "app.js"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env"; DestDir: "{app}"; Flags: ignoreversion
Source: "keys.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\Scott\FYR_LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

; Chrome extension (unpacked). On the SERVER this folder is the single deployed
; copy: the installer below shares C:\FYRTOOLS read-only, and client machines
; load the extension straight from the share
;   \\<server>\FYRTOOLS\WYSIWYG\ChromeExt
; so replacing these files here (bump ChromeExt\version.json + manifest.json) is
; all a release needs -- background.js compares the version Chrome loaded against
; version.json on disk and calls chrome.runtime.reload() by itself.
; The local copy is still installed so a client can fall back to it if the share
; is unreachable. ignoreversion overwrites on upgrade.
Source: "ChromeExt\*"; DestDir: "{app}\ChromeExt"; Flags: ignoreversion recursesubdirs createallsubdirs

; Standalone single-file scanner. WYSIWYG never launches this exe - it runs the
; embedded Python scanner (WysiScan\scanner_server.py inside the bundle) - but
; external tools (e.g. WysiChat) start it from C:\FYRTOOLS\WysiScan.
Source: "WysiScan\dist\WysiScan.exe"; DestDir: "C:\FYRTOOLS\WysiScan"; Flags: ignoreversion

; WysiChat (built by the root !build.bat from WysiChat\, PyInstaller onefile).
; Installs into C:\FYRTOOLS\WysiChat - the same folder the standalone WysiChat
; installer uses (it spells it C:\FYRtOOLS; Windows paths are case-insensitive).
; ONLY the exe is shipped: both images are baked into it via --add-data and are
; read from the PyInstaller bundle at runtime, and user_prefs_<alias>.json /
; chat_history_<alias>.db live next to the exe. So an install/upgrade replaces
; the exe and nothing else, and an uninstall removes only the exe - chat
; history, preferences and logs are never touched.
Source: "WysiChat\dist\Wysichat.exe"; DestDir: "C:\FYRTOOLS\WysiChat"; Flags: ignoreversion

; Subfolders
; NOTE: The compiled EXE is a PyInstaller onedir build that bundles Uberpaste,
; WysiScan and Adds internally (via --add-data / sys._MEIPASS). At runtime
; main.py and scanner_server.py read those assets from the bundle, not from on-disk
; folders, and the scanner self-creates its writable data dirs (WysiScan\scans,
; WysiScan\temp, config.json) next to the EXE on first launch. So we deliberately do
; NOT copy these source folders to {app} — that keeps client installs clean (no raw
; source code visible under C:\FYRTOOLS\WYSIWYG).

; Discogs Adds is no longer shipped (not working, no menu entry, no hotkey), so the
; build strips it from the bundle. Older installs still have these files from
; previous builds; delete them on upgrade rather than leaving them behind.
[InstallDelete]
Type: files; Name: "{app}\_internal\Adds\discogs_*"
Type: files; Name: "{app}\_internal\Adds\Discogs ADD*.txt"
Type: files; Name: "{app}\_internal\Adds\__pycache__\discogs_add*"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon
; WysiChat sits in its own folder (like WysiScan), so it gets its own entry.
Name: "{autoprograms}\WysiChat"; Filename: "C:\FYRTOOLS\WysiChat\Wysichat.exe"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

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
    'taskkill /F /T /IM Wysichat.exe >nul 2>&1' + #13#10 +
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
    // Standalone scanner and WysiChat live outside {app}
    AddDefenderExclusion('C:\FYRTOOLS\WysiScan');
    AddDefenderExclusion('C:\FYRTOOLS\WysiChat');
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
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM Wysichat.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    // Remove the Microsoft Defender exclusions we added at install time.
    RemoveDefenderExclusion(ExpandConstant('{app}'));
    RemoveDefenderExclusion(ExpandConstant('{userstartup}'));
    RemoveDefenderExclusion(ExpandConstant('{commonstartup}'));
    RemoveDefenderExclusion(ExpandConstant('{group}'));
    RemoveDefenderExclusion(ExpandConstant('{autodesktop}'));
    RemoveDefenderExclusion(ExpandConstant('{userdesktop}'));
    RemoveDefenderExclusion(ExpandConstant('{tmp}'));
    RemoveDefenderExclusion('C:\FYRTOOLS\WysiScan');
    RemoveDefenderExclusion('C:\FYRTOOLS\WysiChat');
    Sleep(1500); // Give the OS time to release file handles
  end;
end;
