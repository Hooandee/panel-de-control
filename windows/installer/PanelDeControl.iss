; Panel de Control for Windows: Game Bar widget and app, plus the read-only service.
; CI sets PDC_VERSION and PDC_PAYLOAD (folder with the .msix, Dependencies\*.appx and service\*).

#define AppVersion GetEnv("PDC_VERSION")
#if AppVersion == ""
  #define AppVersion "0.0.0"
#endif
#define Payload GetEnv("PDC_PAYLOAD")
#if Payload == ""
  #define Payload "..\..\artifacts\installer-payload"
#endif

[Setup]
AppId={{6E3B8F5A-2C4D-4E7B-9A1F-5D8C3B2A7E41}
AppName=Panel de Control
AppVersion={#AppVersion}
AppVerName=Panel de Control {#AppVersion}
AppPublisher=Hooandee
AppPublisherURL=https://github.com/Hooandee/panel-de-control
AppSupportURL=https://github.com/Hooandee/panel-de-control/issues
DefaultDirName={autopf}\PanelDeControl\Setup
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
OutputDir=..\..\artifacts\installer
OutputBaseFilename=PanelDeControl-Windows-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupIconFile=PanelDeControl.ico
UninstallDisplayIcon={app}\PanelDeControl.ico
UninstallDisplayName=Panel de Control
CloseApplications=no

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#Payload}\*"; DestDir: "{tmp}\payload"; Flags: recursesubdirs createallsubdirs deleteafterinstall
Source: "install.ps1"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "uninstall.ps1"; DestDir: "{app}"
Source: "PanelDeControl.ico"; DestDir: "{app}"
Source: "PanelDeControl.cer"; DestDir: "{app}"

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\uninstall.ps1"" -Log ""{commonappdata}\PanelDeControl\uninstall.log"" -Certificate ""{app}\PanelDeControl.cer"""; Flags: runhidden waituntilterminated; RunOnceId: "RemovePanelDeControl"

[Messages]
es.FinishedLabel=Panel de Control ya está instalado. Ábrelo con Xbox Game Bar (Win+G), en Widgets, o desde el menú Inicio.
en.FinishedLabel=Panel de Control is installed. Open it from Xbox Game Bar (Win+G), under Widgets, or from the Start menu.

[CustomMessages]
es.Installing=Instalando el widget y el servicio…
en.Installing=Installing the widget and the service…
es.InstallFailed=No se pudo terminar la instalación. El registro está en:%n%n%1
en.InstallFailed=Setup could not finish. The log is at:%n%n%1

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  LogPath: String;
begin
  if CurStep <> ssPostInstall then
    Exit;

  LogPath := ExpandConstant('{commonappdata}\PanelDeControl\install.log');
  ForceDirectories(ExtractFileDir(LogPath));
  WizardForm.StatusLabel.Caption := CustomMessage('Installing');
  if not Exec('powershell.exe',
      '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{tmp}\install.ps1') +
      '" -Payload "' + ExpandConstant('{tmp}\payload') + '" -Log "' + LogPath + '"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
    MsgBox(FmtMessage(CustomMessage('InstallFailed'), [LogPath]), mbError, MB_OK);
end;
