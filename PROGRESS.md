# Luma Atelier — İlerleme Kaydı

> Yeni oturumda: önce bu dosyayı ve `CLAUDE_FOTOGRAF_STUDYOSU_PROMPT.md`
> dosyasını oku. Sonra **Sağlık kontrolü** bölümündeki komutları çalıştırıp
> önceki oturumdan kalanın gerçekten çalıştığını doğrula. Tamamlanmış fazları
> yeniden yazma; **Sıradaki adım** bölümünden devam et.

Son güncelleme: 17 Eylül 2026 — **tüm fazlar tamamlandı**

---

## Durum özeti

| Faz | Başlık | Durum |
|---|---|---|
| 0 | Keşif ve teknik doğrulama | ✅ **tamamlandı** — kabul ölçütleri doğrulandı |
| 1 | Uygulama kabuğu ve kitaplık | ✅ **tamamlandı** — 14/14 kabul kontrolü |
| 2 | Çekirdek görüntü motoru | ✅ **tamamlandı** — 17/17 + 16/16 |
| 3 | Efekt sistemi ve ilk 30 preset | ✅ **tamamlandı** — 120 preset üretildi |
| 4 | Sinema Laboratuvarı | ✅ **tamamlandı** — 26/26 kabul kontrolü |
| 5 | Maskeler ve proje kalıcılığı | ✅ **tamamlandı** — 72/72 kabul kontrolü |
| 6 | Koleksiyonu 120 presete tamamlama | ✅ **tamamlandı** — 21/21 kapsam denetimi |
| 7 | Tam kalite export ve toplu işleme | ✅ **tamamlandı** — 100/100 kabul kontrolü |
| 8 | Görsel kalite, erişilebilirlik, performans | ✅ **tamamlandı** — 31/31 denetim |
| 9 | Kurulum ve son teslim | ✅ **tamamlandı** — 26/26 kabul kontrolü |

Sayılar: **38 gerçek görüntü işlemi** (hedef 35+) · **120 hazır görünüm**
(90 genel + 30 sinematik) · **1171 test geçiyor** · uçtan uca: Faz 0 5/5,
Faz 1 14/14, Faz 2 17/17 + 16/16, Faz 3–4 26/26, Faz 5 72/72, Faz 7 100/100,
Faz 8 31/31, Faz 9 26/26.

**Kurulum dosyası:** `dist/LumaAtelier-Setup-0.1.0.exe` (67 MB) — kuruldu,
masaüstü kısayolundan açıldığı doğrulandı. Kurulu sürümün son test
edilen kodu içerdiği SHA-256 ile kanıtlandı (`tools/verify_installed.py`).

**Son kapsam denetimi (18 Eylül 2026):** `tools/scope_audit.py` 21/21.
Ayrıntı ve bulunan hatalar `TESLIM.md` bölüm 5a'da.

---

## Sağlık kontrolü (her oturum başında çalıştır)

```bash
cd "<proje-klasoru>"

./.venv/Scripts/python.exe tools/verify_stack.py     # beklenen: 6/6 geçti
./.venv/Scripts/python.exe tools/phase0_e2e.py       # beklenen: 5/5 geçti
./.venv/Scripts/python.exe tools/phase1_e2e.py       # beklenen: 14/14 geçti
./.venv/Scripts/python.exe tools/phase2_e2e.py       # beklenen: 17/17 geçti
./.venv/Scripts/python.exe tools/phase2_ui.py        # beklenen: 16/16 geçti
./.venv/Scripts/python.exe tools/phase34_e2e.py     # beklenen: 26/26 geçti
./.venv/Scripts/python.exe tools/make_presets.py --check   # 120 preset denetimi
./.venv/Scripts/python.exe -m pytest tests/          # beklenen: 1035 passed
```

Arayüzü gözle görmek için:

```bash
PYTHONPATH=src ./.venv/Scripts/python.exe -m luma_atelier          # pencere açar
./.venv/Scripts/python.exe tools/widget_gallery.py g.png           # bileşen galerisi
```

Yeniden paketlemek için:

```bash
./.venv/Scripts/python.exe tools/make_icon.py
./.venv/Scripts/python.exe tools/make_version_info.py
./.venv/Scripts/python.exe -m PyInstaller packaging/LumaAtelier.spec \
    --noconfirm --distpath dist --workpath build
./dist/LumaAtelier/LumaAtelier.exe --self-test       # beklenen: SELF-TEST OK
```

