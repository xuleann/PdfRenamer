; ============================================================
; Inno Setup 6 script for PdfRenamer
; Compile: build\innosetup\ISCC.exe build\installer.iss
; Output : <project-root>\dist\PdfRenamer_setup.exe
; ============================================================
#define MyAppName "PdfRenamer"
#define MyAppVersion "1.6.5"
#define MyAppPublisher "Local Desktop Tool"
#define MyAppURL "https://localhost/"
#define MyAppExeName "PdfRenamer.exe"
#define MyRoot AddBackslash(SourcePath) + ".."

[Setup]
AppId={{8F3A6C21-9B7D-4E52-A1C4-6D0E5F2B7A93}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=no
OutputDir={#MyRoot}\dist
OutputBaseFilename=PdfRenamer_setup
SetupIconFile={#MyRoot}\assets\app.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest
; 卸载时保留 %APPDATA%\PdfRenamer（用户配置与还原日志）

[Languages]
Name: "chinesesimplified"; MessagesFile: "{#MyRoot}\build\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
Source: "{#MyRoot}\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyRoot}\docs\*.docx"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#MyRoot}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyRoot}\config\default_config.json"; DestDir: "{app}\config"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 PdfRenamer"; Flags: nowait postinstall skipifsilent

[Messages]
BeveledLabel=PdfRenamer - 本地 PDF 信息提取与批量更名
