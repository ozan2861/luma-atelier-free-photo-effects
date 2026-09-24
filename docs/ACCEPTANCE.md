# Kabul Ölçütleri ve Doğrulama Durumu

Bu dosya gereksinim belgesindeki (Bölüm 14) faz kabul ölçütlerini
çalıştırılabilir kontrollere bağlar. Her satır ya **geçti** (kanıt
komutuyla), ya **kaldı**, ya da **çalıştırılmadı** olarak işaretlenir.
"Çalıştırılmadı" bir başarısızlık değildir ama başarı gibi de yazılmaz.

Son güncelleme: 17 Eylül 2026 · Faz 0, 1 ve 2 tamamlandı

## Doğrulama komutları

```bash
# Ortam: proje kökünde
.venv/Scripts/python tools/verify_stack.py      # yığın uyumluluğu
.venv/Scripts/python tools/phase0_e2e.py        # uçtan uca dosya akışı
.venv/Scripts/python -m pytest tests/           # birim + entegrasyon
.venv/Scripts/python tools/widget_gallery.py g.png --dpi 1.5   # görsel denetim
```

---

## Faz 0 — Keşif ve teknik doğrulama ✅

| Ölçüt | Durum | Kanıt |
|---|---|---|
| Ortam, donanım ve proje durumu incelendi | ✅ geçti | `docs/ARCHITECTURE.md` §1, §4 — i7-13700H / 32 GB / Win11 26200 |
| `docs/ARCHITECTURE.md` oluşturuldu | ✅ geçti | dosya mevcut |
| `docs/ACCEPTANCE.md` oluşturuldu | ✅ geçti | bu dosya |
| `PROGRESS.md` oluşturuldu | ✅ geçti | depo kökünde |
| Giriş/çıkış formatları netleşti | ✅ geçti | `docs/FORMAT_SUPPORT.md` |
| Renk hattı netleşti | ✅ geçti | `ARCHITECTURE.md` §3, `tests/test_pixels.py` (31 test) |
| Veri şemaları netleşti | ✅ geçti | `ARCHITECTURE.md` §5 |
| Paketleme yaklaşımı netleşti | ✅ geçti | `packaging/LumaAtelier.spec` |
| Bir Qt penceresi + görüntü motoru denemesi | ✅ geçti | `--capture` ekran görüntüsü |
| **Gerçek dosya açıldı** | ✅ geçti | `phase0_e2e.py`: 3840×2400 JPEG, 104 ms |
| **Bir ayar işlendi** | ✅ geçti | +0.55 stop, ortalama fark 0.1089 |
| **Export edildi** | ✅ geçti | JPEG/PNG/WebP/16-bit TIFF, hepsi geri okunup doğrulandı |
| **Küçük paketlenmiş uygulama çalıştı** | ✅ geçti | `dist/LumaAtelier/LumaAtelier.exe --self-test` → çıkış 0; `--capture` → `docs/phase0-packaged-capture.png` |
| Orijinal dosya korundu | ✅ geçti | SHA-256 değişmedi |

**Ek olarak Faz 0'da tamamlananlar** (sonraki fazların önünü açmak için):
tasarım jeton sistemi, QSS üretici, uygulama ikonu ve kontrol süslemeleri,
günlükleme, test fikstürleri, bileşen galerisi aracı.

---

## Faz 1 — Uygulama kabuğu ve kitaplık ✅

Doğrulama komutu: `.venv/Scripts/python tools/phase1_e2e.py` → **14/14 geçti**.
Ekran görüntüleri: `docs/_captures/faz1-*.png` (gerçek uygulamadan alındı).

| Ölçüt | Durum | Kanıt |
|---|---|---|
| Farklı boyutlarda JPEG açılır | ✅ geçti | 2400×1600 `manzara_buyuk.jpg` |
| Farklı boyutlarda PNG açılır | ✅ geçti | 240×240 `kucuk_kare.png`, 480×480 saydam |
| Farklı boyutlarda WebP açılır | ✅ geçti | 240×240 `renkli.webp` |
| Farklı boyutlarda TIFF açılır | ✅ geçti | 256×256 16-bit `rampa16.tif` |
| Dikey EXIF doğru görünür | ✅ geçti | 900×600 kaynak, Orientation=6 → ekranda 600×900 |
| Saydamlık doğru görünür | ✅ geçti | 4 kanal yüklendi; tuval damalı zemin çiziyor |
| Fotoğraflar arasında geçilir | ✅ geçti | 3 ileri / 3 geri, konum göstergesi doğru |
| Pencere boyutlandırma sorunsuz | ✅ geçti | 1366×768, 1100×680, 1920×1080 — taşma yok |
| Boş / yükleniyor / hata durumları tam | ✅ geçti | boş kitaplık metni, "yukleniyor" kartı, hata kartı |
| Sürükle-bırak çalışır | ✅ geçti | başlangıç ekranı ve ana pencere |
| Bozuk dosya akışı çökertmez | ✅ geçti | 6 eklendi, 1 okunamadı, 1 desteklenmeyen — ayrı raporlandı |
| Küçük resimler arka planda üretilir | ✅ geçti | 6/6 üretildi; UI iş parçacığı bloklanmadı |
| Zoom / pan / %100 / sığdır | ✅ geçti | `tests/test_canvas.py` (31 test) |
| Önce-sonra karşılaştırması | ✅ geçti | sürgülü, yan yana, yalnız orijinal |

