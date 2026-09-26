#define AppVersion "0.2.5"
[Setup]
AppId={{285C4BC6-8A4D-4DCA-8D18-A8297358A40D}
AppName=人脸采集服务
AppVersion={#AppVersion}
AppPublisher=zookchen
DefaultDirName={localappdata}\Programs\FaceCapture
DefaultGroupName=人脸采集服务
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\installer
OutputBaseFilename=FaceCapture-Setup-{#AppVersion}-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\FaceCapture.exe
SetupIconFile=..\assets\face-capture.ico
AppMutex=FaceCaptureAgent
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes

[Files]
Source: "..\dist\FaceCapture\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\assets\face-capture.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\web\capture-sdk.js"; DestDir: "{app}\integration"; Flags: ignoreversion
Source: "..\examples\integration.html"; DestDir: "{app}\examples"; Flags: ignoreversion
Source: "..\web\capture-sdk.js"; DestDir: "{app}\web"; Flags: ignoreversion

[Icons]
Name: "{userdesktop}\人脸采集服务"; Filename: "{app}\FaceCapture.exe"; WorkingDir: "{app}"; IconFilename: "{app}\face-capture.ico"
Name: "{group}\人脸采集服务"; Filename: "{app}\FaceCapture.exe"; IconFilename: "{app}\face-capture.ico"
Name: "{group}\打开采集测试页面"; Filename: "{app}\FaceCapture.exe"; Parameters: "--open-demo"; IconFilename: "{app}\face-capture.ico"
Name: "{group}\停止采集服务"; Filename: "{app}\FaceCapture.exe"; Parameters: "--stop"; IconFilename: "{app}\face-capture.ico"
Name: "{group}\查看运行日志"; Filename: "{localappdata}\FaceCapture\logs"
Name: "{group}\卸载人脸采集服务"; Filename: "{uninstallexe}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "FaceCapture"; ValueData: """{app}\FaceCapture.exe"" --minimized"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\facecapture"; ValueType: string; ValueData: "URL:Face Capture"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\facecapture"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\facecapture\DefaultIcon"; ValueType: string; ValueData: "{app}\FaceCapture.exe,0"
Root: HKCU; Subkey: "Software\Classes\facecapture\shell\open\command"; ValueType: string; ValueData: """{app}\FaceCapture.exe"" ""%1"""

[Run]
Filename: "{app}\FaceCapture.exe"; Flags: nowait

[UninstallRun]
Filename: "{app}\FaceCapture.exe"; Parameters: "--stop"; Flags: runhidden waituntilterminated; RunOnceId: "StopFaceCapture"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var Code: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\FaceCapture.exe')) then
    if not Exec(ExpandConstant('{app}\FaceCapture.exe'), '--stop', '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
      Result := '无法停止现有采集服务，请先从开始菜单停止服务。';
end;
