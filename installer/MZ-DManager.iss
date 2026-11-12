; MZ-DManager installer (Inno Setup 6). Built automatically by GitHub Actions.
#ifndef AppVersion
  #define AppVersion "1.7.0"
#endif

; Optional install password: set the INSTALLER_PASSWORD secret on GitHub. It never appears in the code.
#define InstallPwd GetEnv("INSTALLER_PASSWORD")

[Setup]
#if InstallPwd != ""
Password={#InstallPwd}
Encryption=yes
#endif
AppId={{6F0C2B7E-6C2E-4C1B-9E0B-5D4D9A2F7A31}
AppName=MZ-DManager
AppVersion={#AppVersion}
AppVerName=MZ-DManager {#AppVersion}
AppPublisher=MZ-DManager
DefaultDirName={localappdata}\Programs\MZ-DManager
DefaultGroupName=MZ-DManager
DisableProgramGroupPage=yes
DisableDirPage=auto
UsePreviousAppDir=no
UsePreviousGroup=no
PrivilegesRequired=lowest
OutputDir=..\output
OutputBaseFilename=MZ-DManager-Setup
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\MZ-DManager.exe
UninstallDisplayName=MZ-DManager
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start MZ-DManager with Windows (runs next to the clock)"; GroupDescription: "Options:"

[InstallDelete]
; clean up the previous names (EDENLOAD, DMTOR)
Type: filesandordirs; Name: "{localappdata}\Programs\EDENLOAD"
Type: filesandordirs; Name: "{userprograms}\EDENLOAD"
Type: files; Name: "{userdesktop}\EDENLOAD.lnk"
Type: filesandordirs; Name: "{localappdata}\Programs\DMTOR"
Type: filesandordirs; Name: "{userprograms}\DMTOR"
Type: files; Name: "{userdesktop}\DMTOR.lnk"

[Files]
Source: "..\dist\MZ-DManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\extension\*"; DestDir: "{app}\extension"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "guide.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\app.png"; DestDir: "{app}"; DestName: "icon.png"; Flags: ignoreversion

[Icons]
Name: "{group}\MZ-DManager"; Filename: "{app}\MZ-DManager.exe"
Name: "{group}\Connect browser"; Filename: "{app}\MZ-DManager.exe"; Parameters: "--guide"
Name: "{group}\Uninstall MZ-DManager"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MZ-DManager"; Filename: "{app}\MZ-DManager.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MZ-DManager"; \
  ValueData: """{app}\MZ-DManager.exe"" --tray"; Tasks: startup; Flags: uninsdeletevalue

Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "DMTOR"; Flags: deletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "EDENLOAD"; Flags: deletevalue

[Run]
; create Music, Videos, Programs, Documents, Torrents and Others in the Downloads folder
Filename: "{app}\MZ-DManager.exe"; Parameters: "--init-folders"; Flags: runhidden waituntilterminated
Filename: "{app}\MZ-DManager.exe"; Parameters: "--guide"; Description: "Connect Chrome / Edge now (opens a short guide)"; \
  Flags: postinstall nowait skipifsilent
Filename: "{app}\MZ-DManager.exe"; Description: "Open MZ-DManager"; Flags: postinstall nowait skipifsilent
; after an automatic (silent) update, reopen MZ-DManager
Filename: "{app}\MZ-DManager.exe"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM MZ-DManager.exe"; Flags: runhidden; RunOnceId: "KillApp"
Filename: "{app}\MZ-DManager.exe"; Parameters: "--unregister"; Flags: runhidden waituntilterminated; RunOnceId: "Unregister"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  { close a running copy (also an old EdenDM.exe) so its files can be replaced }
  Exec(ExpandConstant('{cmd}'), '/C taskkill /F /IM MZ-DManager.exe & taskkill /F /IM EDENLOAD.exe & taskkill /F /IM DMTOR.exe & taskkill /F /IM EdenDM.exe', '', SW_HIDE,
       ewWaitUntilTerminated, Code);
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    { remember the "start with Windows" choice inside the app's own settings too }
    if WizardIsTaskSelected('startup') then
    begin
      ForceDirectories(ExpandConstant('{userappdata}\MZ-DManager'));
      SaveStringToFile(ExpandConstant('{userappdata}\MZ-DManager\startup.flag'), '1', False);
    end;
#if InstallPwd != ""
    { remember the password on this PC so automatic updates don't ask for it again }
    if WizardForm.PasswordEdit.Text <> '' then
      RegWriteStringValue(HKEY_CURRENT_USER, 'Software\MZ-DManager', 'InstallKey', WizardForm.PasswordEdit.Text);
#endif
  end;
end;
