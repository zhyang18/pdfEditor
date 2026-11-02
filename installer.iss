; Inno Setup 5/6 自动化安装包构建脚本
; 将 dist/PdfEditor 便携目录打包为单一标准 Windows 安装程序 (PdfEditor_Setup.exe)
; 兼顾“单文件便携分发”与“免运行时解压的秒级冷启动”双重优势

#define MyAppName "PDF 编辑器"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "PdfEditorPro"
#define MyAppExeName "PdfEditor.exe"

[Setup]
AppId={{C8E8F5D2-8A73-4E8E-B43B-987762A4DFE1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=PdfEditor_Setup_v{#MyAppVersion}
SetupIconFile=assets\app.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 复制 dist\PdfEditor 便携目录下的所有程序和资源文件
Source: "dist\PdfEditor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Filename: "{app}\{#MyAppExeName}"; Flags: nowait postinstall skipifsilent
