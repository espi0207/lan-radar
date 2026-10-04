; Instalador de Windows, con Inno Setup 6. Lo compila la CI después de PyInstaller:
;     iscc packaging\windows\lan-radar.iss
; La versión llega en la variable de entorno LANRADAR_VERSION.

#define AppVersion GetEnv("LANRADAR_VERSION")

[Setup]
; Este identificador no se cambia nunca: es lo que hace que una versión nueva se instale
; encima de la anterior en vez de al lado.
AppId={{05120A09-99DF-4911-B8FF-1B94835C183E}
AppName=lan-radar
AppVersion={#AppVersion}
AppVerName=lan-radar {#AppVersion}
AppPublisher=espi0207
AppPublisherURL=https://github.com/espi0207/lan-radar
AppSupportURL=https://github.com/espi0207/lan-radar/issues
DefaultDirName={autopf}\lan-radar
DisableProgramGroupPage=yes
; Sin permisos de administrador se instala solo para quien lo instala (y no sale el aviso
; de "¿Quieres permitir que esta aplicación haga cambios?").
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=lan-radar-windows
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\lan-radar.exe
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; Flags: unchecked

[Files]
Source: "..\..\dist\lan-radar\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\lan-radar"; Filename: "{app}\lan-radar.exe"
Name: "{autodesktop}\lan-radar"; Filename: "{app}\lan-radar.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\lan-radar.exe"; Description: "Abrir lan-radar"; Flags: nowait postinstall skipifsilent
