; MZ-DManager Lite — Windows 7 edition (files only). Separate from MZ-DManager: own name, folder, settings and port.
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define InstallPwd GetEnv("INSTALLER_PASSWORD")

[Setup]
#if InstallPwd != ""
Password={#InstallPwd}
Encryption=yes
#endif
AppId={{B3D6A1F2-7C41-4E8A-9A55-2F1D7E0C4B19}
AppName=MZ-DManager Lite
AppVersion={#AppVersion}
AppVerName=MZ-DManager Lite {#AppVersion}
AppPublisher=MZ-DManager
DefaultDirName={autopf}\MZ-DManager Lite
DefaultGroupName=MZ-DManager Lite
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=admin
UsedUserAreasWarning=no
MinVersion=6.1sp1
OutputDir=..\output
OutputBaseFilename=MZ-DManager-Lite-Setup
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\MZ-DManager-Lite.exe
UninstallDisplayName=MZ-DManager Lite
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start MZ-DManager Lite with Windows (minimized)"; GroupDescription: "Options:"; Flags: unchecked

[Files]
Source: "..\dist\MZ-DManager-Lite\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; the browser extension lives in a fixed per-user folder, so Chrome / Edge never lose it on updates
Source: "..\extension\*"; DestDir: "{localappdata}\MZ-DManager Lite\extension"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "guide.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\app.png"; DestDir: "{app}"; DestName: "icon.png"; Flags: ignoreversion

[Icons]
Name: "{group}\MZ-DManager Lite"; Filename: "{app}\MZ-DManager-Lite.exe"
Name: "{group}\Connect browser"; Filename: "{app}\MZ-DManager-Lite.exe"; Parameters: "--guide"
Name: "{group}\Uninstall MZ-DManager Lite"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MZ-DManager Lite"; Filename: "{app}\MZ-DManager-Lite.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MZ-DManager Lite"; \
  ValueData: """{app}\MZ-DManager-Lite.exe"" --minimized"; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\MZ-DManager-Lite.exe"; Parameters: "--init-folders"; Flags: runhidden waituntilterminated runasoriginaluser
Filename: "{app}\MZ-DManager-Lite.exe"; Parameters: "--guide"; Description: "Connect Chrome / Edge now (opens a short guide)"; \
  Flags: postinstall nowait skipifsilent runasoriginaluser
Filename: "{app}\MZ-DManager-Lite.exe"; Description: "Open MZ-DManager Lite"; Flags: postinstall nowait skipifsilent runasoriginaluser
Filename: "{app}\MZ-DManager-Lite.exe"; Flags: nowait runasoriginaluser; Check: WizardSilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM MZ-DManager-Lite.exe"; Flags: runhidden; RunOnceId: "KillApp"
Filename: "{app}\MZ-DManager-Lite.exe"; Parameters: "--unregister"; Flags: runhidden waituntilterminated; RunOnceId: "Unregister"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  Exec(ExpandConstant('{cmd}'), '/C taskkill /F /IM MZ-DManager-Lite.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
#if InstallPwd != ""
    if WizardForm.PasswordEdit.Text <> '' then
      RegWriteStringValue(HKEY_CURRENT_USER, 'Software\MZ-DManager Lite', 'InstallKey', WizardForm.PasswordEdit.Text);
#endif
  end;
end;
