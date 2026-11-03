; =========================================================================
; INNO SETUP SCRIPT: THUNDER Studio — PUBG Mobile Highlight Automation Studio
; Professional Windows Standalone Installer Builder (Zero Dependencies Required)
; Embedded Python Runtime + No Console CMD Window
; (c) 2026 MAAKTHUNDER Studios. All Rights Reserved.
; =========================================================================

#define MyAppName "THUNDER Studio"
#define MyAppFullName "THUNDER — PUBG Mobile Highlight Automation Studio"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "MAAKTHUNDER Studios"
#define MyAppURL "https://maakthunder-studio.web.app"
#define MyAppExeName "THUNDER Studio.exe"

[Setup]
; Unique App ID (Persistent GUID across updates)
AppId={{5D89F4B1-3E2A-4C78-9B1D-THUNDERSTUDIO2026}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppFullName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/version.json
DefaultDirName={autopf}\{#MyAppPublisher}\{#MyAppName}
DefaultGroupName={#MyAppPublisher}\{#MyAppName}
AllowNoIcons=yes

; Mandatory Legal Agreement & ReadMe Screens
LicenseFile=LICENSE_AND_DISCLAIMER.txt
InfoBeforeFile=INFO_BEFORE.txt

; Visual Styling & Branding
SetupIconFile=assets\thunder_app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
OutputDir=dist_installer
OutputBaseFilename=THUNDER_Studio_Setup_v1.0.0

; Version Information Embedded in the Setup .exe Metadata
VersionInfoVersion=1.0.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppFullName} Setup
VersionInfoCopyright=(c) 2026 MAAKTHUNDER Studios
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion=1.0.0.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Standalone compiled binaries & all dependencies (Self-contained, No Python installation required)
Source: "dist_bin\THUNDER Studio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "LICENSE_AND_DISCLAIMER.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "INFO_BEFORE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "launch_thunder.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu Folder Shortcuts
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\THUNDER Web Portal & License Admin"; Filename: "{#MyAppURL}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

; Desktop Shortcut (Direct launch with official app icon, NO console window)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
