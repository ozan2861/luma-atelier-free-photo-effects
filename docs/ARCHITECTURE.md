# Luma Atelier — Mimari

Son güncelleme: 17 Eylül 2026 (Faz 0–2)

## 1. Teknoloji seçimi ve gerekçesi

| Katman | Seçim | Sürüm | Gerekçe |
|---|---|---|---|
| Dil | Python | 3.11.9 | PySide6, OpenCV, tifffile, imagecodecs için en geniş tekerlek (wheel) desteği. Makinedeki 3.14 için OpenCV/PySide6 tekerlekleri henüz yok. |
| Arayüz | PySide6 **QtWidgets** | 6.9.1 | Aşağıda gerekçesi. |
| Sayısal | NumPy | 2.2.6 | float32 piksel modeli. |
| Görüntü işleme | OpenCV (headless) | 4.11.0.86 | SIMD + çok çekirdekli filtreler, yeniden boyutlandırma, blur. `headless` sürüm seçildi: GUI bağımlılıkları Qt ile çakışmasın ve paket küçülsün. |
| Dosya G/Ç | Pillow | 12.3.0 | JPEG/PNG/WebP okuma-yazma, EXIF, ICC (`ImageCms`). |
| 16-bit TIFF | tifffile + imagecodecs | 2025.5.10 / 2025.3.30 | Pillow bazı 16-bit TIFF varyantlarını 8-bit'e düşürür; tifffile bit derinliğini korur (test: `test_tiff_16bit_preserves_every_level`). |
| EXIF yazma | piexif | 1.1.3 | Yön etiketi ve metadata düzenleme. |
| Paketleme | PyInstaller (onedir) | 6.14.1 | Aşağıda gerekçesi. |
| Kurulum | Inno Setup 6 | *henüz kurulu değil* | Faz 9'da kurulacak. Bkz. Bilinen engeller. |

### Neden QtWidgets, QML değil

Gereksinim belgesi başlangıç önerisi olarak Qt Quick/QML veriyor ve gerekçeli değişikliğe izin veriyor. QtWidgets seçildi:

1. **Özel çizim gerektiren kontroller baskın.** Eğri editörü, renk çarkları, histogram, fırça maskesi, önce/sonra sürgüsü, kırpma tutamakları — hepsi piksel düzeyinde `QPainter` işi. QtWidgets'ta bu doğrudan; QML'de her biri için ayrı `QQuickPaintedItem` veya shader gerekir.
2. **Paketleme riski düşük.** QML paketlerken `qmldir`, plugin ve tip kaydı toplama adımları PyInstaller'da sık kırılır. Faz 0'ın kabul ölçütü paketleme riskini başa almak; widget yolu ilk denemede çalıştı.
3. **Tuval çoğunlukla durağan.** Sahne grafiği/GPU animasyon avantajı bu üründe karşılık bulmuyor; maliyet önizleme render'ında, çizimde değil.

Karşılığında kaybedilen: hazır akıcı animasyon ve deklaratif düzen. Bunlar jetonlaştırılmış QSS + `QPropertyAnimation` ile karşılanıyor.

### Neden PyInstaller onedir

- Açılış süresi onefile'a göre belirgin kısa; onefile her çalıştırmada ~250 MB'ı geçici klasöre açar.
- SmartScreen/antivirüs onedir'e daha az takılır; UPX sıkıştırma bilerek kapalı (yanlış pozitifleri artırır).
- Inno Setup dosyaları zaten kendisi kuracağı için tek dosya avantajı yok.

## 2. Modül haritası

