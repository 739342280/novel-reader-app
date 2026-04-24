[Setup]
AppName=小说智读
AppVersion=1.0.0
DefaultDirName={autopf}\小说智读
DefaultGroupName=小说智读
OutputDir=dist_installer
OutputBaseFilename=小说智读_安装版
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin

[Files]
; 【核心变动】：匹配最新流水线里 PyInstaller 引擎输出的免安装基础目录
Source: "dist\小说智读\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "其他任务:";

[Icons]
; 【防闪退核心】：必须带上 WorkingDir: "{app}"，锁定工作目录，防止资源加载失败
Name: "{autoprograms}\小说智读"; Filename: "{app}\小说智读.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\小说智读"; Filename: "{app}\小说智读.exe"; Tasks: desktopicon; WorkingDir: "{app}"

[Run]
; 【防闪退核心】：安装完成后立即运行也必须锁定工作目录
Filename: "{app}\小说智读.exe"; Description: "立即运行 小说智读"; Flags: nowait postinstall skipifsilent; WorkingDir: "{app}"