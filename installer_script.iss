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
; 将打包好的整个免安装目录塞进安装包
Source: "dist\小说智读\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "其他任务:";

[Icons]
; 【核心修复】：必须带上 WorkingDir: "{app}"，否则快捷方式启动会因为找不到资源文件夹而闪退
Name: "{autoprograms}\小说智读"; Filename: "{app}\小说智读.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\小说智读"; Filename: "{app}\小说智读.exe"; Tasks: desktopicon; WorkingDir: "{app}"

[Run]
; 【核心修复】：必须带上 WorkingDir: "{app}"，否则安装完成后勾选“立即运行”会闪退
Filename: "{app}\小说智读.exe"; Description: "立即运行 小说智读"; Flags: nowait postinstall skipifsilent; WorkingDir: "{app}"