; Bộ cài PipeCut Studio cho Windows (Inno Setup 6).
;
;   pyinstaller packaging\pipecut.spec --noconfirm --clean
;   "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" /DAppVersion=1.12.0 packaging\installer.iss
;
; Ra dist\PipeCutStudio-<phiên bản>-setup.exe.  Có Vietnamese.isl (bản dịch không
; chính thức của Inno Setup) đặt cạnh tệp này thì bộ cài nói tiếng Việt.

#define AppName "PipeCut Studio"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppExe "PipeCutStudio.exe"

[Setup]
AppId={{6F3C2B9E-1D4A-4C1F-9B7E-5A2E8C4D7F10}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=NL-Rino
AppPublisherURL=https://github.com/NL-Rino/CNC-on-ESP32
AppSupportURL=https://github.com/NL-Rino/CNC-on-ESP32/issues
AppUpdatesURL=https://github.com/NL-Rino/CNC-on-ESP32/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} {#AppVersion}
SetupIconFile=pipecut.ico
OutputDir=..\dist
OutputBaseFilename=PipeCutStudio-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Không có quyền quản trị vẫn cài được (vào thư mục của riêng người dùng)
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog commandline
; Đang mở phần mềm thì đóng lại trước khi ghi đè
CloseApplications=yes
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}

[Languages]
#if FileExists(AddBackslash(SourcePath) + "Vietnamese.isl")
Name: "vi"; MessagesFile: "Vietnamese.isl"
#endif
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
en.GroupExamples=Examples
en.GroupFirmware=FluidNC configs
en.GroupGuide=User guide (docs)
en.GroupConfig=Machine profiles
#if FileExists(AddBackslash(SourcePath) + "Vietnamese.isl")
vi.GroupExamples=Công việc mẫu
vi.GroupFirmware=Cấu hình FluidNC cho ESP32
vi.GroupGuide=Hướng dẫn sử dụng
vi.GroupConfig=Hồ sơ máy mẫu
#endif

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Bản cũ để lại thư viện đã đổi tên thì dọn đi, tránh lẫn phiên bản
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\PipeCutStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Chạy trong thư mục Documents: mọi thứ người dùng lưu mặc định vào đó,
; không vào Program Files (không ghi được)
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{userdocs}"
Name: "{group}\{cm:GroupGuide}"; Filename: "{app}\docs"
Name: "{group}\{cm:GroupExamples}"; Filename: "{app}\examples"
Name: "{group}\{cm:GroupFirmware}"; Filename: "{app}\firmware"
Name: "{group}\{cm:GroupConfig}"; Filename: "{app}\config"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{userdocs}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; WorkingDir: "{userdocs}"; Flags: nowait postinstall skipifsilent