```
src/luma_atelier/
  core/          Marka, yollar, ayarlar — Qt'ye bağımlı değil
    branding.py  Tek noktadan uygulama adı/sürümü
    paths.py     Windows Known Folder çözümlemesi, kullanıcı veri konumları
  imaging/       Saf görüntü işleme — Qt'ye bağımlı değil, headless test edilir
    pixels.py    float32 piksel modeli, sRGB<->lineer, alpha, karışım
    loader.py    Okuma: format, bit derinliği, EXIF yönü, ICC
    saver.py     Yazma: atomik, format seçenekleri, çakışma yönetimi
    effects/     (Faz 3) Efekt kayıt sistemi ve algoritmalar
    color/       (Faz 2) Eğriler, HSL, color grading, LUT
    masks/       (Faz 5) Fırça ve parametrik maskeler
  ui/            Yalnızca sunum — görüntü işleme mantığı içermez
    theme/       tokens.py (tasarım jetonları) + stylesheet.py (QSS üretici)
    widgets/     Yeniden kullanılabilir kontroller
    views/       Ekranlar
  services/      (Faz 2) İş parçacığı havuzu, render kuyruğu, önbellek
  storage/       (Faz 5) SQLite kitaplık, .luma proje, preset G/Ç
  app/           Giriş noktası, günlükleme, pencere kabuğu
```

**Katman kuralı:** `imaging` ve `core` Qt ithal etmez. Bu sayede tüm görüntü mantığı ekransız test edilir (`QT_QPA_PLATFORM=offscreen` bile gerekmez) ve ileride farklı bir arayüze taşınabilir.

## 3. Piksel modeli ve renk hattı

Motorun tek veri tipi:

```
float32, şekil (Y, X, 3) veya (Y, X, 4), nominal aralık 0..1
kanal sırası RGB, alpha düz (straight, premultiplied değil)
```

- **Aralık nominal.** Ara adımlarda 1.0 üstü değerler korunur; parlak alan bilgisi yalnızca dosyaya yazarken kırpılır. Faz 0 ölçümü: +0.55 stop pozlamada piksellerin %15.6'sı 1.0 üstüne çıkıyor — bu bilgi erken kırpılsaydı halation/bloom yanlış çalışırdı.
- **Varsayılan kodlama sRGB** (display-referred). Işık toplayan işlemler (blur, bloom, halation, pozlama) `srgb_to_linear` ile lineer ışığa geçer, işini orada yapar, `linear_to_srgb` ile döner.
- **Negatif ve 1.0 üstü değerler** transfer fonksiyonunda tek taraflı (odd) uzantı ile korunur.
- **8-bit'e ara dönüş yok.** Ölçülen kanıt: tipik 4 adımlı zincir float32'de 49.589 ton korurken, her adımda 8-bit'e dönen aynı zincir 212 tona düşüyor (`tools/verify_stack.py`).

### Giriş renk yönetimi

1. Dosyada ICC profili varsa `ImageCms` ile sRGB'ye dönüştürülür.
2. Profil yoksa sRGB varsayılır ve bu varsayım `ImageMetadata.assumed_srgb = True` olarak kaydedilir (gizlenmez).
3. EXIF `Orientation` okunur ve **piksellere uygulanır**; sonrasında görüntü görsel olarak diktir.

## 4. Performans yaklaşımı

Ölçüm cihazı: Intel i7-13700H (14 çekirdek / 20 iş parçacığı), 32 GB RAM, Windows 11 Pro 26200.

| İşlem | 9.2 MP (3840×2400) | Not |
|---|---|---|
| JPEG okuma + float32'ye dönüşüm | 104 ms | |
| sRGB→lineer→sRGB çift dönüşüm | 512 ms | `cv2.pow` ile; `np.power` 744 ms idi |
| Pozlama (tam zincir) | 499 ms | |
| JPEG yazma (q92) | 253 ms | |
| 16-bit TIFF yazma | 185 ms | |

**Optimizasyon kararı:** `np.power` yerine `cv2.pow`. Aynı girdide 372 ms → 236 ms (1.6×), maksimum sapma 5e-07 (float32 için önemsiz). İki tuzak ele alındı: OpenCV tek boyutlu diziyi N×N matris sanıp devasa ayırma denedi; ve sürekli (contiguous) bellek bekliyor.

