; EDENLOAD installer (Inno Setup 6). Built automatically by GitHub Actions.
#ifndef AppVersion
  #define AppVersion "1.7.0"
#endif

[Setup]
AppId={{6F0C2B7E-6C2E-4C1B-9E0B-5D4D9A2F7A31}
AppName=EDENLOAD
AppVersion={#AppVersion}
AppVerName=EDENLOAD {#AppVersion}
AppPublisher=EDENLOAD
DefaultDirName={localappdata}\Programs\EDENLOAD
DefaultGroupName=EDENLOAD
DisableProgramGroupPage=yes
DisableDirPage=auto
UsePreviousAppDir=no
UsePreviousGroup=no
PrivilegesRequired=lowest
OutputDir=..\output
OutputBaseFilename=EDENLOAD-Setup
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\EDENLOAD.exe
UninstallDisplayName=EDENLOAD
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
Name: "startup"; Description: "Start EDENLOAD with Windows (runs next to the clock)"; GroupDescription: "Options:"

[InstallDelete]
; clean up the previous name (DMTOR)
Type: filesandordirs; Name: "{localappdata}\Programs\DMTOR"
Type: filesandordirs; Name: "{userprograms}\DMTOR"
Type: files; Name: "{userdesktop}\DMTOR.lnk"

[Files]
Source: "..\dist\EDENLOAD\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\extension\*"; DestDir: "{app}\extension"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "guide.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\app.png"; DestDir: "{app}"; DestName: "icon.png"; Flags: ignoreversion

[Icons]
Name: "{group}\EDENLOAD"; Filename: "{app}\EDENLOAD.exe"
Name: "{group}\Connect browser"; Filename: "{app}\EDENLOAD.exe"; Parameters: "--guide"
Name: "{group}\Uninstall EDENLOAD"; Filename: "{uninstallexe}"
Name: "{autodesktop}\EDENLOAD"; Filename: "{app}\EDENLOAD.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "EDENLOAD"; \
  ValueData: """{app}\EDENLOAD.exe"" --tray"; Tasks: startup; Flags: uninsdeletevalue

Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "DMTOR"; Flags: deletevalue

[Run]
; create Music, Videos, Programs, Documents, Torrents and Others in the Downloads folder
Filename: "{app}\EDENLOAD.exe"; Parameters: "--init-folders"; Flags: runhidden waituntilterminated
Filename: "{app}\EDENLOAD.exe"; Parameters: "--guide"; Description: "Connect Chrome / Edge now (opens a short guide)"; \
  Flags: postinstall nowait skipifsilent
Filename: "{app}\EDENLOAD.exe"; Description: "Open EDENLOAD"; Flags: postinstall nowait skipifsilent
; after an automatic (silent) update, reopen EDENLOAD
Filename: "{app}\EDENLOAD.exe"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM EDENLOAD.exe"; Flags: runhidden; RunOnceId: "KillApp"
Filename: "{app}\EDENLOAD.exe"; Parameters: "--unregister"; Flags: runhidden waituntilterminated; RunOnceId: "Unregister"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  { close a running copy (also an old EdenDM.exe) so its files can be replaced }
  Exec(ExpandConstant('{cmd}'), '/C taskkill /F /IM EDENLOAD.exe & taskkill /F /IM DMTOR.exe & taskkill /F /IM EdenDM.exe', '', SW_HIDE,
       ewWaitUntilTerminated, Code);
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  { remember the "start with Windows" choice inside the app's own settings too }
  if CurStep = ssPostInstall then
    if WizardIsTaskSelected('startup') then
    begin
      ForceDirectories(ExpandConstant('{userappdata}\EDENLOAD'));
      SaveStringToFile(ExpandConstant('{userappdata}\EDENLOAD\startup.flag'), '1', False);
    end;
end;
