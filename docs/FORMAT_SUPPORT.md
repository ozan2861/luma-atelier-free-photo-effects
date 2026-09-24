# Format Destek Matrisi

Bu tablo **test edilmiş** davranışı gösterir; tahmin içermez.
Doğrulama: `tests/test_io.py` ve `tools/phase0_e2e.py`.

Son güncelleme: 17 Eylül 2026 · Faz 0

## Giriş (okuma)

| Format | Uzantı | 8-bit | 16-bit | Alpha | EXIF yön | ICC | Durum |
|---|---|:---:|:---:|:---:|:---:|:---:|---|
| JPEG | `.jpg .jpeg .jpe` | ✅ | — | — | ✅ | ✅ | test edildi |
| PNG | `.png` | ✅ | ⚠️ | ✅ | — | ✅ | test edildi |
| WebP | `.webp` | ✅ | — | ✅ | ✅ | ✅ | test edildi |
| TIFF | `.tif .tiff` | ✅ | ✅ | ✅ | ✅ | ⚠️ | test edildi |
| BMP | `.bmp` | ✅ | — | — | — | — | kabul ediliyor, ayrı test yok |

- ⚠️ **16-bit PNG:** Pillow okur; ayrı test yazılmadı, bu yüzden garanti verilmiyor.
- ⚠️ **TIFF ICC:** 16-bit TIFF `tifffile` ile okunur ve bu yolda gömülü profil sRGB varsayılır. 8-bit TIFF Pillow yolundan geçer ve profili dönüştürülür.
- **Kapsam dışı (ilk sürüm):** RAW (CR2/NEF/ARW...), HEIC, AVIF, GIF, PSD. Gereksinim belgesi Bölüm 17'de isteğe bağlı olarak listeli.

### Okuma davranışı

- Her giriş **float32 0..1 RGB/RGBA**'ya çevrilir. 16-bit girişte yolda 8-bit'e düşme yoktur (`test_tiff_16bit_preserves_every_level`).
- EXIF `Orientation` piksellere uygulanır; dikey telefon fotoğrafı yan yatmaz (8 yön etiketinin hepsi test edildi).
- ICC profili varsa sRGB'ye dönüştürülür; yoksa sRGB varsayılır ve bu **kaydedilir** (`assumed_srgb`).
- Kısmen bozuk JPEG'de elde olan gösterilir, dosya tümden reddedilmez.
- Bozuk/boş/desteklenmeyen dosya Türkçe mesajla `ImageLoadError` verir; kitaplık taraması durmaz.

### Güvenlik sınırları

| Sınır | Değer | Neden |
|---|---|---|
| Maksimum piksel sayısı | 400 MP | Decompression-bomb koruması. 200 MP profesyonel dosyalar için fazlasıyla yeterli. |

## Çıkış (yazma)

| Format | Uzantı | Bit derinliği | Alpha | Kalite ayarı | ICC | EXIF |
|---|---|---|:---:|:---:|:---:|:---:|
| JPEG | `.jpg` | 8 | ❌ dolgu rengi ile düzleştirilir | ✅ 1–100 | ✅ | ✅ |
| PNG | `.png` | 8 | ✅ | ❌ *kayıpsız* | ✅ | ❌ |
| WebP | `.webp` | 8 | ✅ | ✅ 1–100 veya kayıpsız | ✅ | ✅ |
| TIFF | `.tif` | 8 veya **16** | ✅ | ❌ *kayıpsız* | ✅ | ❌ |

- **PNG ve TIFF kayıpsızdır**; bu formatlarda kalite kaydırıcısı gösterilmez (sahte kontrol konmaz).
- **JPEG alpha desteklemez.** Saydam alan kullanıcının seçtiği dolgu rengiyle düzleştirilir; sessizce siyaha çevrilmez.
- **16-bit yalnızca TIFF'te.** Diğer formatlarda 16-bit istense de 8-bit yazılır ve sonuç `SaveResult.bit_depth` ile dürüstçe bildirilir.

### Yazma güvenliği

1. Önce aynı klasörde geçici `.part` dosyasına yazılır.
2. Başarılı biterse `os.replace` ile nihai ada taşınır (aynı birimde atomik).
3. Hata veya iptal durumunda geçici dosya silinir — **yarım dosya bitmiş gibi görünmez**.
4. Varsayılan olarak var olan dosyanın üzerine yazılmaz; `ad (2).jpg` üretilir.
5. Kaynak dosyanın üzerine yazmak açık tercih gerektirir.

### Yol ve ad desteği

Test edilmiş: Türkçe karakterler (`ğüşiöçĞÜŞİÖÇ`), boşluklu adlar,
emoji içeren adlar, iç içe Türkçe klasör adları.
