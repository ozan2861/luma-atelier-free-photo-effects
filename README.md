# Luma Atelier

Windows için çevrimdışı çalışan, Türkçe arayüzlü fotoğraf efekt ve
düzenleme uygulaması. Sinema estetiğinden esinlenen ayrı bir
**Sinema Laboratuvarı** bölümü içerir.

> **Geliştirme aşamasında.** Güncel durum, tamamlanan fazlar ve bilinen
> eksikler için [`PROGRESS.md`](PROGRESS.md) dosyasına bakın.
> Gündelik kullanım için kurulum dosyası Faz 9'da üretilecek.

---

## Gereksinimler

- Windows 11 x64 (Windows 10 test edilmedi)
- Python 3.11 (yalnızca geliştirme için; kurulmuş uygulama Python istemez)

## Geliştirme ortamı kurulumu

```bash
cd "luma-atelier-free-photo-effects"

py -3.11 -m venv .venv
./.venv/Scripts/python.exe -m pip install --upgrade pip --use-feature=truststore
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

> Ağda TLS denetimi (kendinden imzalı kök sertifika) varsa
> `--use-feature=truststore` Windows sertifika deposunu kullanır.
> Sertifika doğrulamasını kapatmayın.

## Çalıştırma

```bash
PYTHONPATH=src ./.venv/Scripts/python.exe -m luma_atelier
```

Yararlı bayraklar:

| Bayrak | İşlevi |
|---|---|
| `--self-test` | Arayüz açmadan bağımlılıkları doğrular, sürümleri yazar |
| `--capture FOTO ÇIKTI.png` | Pencereyi açıp fotoğrafı işler ve ekran görüntüsünü kaydeder |
| `--verbose` | Ayrıntılı günlük |

## Test

```bash
./.venv/Scripts/python.exe -m pytest tests/              # birim + entegrasyon
./.venv/Scripts/python.exe tools/verify_stack.py         # yığın uyumluluğu
./.venv/Scripts/python.exe tools/phase0_e2e.py           # uçtan uca dosya akışı
```

Güvenlik kontrolleri:

```bash
./.venv/Scripts/python.exe tools/security_audit.py .
./.venv/Scripts/python.exe -m bandit -r src tools -ll -ii
./.venv/Scripts/python.exe -m pip_audit -r requirements.txt --strict
```

Görsel denetim:

```bash
./.venv/Scripts/python.exe tools/widget_gallery.py galeri.png --dpi 1.5
```

## Paketleme

```bash
./.venv/Scripts/python.exe tools/make_icon.py            # ikon + kontrol süslemeleri
./.venv/Scripts/python.exe tools/make_version_info.py    # exe sürüm kaynağı
./.venv/Scripts/python.exe -m PyInstaller packaging/LumaAtelier.spec \
    --noconfirm --distpath dist --workpath build
./dist/LumaAtelier/LumaAtelier.exe --self-test
```

Sonuç: `dist/LumaAtelier/` (onedir, yaklaşık 247 MB).

### Masaüstü kısayolu

```bash
./.venv/Scripts/python.exe tools/make_shortcut.py                 # oluştur
./.venv/Scripts/python.exe tools/make_shortcut.py --start-menu    # Başlat menüsüne de
./.venv/Scripts/python.exe tools/make_shortcut.py --remove        # kaldır
```

Kısayol Windows **Known Folder** API'siyle çözülen gerçek masaüstü
konumuna yazılır (bu makinede `OneDrive\Desktop`).

Windows kurulum dosyası (`LumaAtelier-Setup.exe`) Faz 9'da üretilecek;
o zamana kadar kısayol yukarıdaki derlenmiş yapıya işaret eder.

## Proje yapısı

```
src/luma_atelier/
  core/        Marka, yollar, ayarlar  (Qt'ye bağımlı değil)
  imaging/     Piksel modeli, okuma/yazma, efektler  (Qt'ye bağımlı değil)
  ui/          Tema, bileşenler, ekranlar
  services/    İş parçacıkları, önbellek, render kuyruğu
  storage/     SQLite kitaplık, proje ve preset saklama
  app/         Giriş noktası, günlükleme, pencere kabuğu
resources/     İkonlar, yerleşik presetler, LUT'lar, dokular
tests/         pytest paketi
tools/         Doğrulama, ölçüm ve varlık üretme betikleri
packaging/     PyInstaller ve installer yapılandırması
docs/          Mimari, kabul ölçütleri, format matrisi, test raporu
```

**Katman kuralı:** `core` ve `imaging` Qt ithal etmez; tüm görüntü
mantığı ekransız test edilir.

## Belgeler

| Dosya | İçerik |
|---|---|
| [`PROGRESS.md`](PROGRESS.md) | Faz durumu, sıradaki adım, bilinen sorunlar |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Teknoloji seçimleri, modül haritası, renk hattı, ölçümler |
| [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) | Faz kabul ölçütleri ve doğrulama durumu |
| [`docs/FORMAT_SUPPORT.md`](docs/FORMAT_SUPPORT.md) | Test edilmiş giriş/çıkış format matrisi |

## Gizlilik

Uygulama çevrimdışı çalışır. Fotoğraflar veya dosya yolları hiçbir yere
gönderilmez; telemetri yoktur. Günlükler yalnızca yerel diskte tutulur
(`%APPDATA%\LumaAtelier\logs\`).

## Lisanslar

Üçüncü taraf bileşenlerin lisans bildirimleri Faz 9'da
`docs/THIRD_PARTY_NOTICES.md` içinde toplanacak ve kurulum paketine
dahil edilecek. PySide6/Qt LGPL yükümlülükleri dahildir.
