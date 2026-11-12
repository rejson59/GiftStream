#ifndef AppVersion
  #define AppVersion "0.3.0"
#endif

[Setup]
AppId={{B2916C12-8854-4E60-A62B-6A24DD8A813F}
AppName=GiftStream
AppVersion={#AppVersion}
AppPublisher=GiftStream
DefaultDirName={localappdata}\Programs\GiftStream
DefaultGroupName=GiftStream
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64
OutputDir=..\release-assets
OutputBaseFilename=GiftStream-Setup-win-x64
UninstallDisplayIcon={app}\GiftStream.exe
SetupIconFile=..\assets\giftstream.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
Uninstallable=yes

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"

[Tasks]
Name: "desktopicon"; Description: "Utwórz skrót GiftStream na pulpicie"; GroupDescription: "Dodatkowe skróty:"; Flags: unchecked

[Files]
Source: "..\release-assets\GiftStream.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\release-assets\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{autoprograms}\GiftStream"; Filename: "{app}\GiftStream.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\GiftStream"; Filename: "{app}\GiftStream.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Instalowanie składnika Microsoft Edge WebView2..."; Flags: runhidden waituntilterminated
Filename: "{app}\GiftStream.exe"; Description: "Uruchom GiftStream"; Flags: postinstall nowait skipifsilent
