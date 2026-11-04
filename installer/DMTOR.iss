; DMTOR installer (Inno Setup 6). Built automatically by GitHub Actions.
#ifndef AppVersion
  #define AppVersion "1.6.0"
#endif

[Setup]
AppId={{6F0C2B7E-6C2E-4C1B-9E0B-5D4D9A2F7A31}
AppName=DMTOR
AppVersion={#AppVersion}
AppVerName=DMTOR {#AppVersion}
AppPublisher=DMTOR
DefaultDirName={localappdata}\Programs\DMTOR
DefaultGroupName=DMTOR
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\output
OutputBaseFilename=DMTOR-Setup
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\DMTOR.exe
UninstallDisplayName=DMTOR
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
Name: "startup"; Description: "Start DMTOR with Windows (runs next to the clock)"; GroupDescription: "Options:"

[Files]
Source: "..\dist\DMTOR\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\extension\*"; DestDir: "{app}\extension"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "guide.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\app.png"; DestDir: "{app}"; DestName: "icon.png"; Flags: ignoreversion

[Icons]
Name: "{group}\DMTOR"; Filename: "{app}\DMTOR.exe"
Name: "{group}\Connect browser"; Filename: "{app}\DMTOR.exe"; Parameters: "--guide"
Name: "{group}\Uninstall DMTOR"; Filename: "{uninstallexe}"
Name: "{autodesktop}\DMTOR"; Filename: "{app}\DMTOR.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "DMTOR"; \
  ValueData: """{app}\DMTOR.exe"" --tray"; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\DMTOR.exe"; Parameters: "--guide"; Description: "Connect Chrome / Edge now (opens a short guide)"; \
  Flags: postinstall nowait skipifsilent
Filename: "{app}\DMTOR.exe"; Description: "Open DMTOR"; Flags: postinstall nowait skipifsilent
; after an automatic (silent) update, reopen DMTOR
Filename: "{app}\DMTOR.exe"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM DMTOR.exe"; Flags: runhidden; RunOnceId: "KillApp"
Filename: "{app}\DMTOR.exe"; Parameters: "--unregister"; Flags: runhidden waituntilterminated; RunOnceId: "Unregister"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  { close a running copy (also an old EdenDM.exe) so its files can be replaced }
  Exec(ExpandConstant('{cmd}'), '/C taskkill /F /IM DMTOR.exe & taskkill /F /IM EdenDM.exe', '', SW_HIDE,
       ewWaitUntilTerminated, Code);
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  { remember the "start with Windows" choice inside the app's own settings too }
  if CurStep = ssPostInstall then
    if WizardIsTaskSelected('startup') then
    begin
      ForceDirectories(ExpandConstant('{userappdata}\DMTOR'));
      SaveStringToFile(ExpandConstant('{userappdata}\DMTOR\startup.flag'), '1', False);
    end;
end;