**Önizleme stratejisi:** uzun kenar ~1600–2048 px. 9.2 MP'lik çift dönüşüm 512 ms ise, 2.6 MP'lik önizleme ~145 ms — hedef aralıkta (150–300 ms). Faz 2'de iş parçacığı havuzu ve iptal mekanizmasıyla ölçülecek.

### Faz 2 optimizasyonu: 781 ms → 272 ms

İlk ölçümde 5 katmanlı bir tarif 2 MP önizlemede **781 ms** sürüyordu — hedefin (150–300 ms) çok üstünde. Darboğazlar ölçülüp sırayla giderildi:

| Değişiklik | Kazanç | Not |
|---|---|---|
| Ton açısı hesabı elle NumPy yerine `cv2.cvtColor` (float32 HSV) | 150 ms → **1.8 ms** | ölçülen sapma 0.008°; 8-bit HSV'nin bantlaşması yok çünkü giriş float32 kalıyor |
| Transfer fonksiyonunda negatifsiz hızlı yol | 51 ms → **34 ms** | sonuç birebir aynı; `abs`/`copysign` atlanıyor |
| Ton maskelerinde `cv2.pow` | ~40 ms tasarruf | |
| `shadows_highlights` maskesi tek kanaldan | ~28 ms tasarruf | üç kanalı dönüştürmek yerine yalnızca parlaklık |
| `vibrance` içinde yerinde (in-place) matematik | ~45 ms tasarruf | geçici dizi sayısı azaldı |
| **Alan (domain) gruplaması + kanonik sıra** | 6 transfer dönüşümü → **2** | aşağıda |

**Alan gruplaması.** Her işlem hangi veri alanında çalıştığını bildirir (`Operation.domain`: `"srgb"` veya `"linear"`). Motor alanı takip eder ve transfer dönüşümünü yalnızca alan *değiştiğinde* yapar. Tek başına bu yetmedi: tarif sırası lineer/sRGB arasında gidip geliyordu. Bu yüzden `Recipe.set_or_add` işlemi **kanonik konuma** yerleştirir (`Operation.stack_order`):

```
10 linear  color.white_balance
11 linear  tone.exposure
12 linear  tone.shadows_highlights
20 srgb    tone.black_white_point
21 srgb    tone.contrast
...
```

Bu sıra hem fotoğraf düzenleme akışına uygun (beyaz dengesi → pozlama → ton → renk → ayrıntı) hem de aynı alandaki işlemleri toplar. Doğrulandı: gruplama sonucu **bit düzeyinde değiştirmiyor** (`test_domain_grouping_does_not_change_result`, ölçülen fark 0.0).

Kullanıcının efekt listesinden elle eklediği işlemler `add()` ile yığının sonuna gider ve bu sıralamaya tabi değildir; sıra kullanıcının denetiminde kalır.

### %100 görünüm ve detay karosu

Tuval bir **önizleme** üzerinde çalışır (uzun kenar 1800 px). Bu, önizlemeyi büyüttüğünde %100 görünümün bulanık olması demekti — oysa gereksinim "yüzde 100 görünüm gerçek kaliteyi gösterebilsin" diyor.

Çözüm: zoom 1.0'ı aştığında `ImageCanvas` görünen bölgeyi *kaynak* koordinatlarında bildirir, `RenderService.render_tile` o bölgeyi tam çözünürlükte render eder ve tuval bunu önizlemenin üzerine çizer. Karo, komşu piksel okuyan işlemler (blur, clarity) için 96 px kenar payıyla işlenir ve sonra kırpılır; karo sınırı görünmez.

Sınır: global istatistik gerektiren bir işlem eklenirse bu yaklaşım tek başına yetmez ve ayrıca ele alınmalıdır. Şu anda böyle bir işlem yok.

## 5. Veri şemaları