Masaüstü kısayolu (Faz 9 installer'ı da aynı mantığı kullanacak):

```bash
./.venv/Scripts/python.exe tools/make_shortcut.py              # oluştur
./.venv/Scripts/python.exe tools/make_shortcut.py --remove     # kaldır
```

---

## Faz 0 — tamamlandı (17 Eylül 2026)

### Yapılanlar

**Ortam ve bağımlılıklar**
- Python 3.11.9 sanal ortamı (`.venv`). 3.14 kuruluydu ama OpenCV/PySide6
  tekerlekleri yok; 3.11 seçildi.
- Sabitlenmiş sürümler: PySide6 6.9.1, NumPy 2.2.6, OpenCV-headless 4.11.0.86,
  Pillow 12.3.0, tifffile 2025.5.10, imagecodecs 2025.3.30, piexif 1.1.3.
- Ağda TLS denetimi var (kendinden imzalı kök sertifika). `pip` Windows
  sertifika deposunu kullanacak şekilde çözüldü (`--use-feature=truststore`);
  sertifika doğrulaması **kapatılmadı**.

**Yazılan modüller**
| Dosya | İçerik |
|---|---|
| `core/branding.py` | Tek noktadan ad/sürüm/şema sürümleri |
| `core/paths.py` | Windows Known Folder çözümlemesi, kullanıcı veri konumları |
| `imaging/pixels.py` | float32 model, sRGB↔lineer, alpha, karışım, kuantizasyon |
| `imaging/loader.py` | Okuma: format, bit derinliği, EXIF yönü, ICC, hata yönetimi |
| `imaging/saver.py` | Yazma: atomik, 4 format, 16-bit TIFF, çakışma yönetimi |
| `ui/theme/tokens.py` | Tasarım jetonları (renk, tipografi, boşluk, ölçü, hareket) |
| `ui/theme/stylesheet.py` | Jetonlardan QSS üretici |
| `app/logging_setup.py` | Yerel döngüsel günlük, yakalanmamış hata kancası |
| `app/main.py` | Giriş noktası; `--self-test`, `--capture`, `--verbose` |
| `app/smoke_window.py` | Faz 0 teknik deneme penceresi |

**Araçlar**
- `tools/verify_stack.py` — yığın uyumluluğu (6 kontrol)
- `tools/phase0_e2e.py` — uçtan uca dosya akışı (5 kontrol)
- `tools/make_icon.py` — uygulama ikonu + 18 kontrol süslemesi (hepsi kod ile çizilir)
- `tools/make_version_info.py` — exe sürüm kaynağı
- `tools/widget_gallery.py` — bileşen galerisi, DPI parametreli

**Belgeler:** `docs/ARCHITECTURE.md`, `docs/ACCEPTANCE.md`,
`docs/FORMAT_SUPPORT.md`, bu dosya.

### Doğrulanan kabul ölçütleri

| Ölçüt | Sonuç |
|---|---|
| Gerçek dosya açıldı | ✅ 3840×2400 JPEG, 104 ms |
| Bir ayar işlendi | ✅ +0.55 stop, ölçülen fark 0.1089 |
| Export edildi | ✅ JPEG/PNG/WebP/16-bit TIFF; dördü de geri okunup doğrulandı |
| Paketlenmiş uygulama çalıştı | ✅ `dist/LumaAtelier/LumaAtelier.exe` (247 MB) |
| Orijinal korundu | ✅ SHA-256 değişmedi |
| Testler | ✅ 81/81 |

Paketlenmiş exe'nin gerçekten çalıştığının kanıtı:
`docs/phase0-packaged-capture.png` — exe başlatıldı, 9.2 MP fotoğraf
yüklendi, +0.55 stop uygulandı, pencere çizildi ve görüntü diske yazıldı.

### Ölçümler (i7-13700H / 32 GB / Win11 26200)

| İşlem | 9.2 MP süre |
|---|---|
| JPEG okuma + float32 | 104 ms |
| sRGB→lineer→sRGB | 512 ms |
| Pozlama (tam zincir) | 499 ms |
| JPEG yazma q92 | 253 ms |
| 16-bit TIFF yazma | 185 ms |

`np.power` → `cv2.pow` değişimiyle transfer fonksiyonu 372 → 236 ms (1.6×),
maksimum sapma 5e-07.

### Yol boyunca bulunan ve düzeltilen gerçek hatalar

1. **cv2.pow 1-B diziyi N×N sanıyordu** → 40 GB bellek istedi. `_pow`
   artık şekil ve süreklilik açısından güvenli. Test: `test_shapes_are_handled`.
2. **QSS kaydırıcı `add-page` tanımsızdı** → dolu kısım tüm yolu kaplıyordu.
   Kısmen düzeltildi (aşağıdaki bilinen sorun).
3. **QSS'te `QLabel` kendi zeminini çiziyordu** → kart içindeki her metin
   koyu kutu gibi görünüyordu. `background: transparent` eklendi.
4. **QComboBox iki ok çiziyordu** → `drop-down`'a `subcontrol-position`
   verilince Qt oku iki yerde çiziyor. Konum kaldırıldı.
5. **Kenarlık üçgeni numarası Qt'de güvenilir değil** → açılır menü ve spin
   okları için yerel PNG varlıklar üretildi.

### Kendi test kurgumda düzelttiğim yanlışlar

Bunlar ürün hatası değildi; yanlış ölçüyordum ve kabul ölçütünü *gevşetmek
yerine* doğru ölçüye çevirdim:

- 8-bit/16-bit "bantlaşma" kontrolü aslında **kliplenmeyi** ölçüyordu.
  Doğru kurgu: float32 zincir ile her adımda 8-bit'e dönen zinciri
  karşılaştırmak (49.589 ton ↔ 212 ton).
- Export gidiş-dönüş karşılaştırmasında referans kırpılmamıştı; dosyaya
  yazarken 1.0 üstü değerler kırpıldığı için kayıpsız formatlar bile
  başarısız görünüyordu.
- WebP renk doğruluğu `max()` ile ölçülüyordu; kayıplı codec'lerde sert
  renk sınırındaki ringing kaçınılmaz. Yama merkezleri + ortalama +
  %99 yüzdelik ile ölçülüyor.


---

## Faz 1 — tamamlandı (17 Eylül 2026)

### Yapılanlar

| Dosya | İçerik |
|---|---|
| `core/session.py` | Kitaplık modeli: içe aktarma, arama, sıralama, favoriler, kayıp dosya, seçim — Qt'ye bağımlı değil |
| `services/thumbnails.py` | Arka planda küçük resim üretimi, disk önbelleği, iptal, önbellek budama |
| `ui/widgets/parameter_slider.py` | QPainter tabanlı özel kaydırıcı |
| `ui/widgets/image_canvas.py` | Zoom/pan tuvali, koordinat dönüşümü, önce/sonra karşılaştırması |
| `ui/widgets/nav_bar.py` | Üst gezinti şeridi, çalışma alanları, gömülü menü çubuğu |
| `ui/views/start_view.py` | Başlangıç ekranı, sürükle-bırak alanı, son projeler, ilk kullanım yardımı |
| `ui/views/library_view.py` | Sanallaştırılmış küçük resim ızgarası, arama, sıralama, favori |
| `app/shell.py` | Ana pencere: çalışma alanları, kısayollar, durum çubuğu, hata bildirimi |
| `tools/phase1_e2e.py` | Faz 1 kabul doğrulaması (14 kontrol, gerçek ekran görüntüleri) |

Testler: `tests/test_session.py` (28), `tests/test_canvas.py` (31).

### Özel kaydırıcı neden yazıldı

QSS kaydırıcısında `sub-page` groove yerine tüm widget yüksekliğini
kaplıyordu (Faz 0 bilinen sorunu #1). Bundan bağımsız olarak fotoğraf
düzenleyicinin ihtiyacı olan davranışlar hazır kontrolde yok:
çift tıkla varsayılana dönüş · çift yönlü parametrelerde merkez işareti
ve merkezden dolan yol · Shift ile ince (1/5), Ctrl ile kaba (3×) ayar ·
sayıya tıklayıp değer yazma · sürüklemenin **tek** geri alma adımı
üretmesi (`editingFinished`) · klavye: oklar, Page Up/Down, Home/End,
Delete ile sıfırlama.

### Doğrulanan kabul ölçütleri

`tools/phase1_e2e.py` — 14/14. Dört format, dikey EXIF, saydamlık,
fotoğraflar arası geçiş, üç pencere boyutu, bozuk dosya izolasyonu,
küçük resim üretimi. Ekran görüntüleri `docs/_captures/faz1-*.png`.

### Yol boyunca bulunan ve düzeltilen gerçek hatalar

1. **Sonsuz döngü (RecursionError).** Kitaplıkta seçim değişimi oturumu
   bilgilendiriyor, oturum kitaplığı tazeliyor, tazeleme seçimi yeniden
   kuruyor ve zincir başa dönüyordu. Testler yine de geçiyordu ama
   yığın taşması günlüğe düşüyordu. `_syncing` yeniden giriş koruyucusu
   eklendi.
2. **Tek içe aktarma kitaplığı iki kez yeniden kuruyordu** —
   `add_paths` hem `set_current(0)` hem kendi `_notify()` çağrısını
   yapıyordu. Test eklendi: `test_import_notifies_exactly_once`.
3. **Menü çubuğu ve gezinti şeridi iki ayrı satırdaydı.** Tek şeritte
   birleştirildi; Alt tuşu erişimi korundu, dikeyde bir satır kazanıldı.
4. **Menü çubuğu kendi koyu zeminini çiziyordu** ve şeridin üstünde blok
   gibi görünüyordu. Şeffaflaştırıldı.
5. **Başlangıç ekranında "Henüz bir proje açmadınız" satırı** liste
   dolduğunda da kalıyordu — `deleteLater` gecikmeli çalıştığı için.
   Önce ebeveynlikten çıkarılıyor.
6. **Bırakma alanı simgesinde fazladan çember** çiziliyordu.

### Faz 1 kapsamında bilerek yapılmayanlar

- Düzenleyicide ton/renk panelleri yok (Faz 2).
- Sinema Laboratuvarı, Dışa Aktar ve Ayarlar çalışma alanları durum
  ekranı gösteriyor; **çalışmayan düğme yok**, hangi fazda geleceği yazılı.
- Proje açma/kaydetme yok (Faz 5); "Proje aç" düğmesi bunu açıkça söylüyor.
- Tek fotoğraf "Kopya olarak kaydet" çalışıyor (Ctrl+S); toplu kuyruk Faz 7.


---

## Faz 2 — tamamlandı (17 Eylül 2026)

### Yapılanlar

| Dosya | İçerik |
|---|---|
| `imaging/effects/base.py` | Efekt altyapısı: parametre şeması, `RenderContext`, kayıt sistemi, alan (domain) bildirimi |
| `imaging/effects/tone.py` | Pozlama, kontrast, gölge/parlak alan, siyah-beyaz nokta, parlaklık, yerel kontrast, fade |
| `imaging/effects/color.py` | Beyaz dengesi, doygunluk, canlılık, HSL (8 aralık), siyah-beyaz karışım, split toning |
| `imaging/recipe.py` | Tahribatsız tarif: sürümlü, JSON'a serileşen, doğrulayan, alan gruplayan |
| `core/history.py` | Geri al/yinele; sürükleme birleştirme (`merge_key`), 120 adım |
| `core/document.py` | Kaynak + tarif + geçmiş; kaynak pikselleri hiç değişmez |
| `services/render.py` | Worker havuzu, istek jetonu ile iptal, `render_tile` (tam çözünürlük karo) |
| `ui/widgets/histogram.py` | RGB + parlaklık histogramı, kırpma uyarısı |
| `ui/widgets/adjustment_panel.py` | `ParamSpec`'ten **otomatik** üretilen kontroller, daraltılabilir bölümler |
| `ui/views/editor_view.py` | Tuval + histogram + ayar panelleri; etkileşimli/tam kalite iki kademeli önizleme |
| `tools/phase2_e2e.py`, `tools/phase2_ui.py` | Kabul doğrulaması (17 + 16 kontrol) |

Testler: `test_effects_contract.py` (267), `test_recipe_history.py` (39).

### Görüntü işlemleri: 13 / 35+

Ton: pozlama · kontrast · gölge-parlak alan · siyah-beyaz nokta · parlaklık
Renk: beyaz dengesi · doygunluk · canlılık · HSL · siyah-beyaz karışım · split toning
Ayrıntı: yerel kontrast · Stil: fade

Kalanlar Faz 3 ve 4'te: eğriler, kanal karıştırıcı, üç bölgeli grading,
vignette, keskinleştirme, gürültü azaltma, Gaussian/radyal/yönlü blur,
tilt-shift, bloom, halation, diffusion, grain, light leak, toz-çizik,
kromatik aberasyon, anamorfik çizgi, duotone, bleach bypass, cross-process,
posterize, kâğıt dokusu, 3D LUT.

### Efekt sözleşmesi (267 otomatik test)

Her kayıtlı işlem şunlara uymak zorunda; yeni işlem eklendiğinde testler
kendiliğinden kapsar:

- Nötr ayar orijinali bozmaz (*dönüşüm* işlemleri bunu açıkça `identity_at_defaults=False` ile bildirir ve o zaman `amount=0` birebir kimliktir)
- NaN/Inf üretmez, uç değerlerde çökmez
- Girdi dizisini değiştirmez
- Alpha kanalını korur ve değerlerini bozmaz
- Aynı girdi + aynı seed = aynı sonuç
- **Önizleme ile tam boy aynı karakteri üretir** (yarı çözünürlükte ölçülen fark < 0.02)
- Bilinmeyen/bozuk/NaN parametre şemaya göre temizlenir
- Hiçbir iki işlem aynı sonucu üretmez (adı farklı aynı efekt kabul edilmez)

### Performans: 781 ms → 272 ms

Hedef karşılanmıyordu ve saklanmadı; darboğaz ölçülüp giderildi.
Ayrıntılı tablo `docs/ARCHITECTURE.md` §4'te.

| Senaryo | Ölçülen |
|---|---|
| Basit önizleme (2 katman, 1800 px) | **140 ms** — hedef 150–300 ms ✅ |
| Ağır birleşim (7 katman, 1800 px) | **373 ms** — hedef ~1 s ✅ |
| Sürükleme sırası (7 katman, 1100 px) | **142 ms** ✅ |
| Tam boy (9.2 MP, 7 katman) | **1702 ms** |

En büyük tek kazanç: ton açısı hesabını elle NumPy yerine `cv2.cvtColor`
float32 HSV ile yapmak (150 ms → 1.8 ms, sapma 0.008°).

### Yol boyunca bulunan ve düzeltilen gerçek sorunlar

1. **%100 görünüm gerçek kaliteyi göstermiyordu.** Tuval önizleme
   üzerinde çalıştığı için yakınlaşınca önizleme geriliyordu. Çözüm:
   zoom 1.0'ı aşınca görünen bölge kaynaktan tam çözünürlükte render
   edilip önizlemenin üzerine çiziliyor (96 px kenar payıyla, karo
   sınırı görünmüyor). Doğrulandı: 1183 px karo, önizleme gerilse
   555 px olurdu.
2. **Kaydırıcının boş yolu panel zeminiyle aynı renkteydi** (#131517 vs
   #191C1F) — kullanıcı aralığı göremiyordu. Ayrı `track_empty` jetonu.
3. **Tek parametreli işlemlerde ad iki kez görünüyordu** ("Pozlama"
   başlık + "Pozlama" etiket). Kompakt yerleşim eklendi.
4. **Dar panelde kaydırıcı yolu çok kısalıyordu.** Etiket sütunu artık
   widget genişliğinin oranına göre sınırlanıyor.
5. **`cv2.pow` tek boyutlu diziyi N×N sanıyordu** (Faz 0'dan kalan
   sınıfın yeni kullanımında tekrar ortaya çıkabilirdi) — şekil ve
   süreklilik koruması test edildi.

### Kendi test kurgumda düzelttiğim yanlışlar

- "Sıra sonucu değiştirmeli" testini doygunluk + siyah-beyaz ile
  kurmuştum; bu ikisi **matematiksel olarak yer değiştirebilir** (ikisi
  de rgb↔gri ekseninde doğrusal, parlaklık doğrusal bir işlev). Test
  gerçekten değişmeyen bir çiftle (pozlama + kontrast) yeniden kuruldu
  ve yer değiştirebilirlik ayrı bir testle *belgelendi* ki ileride
  "sıra çalışmıyor" diye yanlış teşhis konmasın.
- Efekt sözleşme testleri lineer alan bildiren işlemlere sRGB verisi
  veriyordu; artık her işleme kendi alanında veri gidiyor.
- Faz 1 testi tuvalin tam boy göstermesini bekliyordu; tuval artık
  (doğru olarak) önizleme gösteriyor. Test zayıflatılmadı,
  *güçlendirildi*: hem `sourceSize` tam boy olmalı hem önizleme aynı
  en-boy oranını korumalı.


---

## Faz 3 ve 4 — tamamlandı (17 Eylül 2026)

Faz 3 (efekt sistemi + presetler) ve Faz 4 (Sinema Laboratuvarı) birlikte
tamamlandı; Faz 6'nın hedefi olan 120 preset de bu turda üretildi.

### Görüntü işlemleri: 38 / 35+ hedef

| Kategori | İşlemler |
|---|---|
| Ton (6) | pozlama · kontrast · gölge-parlak alan · siyah-beyaz nokta · parlaklık · **eğriler** |
| Renk (9) | beyaz dengesi · doygunluk · canlılık · HSL · siyah-beyaz karışım · split toning · **renk derecelendirme** · **kanal karıştırıcı** · **3D LUT** |
| Ayrıntı (3) | **keskinleştirme** · yerel kontrast · **gürültü azaltma** |
| Stil (5) | fade · **duotone** · **bleach bypass** · **cross-process** · **posterize** |
| Bulanıklık (3) | **Gaussian** · **radyal/yönlü** · **tilt-shift** |
| Işık (4) | **bloom** · **halation** · **diffusion** · **anamorfik çizgi** |
| Film (1) | **film tonu** (toe/shoulder) |
| Lens (2) | **vignette** · **kromatik aberasyon** |
| Doku (4) | **film grain** · **toz ve çizik** · **ışık sızıntısı** · **kâğıt dokusu** |
| Geometri (1) | **sinema kadrajı** (bant / gerçek kırpma) |

**Halation ile bloom ölçülerek ayrıldı.** Koyu zeminde tek parlak nokta,
aynı yarıçap ve yoğunlukta:

| Halka | bloom R−B | halation R−B |
|---|---|---|
| 15–30 px | 0.00000 | +0.00818 |
| 30–60 px | 0.00000 | +0.00797 |
| 60–100 px | 0.00000 | +0.00319 |

Bloom tam nötr, halation belirgin sıcak; halation'ın kırmızı kanalı
aynı yarıçapta daha uzağa ulaşır (`channel_spread`).

### 120 hazır görünüm

9 genel kategori × 10 + 30 sinematik. Her preset gerçek bir tariftir:
ortalama 4,3 katman, 36 farklı işlem kullanılıyor.

**Üretim denetimi** (`tools/make_presets.py`) her preseti altı temsili
sahnede çalıştırır: portre, manzara, gece, renk yamaları, gradyan ve
doygun sahne. Kontroller:

- Tarif geçerli, bilinmeyen işlem yok, boş değil
- **En az bir sahnede görünür etki** (ortalama fark ≥ 0.012 ≈ 3/255)
- NaN/Inf yok
- Aşırı kırpma yok (siyahlarda %16, parlaklarda %18 üstü uyarı)
- **Ayırt edilemeyen çift yok** — aynı kategoride 0.012, farklı
  kategoride 0.005 eşiği

### Eğri editörü ve renk çarkı

Önceki turda `ParamKind.COLOR` ve `CURVE` için arayüz kontrolü yoktu;
bu parametreler yalnızca preset üzerinden ayarlanabiliyordu. İkisi de
yazıldı:

- **`CurveEditor`** — monoton kübik (Fritsch-Carlson) interpolasyon:
  kontrol noktaları arasında aşma ve ton tersine dönmesi yapısal olarak
  imkânsız. Arkada histogram, kesikli kimlik köşegeni, tıklayarak nokta
  ekleme, sağ tıkla silme, çift tıkla sıfırlama, klavye erişimi.
- **`MultiCurveEditor`** — RGB/R/G/B kanal seçicili tek editör.
  Dört eğriyi alt alta koymak dikeyde ~800 px yer kaplıyordu.
  Değiştirilmiş kanallar düğmede • ile işaretlenir.
- **`ColorWheel`** — merkez nötr, açı ton, yarıçap doygunluk.
  Çark görseli bir kez üretilip önbelleklenir.

### Preset davranış sözleşmesi (doğrulandı)

| Davranış | Sonuç |
|---|---|
| Küçük resimler kullanıcının **kendi fotoğrafında** üretilir | ✅ 32 önizleme, sabit örnek fotoğraf yok |
| Yalnızca görünür kartlar öncelikli üretilir | ✅ `prefetchVisible`, ekran dışı istekler iptal |
| Aynı presete tekrar tıklama yığını çoğaltmaz | ✅ 4 → 4 katman |
| Başka preset **grubu değiştirir** | ✅ katman grubu mekanizması |
| Elle yapılan ayar preset değişiminde korunur | ✅ grupsuz katmanlar dokunulmaz |
| "Yığına ekle" ayrı ve birikimli | ✅ 5 → 9 katman |
| Hover önizlemesi belgeyi değiştirmez | ✅ tarif ve geçmiş derinliği aynı |
| Genel yoğunluk etkiyi ölçekler | ✅ %40 fark 0.047 < %100 fark 0.066 |
| Arama, favoriler, son kullanılanlar | ✅ |
| Kendi görünümünü kaydet / dışa / içe aktar | ✅ JSON, kod çalıştırmadan doğrulanır |

### Sinema Laboratuvarı

Ayrı çalışma alanı, **aynı belge**: ekran değişince düzenlemeler
kaybolmaz. Yalnızca 30 sinematik görünüm listelenir. Araç grupları:
film tonu · renk (grading + LUT + split toning) · ışık (halation,
bloom, diffusion, anamorfik) · analog doku (grain, toz, sızıntı,
kâğıt) · lens · kadraj.

30 sinematik görünümün tamamı 3840×2400 fotoğrafta tam boy export
edildi (30/30, medyan render 2340 ms).

### 3D LUT

`.cube` okuma, trilineer interpolasyon, yoğunluk ayarı. Kimlik LUT'u
rengi **bit düzeyinde** bozmuyor (ölçülen sapma 0.00000). Sekiz yerleşik
yaratıcı LUT `tools/make_luts.py` ile kod üretiliyor — ticari LUT
paketi kopyası değil.

**Taşınabilir kimlik:** preset ve proje dosyalarına mutlak yol
yazılmaz; `builtin:ad` ve `user:ad` önekleri çalışma anında çözülür.
Mutlak yol kurulum klasörü değişince kırılırdı.

Desteklenmeyen ve **iddia edilmeyen**: log kamera dönüşümleri
(S-Log, V-Log…), ACES, 1D LUT, `.3dl`/`.look`. Böyle bir dosya açıkça
reddedilir.

### Yol boyunca bulunan ve düzeltilen gerçek sorunlar

1. **%100 görünüm kaydırmadan sonra bozuluyordu.** Pan detay karosunu
   temizliyor ama yenisini istemiyordu; `viewChanged` sinyali eklendi.
   Karşılaştırma modlarında karo hiç çizilmiyordu.
2. **Preset önizlemeleri yalnızca `paint()` içinden isteniyordu** —
   çizim olayı gelmeden hiçbir önizleme başlamıyordu. Çizim yan etkisiz
   olmalı; `prefetchVisible()` eklendi.
3. **Presetler birbirine fazla benziyordu.** Gerçek fotoğrafta ölçüm:
   en benzer çift 0.0099 (≈2.5/255, gözle ayırt edilemez) ve bazı
   presetler fotoğrafı neredeyse hiç değiştirmiyordu. 17 preset
   yeniden düzenlendi; minimum etki 0.0097 → 0.0247.
4. **Preset dosyalarına mutlak LUT yolu yazılıyordu** — kurulumdan
   sonra kırılırdı.

### Kendi denetim kurgumda düzelttiğim yanlışlar

- Tek sahnede ölçüm yapıyordum: yeşil odaklı bir preseti yeşil
  içermeyen sahnede "etkisiz" sayıyordu. Doğru ölçü: preset **en az
  bir** sahnede görünür olmalı, iki preset **tüm** sahnelerde ayırt
  edilemiyorsa aynıdır.
- Tek eşikli tekrar kontrolü farklı kategorilerdeki makul benzerlikleri
  hata sayıyordu. İki kademeli hale getirildi.
- Efekt sözleşme testinde "eşik" parametrelerini yukarı itiyordum; bu
  bloom ve halation'ı tamamen etkisiz bırakıp "etki yok" diye yanlış
  başarısızlık üretiyordu.
- Stokastik dokular (grain, toz, kâğıt) yarı çözünürlükte piksel piksel
  eşleşemez. Bu artık `resolution_exact=False` ile **açıkça bildiriliyor**
  ve istatistiksel olarak (standart sapma oranı 0.25–4.0) test ediliyor.

---

## Faz 5 — tamamlandı (17 Eylül 2026)

### Yapılanlar

- **`imaging/masks/mask.py`** — 5 maske türü: fırça/silgi, doğrusal
  gradyan, radyal gradyan, parlaklık aralığı, renk aralığı. Maskeler
  *piksel olarak değil*, **çizim tanımı olarak** saklanır (fırça darbeleri
  nokta listesi, gradyanlar uç noktalar). Bu yüzden çözünürlükten
  bağımsızdır: aynı maske önizlemede ve tam boyda aynı şekli verir.
- **Maske bileşenleri** — bir maske birden fazla bileşenden oluşur;
  "Ekle" birleşim, "Çıkar" fark. "Gökyüzü radyal, ama ağaçlar hariç"
  kurulabiliyor. İlk bileşen çıkarma ise tabandan başlanır (yoksa sonuç
  boş kalırdı).
- **`imaging/geometry.py`** — kırpma, 90° döndürme, yatay/dikey çevirme,
  serbest açıda ufuk düzeltme. Ufuk düzeltmede boş köşeler en büyük iç
  dikdörtgenle kırpılır; kullanıcı siyah üçgen görmez.
- **`ui/widgets/canvas_tools.py`** — tuval üstü etkileşim katmanı:
  kırpma çerçevesi (8 tutamak, üçte bir rehberleri, canlı boyut etiketi),
  fırça imleci (tekerlekle boyut), gradyan tutamakları, kırmızı maske
  örtüsü.
- **`ui/widgets/mask_panel.py`** ve **`ui/widgets/crop_panel.py`** —
  maske listesi/bileşenleri/parametreleri ve en-boy oranı, yönelim,
  ufuk düzeltme kontrolleri.
- **`storage/project.py`** — `.luma` sürümlü ZIP paketi (manifest,
  project.json, preview.jpg, sources/). Atomik yazma (geçici dosya +
  `os.replace`), zip-slip koruması, boyut sınırı.
- **Taşınabilir proje** — kaynak fotoğrafın kopyası pakete gömülür;
  kullanıcıya ek boyut *kaydetmeden önce* bildirilir.
- **Kaynak yeniden bulma** — dosya taşınmışsa proje yanında ve
  Resimler klasöründe SHA-256 ile aranır; bulunamazsa kullanıcıdan
  konum istenir. İçerik değişmişse "değişmiş" uyarısı verilir.
- **Otomatik kurtarma** — 45 saniyede bir, `<ad>-<hash>.autosave.luma`
  olarak **ayrı** dosyaya. Açılışta kullanıcıya sorulur.

### Kırpma sırası neden değiştirildi

Kırpma önceden döndürmeden *önce* uygulanıyordu. Kullanıcı kırpma
çerçevesini ekranda gördüğü kadraja yerleştirir; 90° döndürülmüş bir
fotoğrafta bu sıra çerçeveyi başka yere düşürüyordu. Sıra
**ufuk → çevirme → döndürme → kırpma** yapıldı; `Mask.transformed` de
aynı sırayı izliyor. `Geometry.rotated` artık kırpma dikdörtgenini de
döndürüyor, böylece içerik kadrajı takip ediyor.

### Geometri neden yığının dışında

Kırpma çıktı boyutunu değiştirir. Yığın ortasında boyut değişikliği
maskeleri, %100 detay karosunu ve önizleme/tam boy eşlemesini bozardı.
Geometri kaynağa **bir kez** uygulanır (`Document.geometry_source`,
önbellekli), yığın o kadraj üzerinde çalışır. Ek fayda: önce kırpıp
sonra küçültmek, küçültüp sonra kırpmaktan çok daha fazla ayrıntı bırakır.

### Doğrulanan kabul ölçütleri (`tools/phase5_e2e.py` — 72/72)

| Ölçüt | Sonuç |
|---|---|
| Maskeli + 5 efektli + geometrili proje kapatılıp açılınca aynı sonuç | **birebir aynı** (bit düzeyinde) |
| Kırpma maskeyi kaydırmıyor | 0.06 px sapma |
| Döndürme 90/180/270 maskeyi kaydırmıyor | ≤ 0.07 px |
| Yatay/dikey çevirme | ≤ 0.01 px |
| Kırpma + döndürme birlikte | 0.04 px |
| %100 detay karosu maske ile hizalı | tam render ile fark 0.0000 |
| Kurtarma ayrı dosyaya yazıyor | `.autosave.luma`, normal kayıt değişmedi |
| Bozuk/boş/sahte `.luma` reddediliyor | 3/3, anlaşılır Türkçe mesaj |
| Bir fırça darbesi = bir geri alma adımı | geçmiş 8 → 9 |
| Maske silinince bağlı katmanın bağı kopuyor | doğrulandı |
| Kırpma aracı açıkken tam kadraj gösteriliyor | belgedeki kırpma bozulmuyor |
| Fareyle tutamak sürükleme çerçeveyi değiştiriyor | gerçek `QMouseEvent` ile |

### Yol boyunca bulunan ve düzeltilen gerçek hatalar

1. **`output_size` ile gerçek kırpma bir piksel ayrışıyordu.** `output_size`
   uzunluğu yuvarlıyor, `crop_array` iki kenarı ayrı ayrı yuvarlıyordu
   (0.58 × 120 → 70 dedi, gerçekte 69 çıktı). "Çıktı: X × Y" etiketi
   yalan söyleyecekti. Kenar aritmetiği tek yardımcıda toplandı.
2. **`crop_array` boş dizi üretebiliyordu.** Kırpma başlangıcı görüntü
   kenarına eşitse `max(x0+1, min(w,x1))` işe yaramıyordu. Artık başlangıç
   `extent-1`'e sıkıştırılıyor; kırpma hiçbir girdide boş dizi veremiyor.
3. **Proje açma, fotoğraf zaten açıksa tarifi uygulamıyordu.**
   `_load_current` aynı yolda erken dönüyor, dolayısıyla `_on_photo_loaded`
   hiç çağrılmıyordu. Bu durum ayrıca ele alındı.
4. **`MaskPanel` sinyalini dışarıdan yaymak paneli güncellemiyordu.**
   `selectMask` / `selectComponent` açık API'si eklendi; `EditorView`
   artık panelin özel alanlarına dokunmuyor.

### Kendi test kurgumda düzelttiğim yanlışlar

- Radyal maskede `feather=0`'ın keskin kenar vereceğini varsaymıştım;
  radyal maske tanımı gereği yumuşak geçişli (smoothstep). Ölçütü
  gevşetmek yerine testi maskenin gerçek profiline göre yazdım.
- Kabuk testinde fotoğrafı `session.set_current` ile açmaya çalıştım;
  `add_paths` zaten ilk fotoğrafı seçtiği için bildirim hiç gitmiyordu.
  Uygulamanın gerçek yolu olan `_open_in_editor` kullanıldı.

---

## Faz 7 — tamamlandı (17 Eylül 2026)

### Yapılanlar

- **`services/export.py`** — tam çözünürlüklü render, biçim seçenekleri,
  yeniden boyutlandırma, ad şablonu, üst veri politikası, çakışma
  politikası ve toplu kuyruk. Arayüzsüz çalışır, bu yüzden testlenebilir.
- **`ui/views/export_view.py`** — Dışa Aktar çalışma alanındaki durum
  metni **gerçek panelle değiştirildi**: kapsam seçimi, hedef klasör,
  biçim/kalite/bit derinliği, boyut, ad şablonu ve canlı örnek ad,
  üst veri, tahmini dosya boyutu, kuyruk listesi ve ilerleme çubuğu.
- **Kuyruk** — tek çalışan iş parçacığında sırayla. Paralel çalıştırmak
  büyük fotoğraflarda belleği katlar, diske yazma zaten sıralı olduğu
  için kayda değer hız da kazandırmaz.
- **Hata izolasyonu** — `export_one` hiçbir koşulda yükselmez; hata
  Türkçe metin olarak sonuçta döner. Başarısızlar kuyruk ekranında ⚠ ile
  işaretlenir ve tek düğmeyle yeniden denenir.
- **Kaynağın üzerine yazma engeli** — çıktı yolu kaynak dosyayla aynıysa
  yazma reddedilir ve kullanıcıya nedeni söylenir.
- **Güvenli dosya adı** — Windows'ta yasak karakterler, sondaki
  nokta/boşluk ve ayrılmış cihaz adları (CON, NUL, COM1...) temizlenir.

### Render sırası neden önemli

Dışa aktarma **geometri → ölçekleme → efekt yığını** sırasını izler;
düzenleyicinin önizleme yolunun aynısı. Ölçüldü: tam boy çıktı ile
önizleme arasındaki ortalama fark **0.00014** (≈ 0.04/255), küçültülmüş
çıktıda **0.00000**. "Uzun kenar 2048" istendiğinde kastedilen *çıktı*
fotoğrafın kenarıdır; bu yüzden boyutlandırma kırpmadan sonra uygulanır.

### Doğrulanan kabul ölçütleri (`tools/phase7_e2e.py` — 100/100)

| Ölçüt | Sonuç |
|---|---|
| 20 fotoğraflık kuyrukta 2 bozuk dosya | 18 yazıldı, 2 ayrı raporlandı, kuyruk durmadı |
| Orijinaller korunuyor | 19 dosya SHA-256 ile bit düzeyinde doğrulandı |
| İptal tutarlı | 4/14'te durdu, yarım/geçici dosya yok, yazılanların hepsi açılıyor |
| Çıktı yeniden açılıyor | JPEG/PNG/WebP/TIFF — 18/18 ve tüm biçimler |
| Boyut doğru | 7 boyutlandırma kipinde beklenen değerle birebir |
| Bit derinliği doğru | TIFF 16 bit olarak geri okundu |
| Tam boy = önizleme karakteri | ortalama fark 0.00014 |
| EXIF/GPS kullanıcının seçtiği gibi | 3 politika × 2 kontrol, hepsi doğru |
| Ad çakışması | yeni ad / üzerine yaz / atla — üçü de doğru |
| Kaynağın üzerine yazma | engellendi, kaynak SHA'sı değişmedi |

### Yol boyunca bulunan gerçek hata — JPEG yazma çökmesi

`optimize` veya `progressive` açıkken Pillow kodlanmış görüntünün
tamamını tek tamponda tutar ve tampon boyutunu `genişlik × yükseklik`
olarak tahmin eder. Yüksek entropili görüntülerde gerçek JPEG bu
tahmini aşar ve yazma `broken data stream when writing image file` ile
çöker. Ölçüldü: 1400×900 saf gürültü, kalite 92 → varsayılan tamponla
**başarısız**, `2 × w × h` ile başarılı.

Bu teorik bir sınır değil: uygulama Sinema Laboratuvarı'nda **grain
ekliyor**. Grain'li bir fotoğrafı JPEG olarak dışa aktarmak çökebilirdi.
`saver.py` artık `ImageFile.MAXBLOCK`'u çıktı piksel sayısına göre
geçici olarak yükseltiyor (4 kat pay + 1 MB) ve sonra eski değerine
döndürüyor. Regresyon testleri `tests/test_export.py::TestEncoderBuffer`
içinde: saf gürültü 3 kalite değerinde, EXIF'li gürültü, gerçek grain
efektli render ve MAXBLOCK'un geri yüklenmesi.

Hata Faz 1'den beri koddaydı ama tetiklenmemişti; tek fotoğraf kaydetme
yolu EXIF geçirmiyor ve test fotoğrafları iyi sıkışıyordu.

---

## Faz 8 — tamamlandı (17 Eylül 2026)

### Yapılanlar

- **Türkçe metin denetimi** — arayüzün tamamı tarandı; **347 metinde**
  eksik diyakritik düzeltildi ("Gorunum" → "Görünüm", "Baslangic" →
  "Başlangıç", "sifirla" → "sıfırla"...). `tools/turkish_map.py` sözlüğü
  ve `tools/fix_turkish.py` aracı bunu tekrarlanabilir kıldı.
- **`ui/views/settings_view.py`** — Ayarlar çalışma alanındaki durum
  metni **gerçek panelle değiştirildi**: önizleme kalitesi, önbellek
  sınırı ve temizleme, varsayılan kayıt klasörü, otomatik kurtarma
  aralığı, araç ipuçları, pencere konumu, yüksek kontrast, kısayol
  listesi.
- **`core/settings.py`** — `settings.json` okuma/yazma. Dosya bozuksa
  uygulama **açılmaya devam eder**; bozuk alan varsayılana döner.
  Yazma atomik.
- **`ui/widgets/filmstrip.py`** — düzenleyicinin altında film şeridi
  (Bilinen sorun #9 kapandı). Küçük resimler eşzamansız; yalnızca
  görünen kareler istenir.
- **`ui/widgets/elided_combo.py`** — dar panelde metnini kısaltan açılır
  liste. Qt'nin `QComboBox`'i metni kırpmaz, kutudan taşırır.

### Ayarlar gerçekten etki ediyor

Her seçeneğin gözle görülür bir karşılığı var; ayar ekranı süs değil.
Doğrulandı: önizleme kalitesi → `RenderService.set_preview_long_edge`
(1920 → 2560 ölçüldü), önbellek sınırı → `ThumbnailService.prune_cache`
(512 → 1024 MB), kurtarma aralığı → zamanlayıcı (45 s → 120 s → kapalı),
yüksek kontrast → QSS katmanı, araç ipuçları → metinler saklanıp geri
yükleniyor.

### Doğrulanan kabul ölçütleri (`tools/phase8_audit.py` — 31/31)

| Ölçüt | Sonuç |
|---|---|
| 1280×720 … 2560×1440'ta taşma/kesilme | **0 sorun** (5 boyut × 6 ekran) |
| %100 / %125 / %150 / %200 DPI'da kesilme | **0 sorun** |
| Kısayollar tanımlı ve çakışmasız | 26 kısayol, çakışma yok |
| Ctrl+Z / Ctrl+Y / ← / → / 1 gerçekten çalışıyor | doğrulandı |
| Sekme ile gezilebilir öğe | 90 odaklanabilir öğe |
| Araç ipucu kapsamı | %72 (26/36 etkileşimli öğe) |
| Kapanan belgeler serbest bırakılıyor | 18 belge açıldı, GC sonrası **1** canlı |
| Tepe RAM | 997 MB (sınır 3 GB) |
| Yükleme arayüzü kilitlemiyor | en uzun blok **109 ms** |
| Kaydırıcı sürükleme akıcı | **21 ms/adım** |
| Bırakma sonrası tam kalite duraklaması | 91 ms |
| Ekran geçişi | 104 ms |

### Bu cihazdaki gecikme ölçümleri

i7-13700H / 32 GB / Windows 11 26200 · 8.3 MP kaynak:

| İşlem | Süre |
|---|---|
| Önizleme, 1 efekt, 1920 px | 79 ms |
| Önizleme, 7 efekt, 1920 px | 515 ms |
| Tam boy 8.3 MP, 7 efekt | 2197 ms |
| %100 detay karosu (900×700) | 248 ms |

### Denetimin bulduğu ve düzeltilen gerçek sorunlar

1. **Gezinti şeridi 1894 px istiyordu.** Her öğesi sabit genişlikteydi
   ve hiçbiri küçülemiyordu; 1366 px'lik bir dizüstünde şerit taşıyordu.
   Kademeli sadeleşme eklendi: tam etiket → kısa etiket → markayı gizle
   → geri al/yinele düğmelerini simgeye indir. Hiçbir aşamada sekme
   gizlenmez.
2. **Pencere alt sınırı yalan söylüyordu.** 1100 px ilan ediliyordu ama
   şerit kompakt kipte bile 1256 px istiyor. Ölçülen gerçek değere
   çekildi: **1280×720**.
3. **Sol panel alt sınırı doğal ihtiyacın altındaydı.** `setMinimumWidth(208)`
   doğal alt sınırı eziyor, "Yığına ekle" düğmesinin metni kesiliyordu.
   Panel 288 px'e çekildi ve sayaç kendi satırına alındı.
4. **Fotoğraf açılışı arayüzü 722 ms kilitliyordu.** İki görünüm de
   (Düzenleyici + Sinema) 12 MP diziyi doğrudan tuvale veriyordu;
   float32 → QPixmap dönüşümü her biri için ~370 ms. Artık ilk kare
   1600 px'e küçültülüyor ve **gizli görünüm açılışı erteliyor**.
   Ölçüldü: 722 → **109 ms**.
5. **Kaydırıcı sürüklemede iki kat iş yapılıyordu.** Düzenleyici ve
   Sinema aynı belgeyi dinliyor; görünmeyen olan da tam senkron
   yapıyordu. Görünür olunca `showEvent` tamamlıyor.
6. **Karşılaştırma karesi her sonuçta yeniden üretiliyordu.** Orijinal
   görüntü sürükleme boyunca değişmiyor; dizi kimliği aynıysa mevcut
   QPixmap korunuyor (1920 px'de ~35 ms/kare tasarruf).
7. **Kapanışta önizleme işçisi çöküyordu.** Pencere kapanırken hâlâ
   çalışan `_PreviewTask` yok edilmiş sinyal nesnesine `emit` ediyor ve
   `RuntimeError` yığını basıyordu. Normal kapanış yarışı; sonuç artık
   sessizce bırakılıyor.

### Kendi denetim kurgumda düzelttiğim yanlışlar

- **Kaydırıcı ölçümü yanlış yolu sürüyordu.** `doc.set_param` doğrudan
  çağrılıyordu; gerçek kaydırıcı `EditorView._on_param_changed` çağırır
  ve bu **etkileşimli** (1100 px) render ister. Yanlış yol tam kalite
  render tetikliyor ve 187 ms ölçülüyordu. Gerçek yola çevrilince
  **21 ms** çıktı. Eşik gevşetilmedi; ölçüm düzeltildi.
- **Bellek ölçütü RSS eğilimine bakıyordu.** Python ve OpenCV
  boşalttıkları belleği işletim sistemine hemen geri vermez; aynı
  senaryo iki koşuda +8 ve +209 MB/tur verdi. Gerçek ölçüt nesnelerin
  serbest bırakılmasıdır: açılan her belgeye zayıf referans tutulup GC
  sonrası kaç tanesinin canlı kaldığına bakılıyor (18 açıldı, 1 canlı).
  RSS eğilimi ölçüm olarak raporlanmaya devam ediyor.
- **Kesilme denetimi kısaltan bileşenleri de sorun sayıyordu.**
  `ElidedComboBox` metnini kasıtlı kısaltır; bu taşma değildir.

---

## Faz 9 — tamamlandı (17 Eylül 2026)

### Yapılanlar

- **Inno Setup 6.7.3** resmî GitHub sürümünden indirildi
  (`jrsoftware/issrc` — jrsoftware.org indirme sayfasının gösterdiği
  bağlantı). Authenticode imzası **doğrulandı**: `Valid`, imzalayan
  *Pyrsys B.V.*, veren *Sectigo Public Code Signing CA R36*. Kullanıcı
  profiline kuruldu; **yönetici hakkı gerekmedi**, UAC penceresi çıkmadı.
- **`packaging/LumaAtelier.iss`** — kullanıcı başına kurulum
  (`PrivilegesRequired=lowest`), Türkçe arayüz, masaüstü ve Başlat menüsü
  kısayolları, isteğe bağlı `.luma` dosya ilişkilendirmesi.
- **`tools/build_installer.py`** — sürüm bilgisi → PyInstaller →
  **paketlenmiş exe'yi çalıştırıp doğrulama** → Inno Setup. Bozuk bir
  derleme kurulum paketine giremez.
- **`tools/phase9_e2e.py`** — kurulum, kısayol ve uçtan uca akış denetimi.

### Doğrulanan kabul ölçütleri (`tools/phase9_e2e.py` — 26/26)

| Ölçüt | Sonuç |
|---|---|
| Kurulum dosyası üretildi | `dist/LumaAtelier-Setup-0.1.0.exe`, 67 MB |
| Sessiz kurulum çalışıyor | çıkış kodu 0, **10 saniye** |
| Yönetici hakkı gerekiyor mu | **hayır** — UAC istenmedi |
| Masaüstü kısayolu | `C:\Users\<kullanici>\OneDrive\Desktop\Luma Atelier.lnk` |
| Kısayol kurulu uygulamayı gösteriyor | `...\AppData\Local\Programs\Luma Atelier\LumaAtelier.exe` |
| Başlat menüsü kısayolu | var |
| Kısayoldan açılış → fotoğraf → düzenleme → çizim | **6 saniye**, 1520×940 pencere, 8.5 MP fotoğraf |
| Kurulu sürüm bağımlılık sınaması | `SELF-TEST OK` |
| Sinematik görünüm koleksiyonu | 30 görünüm yüklendi, uygulandı |
| Düzenle → proje kaydet → kapat → yeniden aç | tarif **birebir aynı** |
| Dışa aktarma | 1530×1020, 478 KB |
| Orijinal fotoğraf değişmedi | SHA-256 aynı |
| Uygulama kodunda ağ modülü | **0** içe aktarma (çevrimdışı) |
| Kullanıcı verisi profil içinde | veri/günlük/önbellek — üçü de |
| Kaldırma fotoğraflara dokunuyor mu | **hayır**; ayarlar için ayrıca soruluyor |

### Yol boyunca bulunan gerçek hata — maske konumu kayboluyordu

`Mask.to_dict` yalnızca maskenin *türüne ait* konum alanlarını yazıyordu
(radyal için `center`/`radius`, doğrusal için `start`/`end`). Ama
`transformed()` kırpma/döndürme sonrasında **tüm** konumları yeni
kadraja taşır. Yazılmayan alanlar projeyi açınca varsayılana dönüyor,
kullanıcı maskenin türünü sonradan değiştirdiğinde gradyan eski kadrajın
yerini gösteriyordu. Ayrıca kırpma bir gradyan ucunu kadraj dışına
taşıyabilir (`-0.07` gibi) — bu geçerli bir değerdir ve korunmalıdır.

Artık konum alanları her zaman yazılıyor (altı sayı, ihmal edilebilir).
Beş maske türünün beşi de birebir korunuyor; regresyon testleri
`tests/test_masks_geometry.py::TestMaskRoundTripAfterGeometry` içinde.

Bu hata yalnızca **preset + maske + kırpma** birlikte kullanıldığında
ortaya çıkıyordu; Faz 5 testi elle kurulmuş bir tarif kullandığı için
yakalamamıştı. Faz 9'un uçtan uca akışı gerçek kullanıcı sırasını
izlediği için görünür oldu.

### İkinci gerçek hata — uygulama kendi kurtarma kaydını soruyordu

Otomatik kurtarma 45 saniyede bir yazılıyor. Kullanıcı A fotoğrafını
düzenleyip B'ye geçse ve sonra A'ya dönse, uygulama **kendi yazdığı**
kaydı bulup "Kurtarma kaydı bulundu, geri yüklensin mi?" diye soruyordu
— hiçbir çökme olmadığı hâlde. Kurtarma çökme sonrası içindir.

Faz 3–4 uçtan uca testi bu modal diyalogda kilitlenince ortaya çıktı.
Artık bu oturumda yazılan kayıtlar işaretleniyor ve onlar için
sorulmuyor; temiz kapanışta da siliniyorlar. Testler
`tests/test_recovery.py` içinde (9 test).

Ayrıca testin kendi yalıtımı düzeltildi: `phase34_e2e.py` önceki
koşudan kalan kurtarma kayıtlarını başlangıçta temizliyor. Uygulama
orada doğru davranıyordu; eksik olan test kurgusuydu.

### Çalıştırılmayan test — açıkça belirtilir

**Temiz Windows ortamında kurulum testi YAPILMADI.** Python, Visual
Studio Code ve geliştirme araçları bulunmayan ayrı bir Windows kurulumu
(sanal makine veya ikinci bilgisayar) elimde yok. Kurulum bu geliştirme
makinesinde test edildi; paketlenmiş sürüm kendi Python'unu taşıdığı ve
`--self-test` bağımlılıkların `_internal` klasöründen yüklendiğini
doğruladığı için temiz bir makinede de çalışması beklenir, ancak bu
**beklenti**dir, ölçüm değildir.

**Windows 10'da test EDİLMEDİ.** Kurulum betiği `MinVersion=10.0`
diyor ama yalnızca Windows 11 26200 üzerinde çalıştırıldı.

**Kod imzalama sertifikası satın alınmadı.** Kurulum dosyası imzasız
(`NotSigned`). Windows SmartScreen ilk çalıştırmada "Bilinmeyen yayımcı"
uyarısı gösterebilir; "Daha fazla bilgi" → "Yine de çalıştır" ile geçilir.

### Eski Faz 3 planı (tamamlandı)

Altyapı hazır: kayıt sistemi, tarif, yığın, parametre şeması, otomatik
panel üretimi. Faz 3 bunun üzerine kurulur.

1. **Kalan görüntü işlemleri** (öncelik sırasıyla): RGB/kanal eğrileri,
   üç bölgeli color grading, kanal karıştırıcı, vignette,
   keskinleştirme, gürültü azaltma, Gaussian blur, duotone,
   bleach bypass, cross-process, posterize.
2. **`ui/widgets/curve_editor.py`** — eğri kontrolü (`ParamKind.CURVE`
   için kontrol henüz yok; şu an yalnızca preset üzerinden ayarlanır).
3. **`ui/widgets/color_wheel.py`** — `ParamKind.COLOR` kontrolü.
4. **`storage/presets.py`** — preset JSON şeması, yerleşik + kullanıcı
   presetleri, doğrulama, dışa/içe aktarma.
5. **`ui/views/preset_browser.py`** — kullanıcının *kendi* fotoğrafı
   üzerinde üretilen küçük resimler, yalnızca görünür kartlar öncelikli,
   önbellekli; hover geçici önizleme, tıklama kalıcı; tekrar tıklama
   yığını çoğaltmamalı.
6. **En az 30 preset**, altı kategoriden.
7. **Efekt yığını paneli** — sıralama, aç/kapat, yoğunluk, kaldırma.

Faz 3 kabul ölçütü: her preset gerçek tarif içerir · hover kalıcı
değişiklik yapmaz · tekrar tıklama yığını yanlışlıkla çoğaltmaz ·
arama ve favoriler yeniden açılışta korunur.

### Eski Faz 2 planı (tamamlandı)

Hedef: gerçek, geri alınabilir, tahribatsız düzenleme.

Sırayla:

1. **`imaging/recipe.py`** — tahribatsız tarif (recipe) veri modeli:
   sürümlü, JSON'a serileşebilir, efekt listesi + parametreler.
2. **`imaging/adjustments.py`** — temel ton/renk işlemleri: pozlama,
   kontrast, gölge/parlak alan, beyaz/siyah nokta, beyaz dengesi,
   doygunluk, vibrance. Hepsi tek işlem mantığı (önizleme = tam boy).
3. **`services/render.py`** — worker havuzu, istek iptali, önizleme
   çözünürlüğü yönetimi. Hızlı slider hareketinde eski görev iptal
   edilsin, son istek ekranda kalsın.
4. **`core/history.py`** — undo/redo, en az 50 adım; slider sürüklemesi
   tek adım (`ParameterSlider.editingFinished` buna bağlanacak).
5. **`ui/widgets/histogram.py`** — RGB + luma histogram, kırpma uyarısı.
6. **`imaging/geometry.py`** — kırpma, döndürme, çevirme, ufuk düzeltme;
   oranlar: serbest, 1:1, 4:5, 3:2, 16:9, 2.39:1.
7. **`ui/views/editor_view.py`** — sol araç kategorileri, sağ kontrol
   paneli + histogram, alt film şeridi; paneller daraltılabilir.

Faz 2 kabul ölçütü: bir fotoğraf açılır, ayarlanır, geri alınır, yeniden
uygulanır ve tam boy kaydedilir. Kaynak dosya hash'i değişmez. Ayarlar
hem görünümde hem çıktıda çalışır.

### Eski Faz 1 planı (tamamlandı)

Hedef: gerçek uygulama kabuğu. `app/shell.py` yazılacak ve
`app/main.py` içindeki varsayılan yol ondan geçecek
(şu an `smoke_window` açılıyor — bu bilerek geçici).

Sırayla:

1. **`ui/widgets/parameter_slider.py`** — QPainter tabanlı özel kaydırıcı.
   Gerekçe: QSS kaydırıcısı düzgün çalışmıyor *ve* uygulamanın zaten
   çift tıkla sıfırlama, çift yönlü parametrelerde merkez işareti,
   Shift ile ince ayar, sayısal giriş ve klavye erişimine ihtiyacı var.
2. **`ui/views/start_view.py`** — başlangıç ekranı: fotoğraf/klasör ekle,
   büyük sürükle-bırak alanı, son projeler, ilk kullanımda üç adımlık yardım.
3. **`ui/widgets/image_canvas.py`** — zoom/pan tuvali. Yakınlaştır,
   uzaklaştır, ekrana sığdır, %100, tutup kaydır.
4. **`ui/views/library_view.py`** — küçük resim ızgarası, çoklu seçim,
   arama, sıralama, favoriler; kayıp dosyayı yeniden konumlandırma.
5. **`services/thumbnails.py`** — arka planda küçük resim üretimi + önbellek.
6. **`app/shell.py`** — ana pencere, gezinti, durum çubuğu, boş/yükleniyor/hata
   durumları; sürükle-bırak.

Faz 1 kabul ölçütleri (`docs/ACCEPTANCE.md`'de izleniyor):
farklı boyutlarda JPEG/PNG/WebP/TIFF açılır · dikey EXIF ve saydamlık
doğru görünür · fotoğraflar arasında geçilir · pencere boyutlandırma sorunsuz.

---

## Son kapsam denetimi — 18 Eylül 2026

Gereksinim dosyasının sayısal maddeleri kaynak koddan yeniden
doğrulandı (`tools/scope_audit.py`, 21/21). Denetim **dört gerçek hata**
buldu; hepsi düzeltildi:

1. **Karanlık fotoğraflar siyaha eziliyordu.** `style.bleach_bypass` ve
   `film.tone_curve` düz çarpımla kontrast uyguluyor, gece fotoğrafında
   değerleri sıfırın altına indiriyordu (`Bleach Drama`: piksellerin
   %96.8'i tam siyah, ortalama −0.048). 16 görünüm bozuluyordu. Kod
   tabanının kendi çözümü — `tone.contrast` içindeki tanh yumuşak omuz —
   her iki yere uygulandı.
2. **Yoğunluk %0 etkisiz değildi.** `with_intensity` yalnızca `amount`
   parametreli katmanları ölçekliyordu. Artık `identity_at_defaults`
   olan işlemlerin parametreleri varsayılanlarına taşınıyor; 120/120
   görünümde %0 = etkisiz.
3. **Dokuz görünüm çifti ayırt edilemiyordu** (en yakını 0.0039).
   11 görünüm kendi karakteri verilerek ayrıldı; en yakın çift artık
   0.0137.
4. **İki görünüm görünmez derecede zayıftı** (`Soft Detail`,
   `Warm Clean`); karakterleri korunarak güçlendirildi.

Yeni araçlar: `tools/scope_audit.py`, `tools/verify_project_roundtrip.py`
(iki ayrı süreçte proje kalıcılığı), `tools/verify_installed.py`
(kurulu sürüm güncelliği).

---

## Bilinen sorunlar

| # | Sorun | Etki | Plan |
|---|---|---|---|
| 1 | ~~QSS `QSlider::sub-page` sorunu~~ | **çözüldü** | `ParameterSlider` yazıldı; uygulama artık QSS kaydırıcısı kullanmıyor |
| 2 | ~~Inno Setup 6 kurulu değil~~ | **çözüldü** | 6.7.3 resmî GitHub sürümünden kuruldu (imza doğrulandı), yönetici hakkı gerekmedi |
| 3 | Kod imzalama sertifikası yok | SmartScreen uyarısı | İmzasız olarak dürüstçe raporlanacak |
| 4 | Temiz Windows test ortamı yok | Faz 9 temiz kurulum testi | Yapılamazsa "çalıştırılmadı" olarak işaretlenecek |
| 5 | Windows 10 test edilmedi | — | Destek sözü verilmeyecek |
| 6 | ~~Lineer ışık önbelleği yok~~ | **çözüldü** | Alan gruplaması + kanonik sıra; 6 dönüşüm → 2 |
| 7 | ~~`COLOR` ve `CURVE` kontrolü yok~~ | **çözüldü** | `CurveEditor`, `MultiCurveEditor` ve `ColorWheel` yazıldı |
| 8 | ~~Kırpma/döndürme/ufuk düzeltme aracı yok~~ | **çözüldü** | `Geometry` + `CropPanel` + tuval kırpma çerçevesi |
| 9 | ~~Film şeridi (alt panel) yok~~ | **çözüldü** | `ui/widgets/filmstrip.py`, Görünüm menüsünden açılır (T) |

---

## Kalıcı kurallar (her fazda uyulacak)

- Orijinal fotoğraf dosyaları hiçbir akışta değişmez.
- Motor içinde float32; her efekt adımında 8-bit'e dönülmez.
- Önizleme, %100 görünüm ve tam boy render **aynı** motoru ve parametreleri kullanır.
- Grain/toz/light leak deterministik: seed kaydedilir.
- Çalıştırılmamış test "çalıştırılmadı" diye yazılır, geçmiş gibi gösterilmez.
- Kabul ölçütü karşılanmıyorsa ölçüt gevşetilmez; sorun çözülür veya açıkça bildirilir.