## Faz 2 — Çekirdek görüntü motoru ✅

Doğrulama: `tools/phase2_e2e.py` → **17/17**, `tools/phase2_ui.py` → **16/16**.
Ekran görüntüleri: `docs/_captures/faz2-*.png`.

| Ölçüt | Durum | Kanıt |
|---|---|---|
| Fotoğraf açılır | ✅ geçti | 3840×2400 JPEG |
| Ayarlanır | ✅ geçti | 5 ayar; kaynaktan ortalama fark 0.044 |
| Geri alınır | ✅ geçti | tarif önceki duruma döner |
| Yeniden uygulanır | ✅ geçti | yineleme aynı tarifi getirir |
| Tam boy kaydedilir | ✅ geçti | 3840×2400 çıktı, düzenlenmişe fark 0.0022 |
| **Kaynak dosya hash'i değişmez** | ✅ geçti | SHA-256 aynı |
| Ayarlar görünümde ve çıktıda çalışır | ✅ geçti | önizleme↔tam boy farkı 0.00003 |
| En az 50 geri alma adımı | ✅ geçti | 67 adım geri alındı |
| Slider sürüklemesi tek adım üretir | ✅ geçti | 20 hareket → 1 geçmiş adımı |
| Hızlı istekte son sonuç kalır | ✅ geçti | 5 istek → yalnız son jeton kabul edildi |
| Histogram + kırpma uyarısı | ✅ geçti | RGB kanalları, uç kırpma işareti |
| Önce/sonra karşılaştırması | ✅ geçti | sürgülü, yan yana, yalnız orijinal |
| **%100 görünüm gerçek kaliteyi gösterir** | ✅ geçti | 1183 px detay karosu kaynaktan üretildi (önizleme gerilse 555 px olurdu) |
| Geri alma sonrası kaydırıcılar tarifle uyumlu | ✅ geçti | tüm kontroller eşitlendi |
| Tek aracın sıfırlanması | ✅ geçti | yalnız o katman kalkar |
| Tarifi başka fotoğrafa kopyalama | ✅ geçti | Ctrl+Shift+C / V |
| Tarif JSON'a yazılıp geri okunur | ✅ geçti | render birebir aynı |
| Bilinmeyen efekt sessizce silinmez | ✅ geçti | saklanıp geri yazılıyor |

### Ölçülen performans (i7-13700H / 32 GB / Win11 26200)

| Senaryo | Süre | Hedef | Durum |
|---|---|---|---|
| Basit önizleme (2 katman, 1800 px) | **140 ms** | 150–300 ms | ✅ |
| Ağır birleşim (7 katman, 1800 px) | **373 ms** | ~1 s | ✅ |
| Sürükleme sırası (7 katman, 1100 px) | **142 ms** | akıcı | ✅ |
| Tam boy render (9.2 MP, 7 katman) | **1702 ms** | — | ölçüldü |
## Faz 3 — Efekt sistemi ve ilk 30 preset ⬜
## Faz 4 — Sinema Laboratuvarı ⬜
## Faz 5 — Maskeler ve proje kalıcılığı ⬜
## Faz 6 — Koleksiyonu 120'ye tamamlama ⬜
## Faz 7 — Tam kalite export ve toplu işleme ⬜
## Faz 8 — Görsel kalite, erişilebilirlik ve performans ⬜
## Faz 9 — Kurulum ve son teslim ⬜

---

## Kalıcı (her fazda geçerli) ölçütler

| Ölçüt | Durum | Kanıt |
|---|---|---|
| Orijinal fotoğraflar hiçbir akışta değişmez | ✅ geçti | `TestOriginalSafety` |
| Kaynağın üzerine yazmak varsayılan değil | ✅ geçti | `test_save_does_not_overwrite_by_default` |
| Yarım dosya bitmiş gibi görünmez | ✅ geçti | `test_no_partial_file_left_when_encoder_fails` |
| Türkçe/Unicode/boşluklu yollar çalışır | ✅ geçti | `TestUnicodePaths` (5 test) |
| Bozuk dosya tüm işlemi çökertmez | ✅ geçti | `TestFailureHandling` (7 test) |
| PNG'de sahte kalite ayarı yok | ✅ geçti | `test_png_reports_no_quality_control` |
| Telemetri yok | ✅ geçti | kodda ağ çağrısı bulunmuyor; günlük yalnızca yerel |
| 16-bit girişte sessiz 8-bit kaybı yok | ✅ geçti | `test_tiff_16bit_preserves_every_level` + karşıt kanıt testi |

---

## Çalıştırılmamış kontroller

Bunlar henüz **denenmedi**; yapılmış gibi raporlanmayacak.

| Kontrol | Neden | Ne zaman |
|---|---|---|
| Temiz Windows (Python/VS Code yok) kurulum testi | Böyle bir ortam yok | Faz 9 — ortam bulunamazsa açıkça işaretlenecek |
| Windows 10 uyumluluğu | Test makinesi yok | Destek sözü verilmeyecek |
| Inno Setup installer üretimi | Inno Setup kurulu değil | Faz 9 |
| Kod imzalama | Sertifika yok | İmzasız olarak raporlanacak |
| %125 / %150 / %200 DPI görsel denetimi | Faz 1 arayüzü henüz yok | Faz 8 (araç hazır: `widget_gallery.py --dpi`) |
