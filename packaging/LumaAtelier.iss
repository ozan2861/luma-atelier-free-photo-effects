; Luma Atelier - Windows kurulum betigi (Inno Setup 6)
;
; Uretim:
;     .venv\Scripts\python.exe tools\build_installer.py
;
; Tasarim kararlari
; -----------------
; * **Kullanici basina kurulum.** Yonetici hakki istenmez; UAC penceresi
;   cikmaz. Boylece kisitli hesaplarda da kurulabilir.
; * **Kaldirma kullanici fotograflarina dokunmaz.** Yalnizca programin
;   kendi dosyalari silinir; ayarlar ve onbellek ayri sorulur, cikti
;   klasoru hicbir kosulda silinmez.
; * **.luma dosya iliskilendirmesi** kullanici kovaninda yapilir.

#define AppName        "Luma Atelier"
#define AppVersion     "0.1.0"
#define AppPublisher   "Luma Atelier"
#define AppExeName     "LumaAtelier.exe"
#define AppId          "{{9C2F4A16-5B7D-4E3A-9F21-7C8D4B2E6A05}"
#define ProjectExt     ".luma"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=LumaAtelier-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Yonetici hakki gerektirmez; kurulum kullanici profiline yapilir
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
SetupIconFile=..\resources\icons\app.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName} {#AppVersion}
CloseApplications=yes
RestartApplications=no
; Uygulama tamamen cevrimdisi calisir; kurulum da oyle
AppSupportURL=
AppUpdatesURL=

[Languages]
Name: "turkce"; MessagesFile: "compiler:Languages\Turkish.isl"

[CustomMessages]
turkce.CreateDesktopIcon=Masaüstü kısayolu oluştur
turkce.AssociateFiles=%1 proje dosyalarını {#AppName} ile aç
turkce.LaunchAfterInstall={#AppName} uygulamasını başlat
turkce.KeepSettings=Ayarlarım ve görünümlerim korunsun
turkce.PhotosSafe=Fotoğraflarınız ve dışa aktardığınız dosyalar silinmez.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"
Name: "associate"; Description: "{cm:AssociateFiles,{#ProjectExt}}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Yukseltmede eski surumun _internal klasoru **once** silinir.
; Aksi halde kaldirilan bir bagimliligin DLL'i yerinde kalir ve yeni
; surum onu yukleyebilir. Kullanici verisi burada degil
; (%APPDATA%\LumaAtelier); etkilenmez.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; PyInstaller onedir ciktisinin tamami
Source: "..\dist\LumaAtelier\{#AppExeName}"; DestDir: "{app}"; \
    Flags: ignoreversion
Source: "..\dist\LumaAtelier\_internal\*"; DestDir: "{app}\_internal"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; \
    Comment: "Fotoğraf efekt stüdyosu"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; \
    Comment: "Fotoğraf efekt stüdyosu"; Tasks: desktopicon

[Registry]
; .luma dosya iliskilendirmesi - kullanici kovani, yonetici gerekmez
Root: HKCU; Subkey: "Software\Classes\{#ProjectExt}"; \
    ValueType: string; ValueName: ""; ValueData: "LumaAtelier.Project"; \
    Flags: uninsdeletevalue; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\LumaAtelier.Project"; \
    ValueType: string; ValueName: ""; ValueData: "{#AppName} projesi"; \
    Flags: uninsdeletekey; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\LumaAtelier.Project\DefaultIcon"; \
    ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"; \
    Tasks: associate
Root: HKCU; Subkey: "Software\Classes\LumaAtelier.Project\shell\open\command"; \
    ValueType: string; ValueName: ""; \
    ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: associate

; "Birlikte ac" listesinde gorunsun; yalnizca varsayilan kayit
; bazi Windows surumlerinde Explorer tarafindan gec taninir.
Root: HKCU; Subkey: "Software\Classes\{#ProjectExt}\OpenWithProgids"; \
    ValueType: string; ValueName: "LumaAtelier.Project"; ValueData: ""; \
    Flags: uninsdeletevalue; Tasks: associate

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchAfterInstall}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; PyInstaller calisirken uretilen gecici klasorler
Type: filesandordirs; Name: "{app}\_internal\__pycache__"

[Code]
{ Kaldirmada kullanici verisi: ayarlar ve onbellek AYRI sorulur.
  Fotograflar, projeler ve disa aktarilan dosyalar **hicbir kosulda**
  silinmez - onlar kullanicinin kendi belgeleri. }

{ Uygulamanin kullandigi gercek klasorler. Bunlar
  luma_atelier/core/paths.py ile ayni olmak zorunda:
    user_data_dir() -> %APPDATA%\LumaAtelier
    cache_dir()     -> %LOCALAPPDATA%\LumaAtelier\cache
  Onceki surumde burada '{localappdata}\Luma Atelier' (bosluklu, yanlis
  kok) yaziyordu; o klasor hic olusmadigi icin kullanicinin "ayarlar da
  silinsin" secimi hicbir sey yapmiyordu. }

function SettingsDir(): String;
begin
  Result := ExpandConstant('{userappdata}\LumaAtelier');
end;

function CacheDir(): String;
begin
  Result := ExpandConstant('{localappdata}\LumaAtelier');
end;

function UserDataExists(): Boolean;
begin
  Result := DirExists(SettingsDir()) or DirExists(CacheDir());
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if not UserDataExists() then
      Exit;
    if MsgBox(
        'Luma Atelier ayarlarınız, kendi görünümleriniz, LUT dosyalarınız' + #13#10 +
        've önbelleğiniz bilgisayarda kalsın mı?' + #13#10#13#10 +
        'Fotoğraflarınız, projeleriniz (.luma) ve dışa aktardığınız' + #13#10 +
        'dosyalar hiçbir durumda silinmez; bu soru yalnızca uygulamanın' + #13#10 +
        'kendi klasörleri içindir.' + #13#10#13#10 +
        'Evet = kalsın    Hayır = uygulama verileri de silinsin',
        mbConfirmation, MB_YESNO) = IDNO then
    begin
      if DirExists(SettingsDir()) then
        DelTree(SettingsDir(), True, True, True);
      if DirExists(CacheDir()) then
        DelTree(CacheDir(), True, True, True);
    end;
  end;
end;