| Veri | Biçim | Konum | Sürüm alanı |
|---|---|---|---|
| Uygulama ayarları | JSON | `%APPDATA%\LumaAtelier\settings.json` | evet |
| Kitaplık, favoriler, son projeler | SQLite | `%APPDATA%\LumaAtelier\library.sqlite3` | `user_version` |
| Preset | JSON | `resources/presets/` (yerleşik), `%APPDATA%\LumaAtelier\presets\` (kullanıcı) | `PRESET_FORMAT_VERSION` |
| Proje | `.luma` (sürümlü paket) | kullanıcının seçtiği yer | `PROJECT_FORMAT_VERSION` |
| Önbellek | ikili + JSON dizin | `%LOCALAPPDATA%\LumaAtelier\cache\` | — |
| Günlük | metin (döngüsel) | `%APPDATA%\LumaAtelier\logs\luma.log` | — |

Görüntülerin tamamı veritabanına konmaz; SQLite yalnızca yol, metadata ve küçük resim referansı tutar.

## 6. Windows entegrasyonu

- **Known Folder API** (`SHGetKnownFolderPath`) kullanılıyor. OneDrive yönlendirmesinde doğrulandı: masaüstü `C:\Users\<kullanici>\OneDrive\Desktop`, Resimler `C:\Users\<kullanici>\OneDrive\Resimler`. Sabit `Desktop`/`Pictures` varsayımı burada kırılırdı.
- `SetCurrentProcessExplicitAppUserModelID` çağrılıyor; görev çubuğu uygulamayı kendi simgesiyle gruplasın.
- Kullanıcı verisi **hiçbir zaman** kurulum klasörüne yazılmaz.
- `LUMA_DATA_HOME` ortam değişkeni veri kökünü değiştirir (testler ve taşınabilir kullanım).

## 7. Faz 0'da doğrulananlar

`tools/verify_stack.py` — 6/6 geçti:
sürüm raporu · 16-bit TIFF gidiş-dönüş (65536 ton korundu) · float32 hattının 8-bit ara yuvarlamaya karşı üstünlüğü · EXIF yön etiketi · ICC profil zinciri · Qt pencere + QImage/NumPy köprüsü.

`tools/phase0_e2e.py` — 5/5 geçti:
gerçek 9.2 MP JPEG açıldı, +0.55 stop uygulandı, JPEG/PNG/WebP/16-bit TIFF olarak yazıldı, dördü de tekrar açılıp boyut/bit derinliği/renk açısından doğrulandı, kaynak dosyanın SHA-256'sı değişmedi.

`pytest` — 81/81 geçti.

**Paketleme:** `dist/LumaAtelier/LumaAtelier.exe` (247 MB, onedir) oluşturuldu, `--self-test` tüm bağımlılıkları yükledi, `--capture` ile gerçek fotoğrafı açıp işleyip pencereyi çizdiği ekran görüntüsüyle kanıtlandı (`docs/phase0-packaged-capture.png`).

## 8. Bilinen engeller ve açık kararlar

| Konu | Durum |
|---|---|
| Inno Setup 6 | **Kurulu değil.** Faz 9'da gerekli. Kurulum gerektiğinde kullanıcıya bildirilecek. |
| Kod imzalama sertifikası | Yok. İmzasız dağıtım imzalıymış gibi sunulmayacak; SmartScreen uyarısı beklenir. |
| Temiz Windows ortamı | Yok. Faz 9'daki temiz kurulum testi yapılamazsa açıkça işaretlenecek. |
| pip TLS | Ağda kendinden imzalı sertifika var; `--use-feature=truststore` (Windows sertifika deposu) ile çözüldü, doğrulama kapatılmadı. |
| QSS kaydırıcı | `sub-page` groove yerine tüm widget yüksekliğini kaplıyor. Faz 1'de `QPainter` tabanlı özel kaydırıcı yazılacak (uygulamanın zaten çift tıkla sıfırlama, merkez işareti ve ince ayar sürüklemesine ihtiyacı var). |
| Windows 10 | Test edilmedi; destek sözü verilmeyecek. |
