; Inno Setup script for PageTurner. Built by build_installer.bat - you don't
; need to run this by hand. Output: installer\Output\PageTurner-Setup-1.1.1.exe

#define AppName "PageTurner"
#define AppVersion "1.1.1"
#define AppExe "PageTurner.exe"

[Setup]
; Keep this AppId the same forever - it lets new versions upgrade old ones.
AppId={{6F1C2B7E-4D3A-4E8B-9A51-2C7D8E0F3B19}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=PageTurner
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Asks "install for all users (admin) or just me" - like 7-Zip.
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=PageTurner-Setup-{#AppVersion}
SetupIconFile=..\assets\logo.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\PageTurner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "PageTurner.Reader"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; --- One file type (ProgID) per format: name, icon and how to open it
Root: HKA; Subkey: "Software\Classes\PageTurner.pdf"; ValueType: string; ValueName: ""; ValueData: "PDF Document"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\PageTurner.pdf\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\PageTurner.exe,0"
Root: HKA; Subkey: "Software\Classes\PageTurner.pdf\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "PageTurner"
Root: HKA; Subkey: "Software\Classes\PageTurner.pdf\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PageTurner.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\PageTurner.epub"; ValueType: string; ValueName: ""; ValueData: "EPUB Book"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\PageTurner.epub\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\PageTurner.exe,0"
Root: HKA; Subkey: "Software\Classes\PageTurner.epub\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "PageTurner"
Root: HKA; Subkey: "Software\Classes\PageTurner.epub\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PageTurner.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\PageTurner.mobi"; ValueType: string; ValueName: ""; ValueData: "MOBI Book"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\PageTurner.mobi\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\PageTurner.exe,0"
Root: HKA; Subkey: "Software\Classes\PageTurner.mobi\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "PageTurner"
Root: HKA; Subkey: "Software\Classes\PageTurner.mobi\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PageTurner.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\PageTurner.fb2"; ValueType: string; ValueName: ""; ValueData: "FictionBook"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\PageTurner.fb2\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\PageTurner.exe,0"
Root: HKA; Subkey: "Software\Classes\PageTurner.fb2\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "PageTurner"
Root: HKA; Subkey: "Software\Classes\PageTurner.fb2\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PageTurner.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\PageTurner.xps"; ValueType: string; ValueName: ""; ValueData: "XPS Document"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\PageTurner.xps\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\PageTurner.exe,0"
Root: HKA; Subkey: "Software\Classes\PageTurner.xps\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "PageTurner"
Root: HKA; Subkey: "Software\Classes\PageTurner.xps\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PageTurner.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\PageTurner.cbz"; ValueType: string; ValueName: ""; ValueData: "Comic Book Archive"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\PageTurner.cbz\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\PageTurner.exe,0"
Root: HKA; Subkey: "Software\Classes\PageTurner.cbz\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "PageTurner"
Root: HKA; Subkey: "Software\Classes\PageTurner.cbz\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PageTurner.exe"" ""%1"""

; --- Adds PageTurner to the "Open with" list of each format
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "PageTurner.pdf"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.epub\OpenWithProgids"; ValueType: string; ValueName: "PageTurner.epub"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.mobi\OpenWithProgids"; ValueType: string; ValueName: "PageTurner.mobi"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.fb2\OpenWithProgids"; ValueType: string; ValueName: "PageTurner.fb2"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.xps\OpenWithProgids"; ValueType: string; ValueName: "PageTurner.xps"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.cbz\OpenWithProgids"; ValueType: string; ValueName: "PageTurner.cbz"; ValueData: ""; Flags: uninsdeletevalue

; --- "Open with PageTurner" entry in the right-click menu (like 7-Zip)
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\PageTurner"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Open with PageTurner"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\PageTurner"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\PageTurner.exe,0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\PageTurner\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PageTurner.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.epub\shell\PageTurner"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Open with PageTurner"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.epub\shell\PageTurner"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\PageTurner.exe,0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.epub\shell\PageTurner\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PageTurner.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.mobi\shell\PageTurner"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Open with PageTurner"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.mobi\shell\PageTurner"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\PageTurner.exe,0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.mobi\shell\PageTurner\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PageTurner.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.fb2\shell\PageTurner"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Open with PageTurner"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.fb2\shell\PageTurner"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\PageTurner.exe,0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.fb2\shell\PageTurner\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PageTurner.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xps\shell\PageTurner"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Open with PageTurner"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xps\shell\PageTurner"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\PageTurner.exe,0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xps\shell\PageTurner\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PageTurner.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.cbz\shell\PageTurner"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Open with PageTurner"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.cbz\shell\PageTurner"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\PageTurner.exe,0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.cbz\shell\PageTurner\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PageTurner.exe"" ""%1"""

; --- Registers the program itself (Open with dialog, Win+R, Default apps)
Root: HKA; Subkey: "Software\Classes\Applications\PageTurner.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "PageTurner"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\PageTurner.exe\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\PageTurner.exe,0"
Root: HKA; Subkey: "Software\Classes\Applications\PageTurner.exe\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PageTurner.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\Applications\PageTurner.exe\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\PageTurner.exe\SupportedTypes"; ValueType: string; ValueName: ".epub"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\PageTurner.exe\SupportedTypes"; ValueType: string; ValueName: ".mobi"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\PageTurner.exe\SupportedTypes"; ValueType: string; ValueName: ".fb2"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\PageTurner.exe\SupportedTypes"; ValueType: string; ValueName: ".xps"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\PageTurner.exe\SupportedTypes"; ValueType: string; ValueName: ".cbz"; ValueData: ""
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\PageTurner.exe"; ValueType: string; ValueName: ""; ValueData: "{app}\PageTurner.exe"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\PageTurner\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "PageTurner"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\PageTurner\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "A simple reader for PDF and EPUB books."
Root: HKA; Subkey: "Software\PageTurner\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: "{app}\PageTurner.exe,0"
Root: HKA; Subkey: "Software\PageTurner\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "PageTurner.pdf"
Root: HKA; Subkey: "Software\PageTurner\Capabilities\FileAssociations"; ValueType: string; ValueName: ".epub"; ValueData: "PageTurner.epub"
Root: HKA; Subkey: "Software\PageTurner\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mobi"; ValueData: "PageTurner.mobi"
Root: HKA; Subkey: "Software\PageTurner\Capabilities\FileAssociations"; ValueType: string; ValueName: ".fb2"; ValueData: "PageTurner.fb2"
Root: HKA; Subkey: "Software\PageTurner\Capabilities\FileAssociations"; ValueType: string; ValueName: ".xps"; ValueData: "PageTurner.xps"
Root: HKA; Subkey: "Software\PageTurner\Capabilities\FileAssociations"; ValueType: string; ValueName: ".cbz"; ValueData: "PageTurner.cbz"
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "PageTurner"; ValueData: "Software\PageTurner\Capabilities"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start PageTurner now"; Flags: nowait postinstall skipifsilent
Filename: "ms-settings:defaultapps?registeredAppMachine=PageTurner"; Description: "Make PageTurner my default reader (opens Windows Settings)"; Flags: shellexec postinstall skipifsilent unchecked; Check: IsAdminInstallMode
Filename: "ms-settings:defaultapps?registeredAppUser=PageTurner"; Description: "Make PageTurner my default reader (opens Windows Settings)"; Flags: shellexec postinstall skipifsilent unchecked; Check: not IsAdminInstallMode
