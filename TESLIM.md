# Luma Atelier — Teslim Raporu

**Sürüm 0.1.0 · 17 Eylül 2026**

Windows için çevrimdışı çalışan, Türkçe fotoğraf efekt stüdyosu.

---

## 1. Kurulum dosyası

| | |
|---|---|
| **Konum** | `<proje-klasoru>\dist\LumaAtelier-Setup-0.1.0.exe` |
| **Boyut** | 67 MB (kurulduğunda 260 MB) |
| **Kod imzası** | **YOK** — sertifika satın alınmadı |
| **Yönetici hakkı** | **Gerekmiyor** — kullanıcı profiline kurulur, UAC penceresi çıkmaz |
| **Kurulum süresi** | 10 saniye (ölçüldü) |

Kurulum yeri: `%LOCALAPPDATA%\Programs\Luma Atelier`

### İmzasız olmanın sonucu

Windows SmartScreen ilk çalıştırmada **"Bilinmeyen yayımcı"** uyarısı
gösterebilir. Geçmek için: **"Daha fazla bilgi"** → **"Yine de çalıştır"**.
Bu, kod imzalama sertifikası alınmadığı için beklenen davranıştır;
uygulamada bir sorun olduğu anlamına gelmez.

---

## 2. Masaüstü kısayolu testi

**Sonuç: ÇALIŞIYOR.** Ölçülerek doğrulandı, varsayılmadı.

| Kontrol | Sonuç |
|---|---|
| Kısayol oluştu mu | ✅ `<Masaüstü>\Luma Atelier.lnk` |
| Hedefi doğru mu | ✅ `...\AppData\Local\Programs\Luma Atelier\LumaAtelier.exe` |
| Hedef dosya var mı | ✅ |
| Başlat menüsü kısayolu | ✅ `...\Start Menu\Programs\Luma Atelier.lnk` |
| Kısayoldan açılış | ✅ 6 saniyede 1520×940 pencere |
| Fotoğraf yükleyip çizdi mi | ✅ 8.5 MP JPEG açıldı, düzenleme uygulandı, ekran görüntüsü alındı |
| Bağımlılık sınaması | ✅ `SELF-TEST OK` (PySide6 6.9.1, NumPy 2.2.6, OpenCV 4.11.0, Pillow 12.3.0, tifffile) |

Kaldırma da test edildi: uygulama klasörü ve kısayol silindi,
**`Resimler\Luma Atelier` içindeki kullanıcı dosyası olduğu gibi kaldı.**

---

## 3. Uygulamada neler var

### Görüntü işlemleri — 38 adet (hedef 35+)

Işık (5), eğriler, renk (5), ayrıntı (3), stil (8), lens (2),
bulanıklık (3), sinematik ışık (4), analog doku (4), film tonu,
3D LUT, kadraj.

Hepsi float32 çalışır, önizleme ile tam boy **aynı** motoru kullanır.

### Hazır görünümler — 120 adet

- **90 genel** (9 kategori): portre, manzara, sokak, analog/vintage,
  siyah-beyaz, gece, doğa, mimari, yaratıcı
- **30 sinematik** (Sinema Laboratuvarı)

Her görünüm **kullanıcının kendi fotoğrafı** üzerinde önizlenir,
yoğunluğu %0–100 arası ayarlanabilir.

### Sinema Laboratuvarı

Ayrı çalışma alanı, kendi araç seti (film tonu, halation, bloom,
diffusion, anamorfik, grain, toz, ışık sızıntısı, kağıt dokusu,
letterbox) ve yalnızca 30 sinematik görünüm. Düzenleyiciyle **aynı
belgeyi** paylaşır; ekran değiştirmek düzenlemeleri kaybettirmez.

### Maskeler

5 tür: fırça/silgi, doğrusal gradyan, radyal gradyan, parlaklık aralığı,
renk aralığı. Bir maske birden çok bileşenden oluşabilir ("Ekle" /
"Çıkar"). Maskeler piksel değil **çizim tanımı** olarak saklanır, bu
yüzden çözünürlükten bağımsızdır.

### Kadraj

Kırpma (8 tutamak, üçte bir rehberleri, canlı boyut etiketi), 9 en-boy
oranı, 90° döndürme, yatay/dikey çevirme, serbest açıda ufuk düzeltme.

### Proje kaydetme

`.luma` paketi: efekt yığını, maskeler, kadraj, seed ve küçük önizleme.
Taşınabilir seçeneği fotoğrafın kopyasını da gömer. Fotoğraf taşınmışsa
SHA-256 ile aranır. 45 saniyede bir otomatik kurtarma **ayrı** dosyaya
yazılır; normal kaydın yerine geçmez.

### Dışa aktarma

JPEG / PNG / WebP / 16-bit TIFF, yeniden boyutlandırma (uzun kenar,
genişlik, yükseklik, yüzde), ad şablonu, EXIF/GPS politikası, ICC
gömme, çakışma politikası. Toplu kuyruk: ilerleme, iptal, hata
izolasyonu, başarısızları yeniden deneme.

### Ayarlar

Önizleme kalitesi, önbellek sınırı ve temizleme, varsayılan kayıt
klasörü, otomatik kurtarma aralığı, araç ipuçları, yüksek kontrast,
kısayol listesi. **Her ayarın gözle görülür bir karşılığı var.**

---

## 4. Ölçümler (bu bilgisayarda)

i7-13700H / 32 GB RAM / Windows 11 Pro 26200 · 8.3 MP kaynak

| İşlem | Süre |
|---|---|
| Önizleme, 1 efekt | 79 ms |
| Önizleme, 7 efekt | 515 ms |
| Tam boy 8.3 MP, 7 efekt | 2.2 s |
| %100 detay karosu | 248 ms |
| Kaydırıcı sürükleme | 21 ms/adım |
| Fotoğraf açılışı (12 MP) | 1.0 s, en uzun arayüz bloğu 109 ms |
| Ekran geçişi | 104 ms |
| Tepe RAM (6 fotoğraf × 3 tur) | 997 MB |

Bellek sızıntısı kontrolü: 18 belge açıldı, çöp toplama sonrası
**yalnızca 1 tanesi canlı** (açık olan). Kapanan belgeler serbest
bırakılıyor.

---

## 5. Doğrulama

| Ne | Sonuç |
|---|---|
| Birim ve bütünleşme testleri | **1171 geçiyor** |
| Faz 0 uçtan uca | 5/5 |
| Faz 1 uçtan uca | 14/14 |
| Faz 2 motor + arayüz | 17/17 + 16/16 |
| Faz 3–4 efektler ve sinema | 26/26 |
| Faz 5 maskeler ve proje | 72/72 |
| Faz 7 dışa aktarma | 100/100 |
| Faz 8 görsel kalite/erişilebilirlik/performans | 31/31 |
| Faz 9 kurulum ve uçtan uca akış | 26/26 |

---

---

## 5a. Kapsam doğrulaması (gereksinim → sonuç → kanıt)

Gereksinim dosyasının sayısal maddeleri kaynak koddan ve kurulu
uygulamadan ayrıca doğrulandı. "Kanıt" sütunu çalıştırılabilir aracı
veya dosyayı gösterir.

| # | Gereksinim | Doğrulama sonucu | Kanıt |
|---|---|---|---|
| 1 | En az 90 genel hazır görünüm | ✅ **90** (9 kategori × 10) | `tools/scope_audit.py` §1 |
| 2 | En az 30 sinematik görünüm | ✅ **30** | `tools/scope_audit.py` §1 |
| 3 | Toplam en az 120 görünüm | ✅ **120** | `tools/scope_audit.py` §1 |
| 4 | En az 6 genel kategori | ✅ **9 kategori** | `tools/scope_audit.py` §1 |
| 5 | Kimlikler benzersiz | ✅ 120/120 | `tools/scope_audit.py` §1 |
| 6 | Şemalar geçerli (ad, açıklama, kategori, reçete) | ✅ 120/120 | `tools/scope_audit.py` §1 |
| 7 | En az 35 gerçek görüntü işlemi | ✅ **38 işlem** (preset değil) | `tools/scope_audit.py` §2 |
| 8 | Her işlem görüntüyü gerçekten değiştiriyor | ✅ 38/38 | `tools/scope_audit.py` §2 |
| 9 | Sinema Lab: 30 görünüm seçilebiliyor | ✅ 30/30 görünür etki | `tools/scope_audit.py` §3 |
| 10 | Sinema Lab: yoğunluk ayarlanabiliyor | ✅ %0 < %40 < %100, 30/30 | `tools/scope_audit.py` §3 |
| 11 | Sinema Lab: tam çözünürlükte export | ✅ 30/30, medyan 2634 ms @ 3840×2400 | `tools/phase34_e2e.py` |
| 12 | Aynı reçete farklı isimle tekrarlanmıyor | ✅ 120 ayrı reçete; en yakın çift **0.0137** | `tools/scope_audit.py` §4 |
| 13 | Her görünüm en az bir sahnede görünür | ✅ 120/120 | `tools/scope_audit.py` §4 |
| 14 | Aşırı klipleme yok | ✅ hiçbiri siyahın altına itmiyor; ton ayrımı ≥64 seviye | `tools/scope_audit.py` §5 |
| 15 | Ten renkleri bozuk değil | ✅ 80 görünümde ton 2°–60° | `tools/scope_audit.py` §5 |
| 16 | Portre/manzara/gece görsel inceleme | ✅ 33 karşılaştırma sayfası üretildi ve incelendi | `docs/_captures/kapsam/` |
| 17 | Maskeli + kırpılmış + grain'li proje korunuyor | ✅ **iki ayrı süreçte** fark 0.50/255 (PNG yuvarlaması) | `tools/verify_project_roundtrip.py` |
| 18 | Kurulu sürüm son test edilen kodu içeriyor | ✅ 19 kaynak dosya SHA-256 eşleşti, paket kaynaklardan sonra üretildi | `tools/verify_installed.py` |

### Bu denetimin bulduğu ve düzeltilen gerçek hatalar

1. **Karanlık fotoğraflar siyaha eziliyordu.** `style.bleach_bypass` ve
   `film.tone_curve` kontrastı `0.5 + (x−0.5)·k` ile düz çarpıyordu.
   Gece fotoğrafında bu, değerleri **sıfırın altına** indiriyordu:
   `Bleach Drama` piksellerin **%96.8'ini** tam siyah yapıyor, çıktının
   ortalaması **−0.048** oluyordu. 16 görünüm bu şekilde bozuluyordu.
   Kod tabanının kendi çözümü (`tone.contrast` içindeki tanh yumuşak
   omuz) her iki yere uygulandı. Sonuç: hiçbir görünüm artık siyahın
   altına inmiyor, gece sahnesinde en kötü durumda bile 162 ton
   seviyesi korunuyor. Kanıt: `docs/_captures/kapsam/gece-cinema.jpg`.
2. **Yoğunluk %0 gerçekten "etkisiz" değildi.** `with_intensity`
   yalnızca `amount` parametresi olan katmanları ölçekliyordu; pozlama,
   beyaz dengesi ve HSL katmanları tam güçte kalıyordu. Kullanıcı
   yoğunluğu sıfıra çektiğinde fotoğraf hâlâ değişiyordu. Artık
   `identity_at_defaults` olan işlemlerin parametreleri varsayılanlarına
   doğru taşınıyor. **120/120 görünümde** %0 = etkisiz, 0 < 40 < 100
   tekdüze.
3. **Dokuz görünüm çifti birbirinden ayırt edilemiyordu.** En yakını
   `Golden Hour` / `Golden Skin` (0.0039 — pratikte aynı görünüm).
   11 görünüm sayı değiştirilerek değil, **kendi fikri verilerek**
   ayrıldı: Golden Hour artık *ışık* (hale + bloom), Golden Skin *ten*
   (HSL hedefli), Warm Skin *sıcak-ten/serin-çevre ayrımı*.
4. **İki görünüm görünmez derecede zayıftı.** `Soft Detail` (0.0070) ve
   `Warm Clean` (0.0116) görünürlük eşiğinin altındaydı; karakterleri
   korunarak güçlendirildi.

### Bu denetimde kendi test kurgumda düzelttiğim yanlışlar

- **Parametre seçimi efektleri kapatıyordu.** "Varsayılandan en uzak ucu
  seç" kuralı `amount` gibi şiddet parametrelerini (varsayılan 100 =
  azami) 0'a indiriyor, üç bulanıklık işlemi yanlışlıkla "ölü"
  görünüyordu. Kural düzeltildi: yalnızca azamisi varsayılanının
  üstünde olan parametreler yükseltilir.
- **Eğri, renk ve LUT parametreleri hiç yapılandırılmıyordu.**
  `tone.curves`, `color.grading` ve `color.lut3d` nötr varsayılanlarında
  kalıyor, çalışmıyor gibi görünüyordu. Üçü de gerçek değerlerle
  sınandığında 0.13 / 0.30 / 0.25 değişim üretiyor.
- **Klipleme ölçütü yanlış şeyi ölçüyordu.** Ham "kliplenmiş piksel
  oranı" yüksek kontrastlı bir siyah-beyaz görünümün gece fotoğrafındaki
  *kasıtlı* sertliğini hata sayıyordu. Ölçüt, gerçekten bozulmayı
  gösteren iki şeye çevrildi: ortalamanın negatife düşmesi ve ton
  ayrımının kaybolması. Klipleme oranı ölçüm olarak raporlanmaya devam
  ediyor.

## 6. Kalan gerçek sınırlamalar

Bunlar **çalıştırılmamış testler** ve **bilinen eksikler**. Yapılmış gibi
sunulmuyor.

### Çalıştırılmayan testler

1. **Temiz Windows ortamında kurulum test EDİLMEDİ.** Python ve
   geliştirme araçları bulunmayan ayrı bir makine/sanal makine elimde
   yok. Paketlenmiş sürüm kendi Python'unu taşır ve `--self-test`
   bağımlılıkların `_internal` klasöründen yüklendiğini doğrular; temiz
   makinede çalışması **beklenir** ama ölçülmedi.
2. **Windows 10'da test EDİLMEDİ.** Kurulum `MinVersion=10.0` diyor,
   yalnızca Windows 11 26200'de çalıştırıldı.
3. **Dokunmatik ekran ve yüksek DPI donanımı** üzerinde fiziksel test
   yapılmadı. DPI ölçekleme yazı tipi büyütülerek benzetildi
   (%100/125/150/200), gerçek 4K ekranda denenmedi.
4. **Çok uzun oturum (saatler)** çalıştırılmadı. Bellek 3 turluk
   simülasyonla ölçüldü.

### Bilinen eksikler

5. **Kod imzalama sertifikası yok.** SmartScreen uyarısı çıkabilir
   (Bölüm 1).
6. **RAW dosya desteği yok.** JPEG, PNG, WebP, TIFF, BMP açılır; CR2/NEF/ARW
   gibi kamera ham dosyaları açılmaz.
7. **Geri alma geçmişi belleğe bağlı**, diske yazılmaz. Uygulama
   kapanınca geçmiş kaybolur (tarifin kendisi projede korunur).
8. **Toplu işte her fotoğrafa aynı görünümü uygulama yok.** Toplu
   kuyruk "her fotoğrafı kendi durumuyla yaz" mantığında çalışır; açık
   fotoğrafın tarifi yalnızca ona uygulanır.
9. **Araç ipucu kapsamı %72** (26/36 etkileşimli öğe). Kalan öğeler
   etiketlerinden anlaşılır durumda ama ipuçsuz.
10. **Ekran okuyucu ile test edilmedi.** Erişilebilir adlar tanımlı,
    klavye gezinmesi çalışıyor, ancak NVDA/Narrator ile denenmedi.
11. **En küçük desteklenen pencere 1280×720.** Daha küçük ekranlarda
    gezinti şeridi sığmıyor; pencere bu boyutun altına inemiyor.

---

## 7. Nasıl kullanılır

1. Masaüstündeki **Luma Atelier** simgesine çift tıklayın.
2. **Fotoğraf aç** (Ctrl+O) veya fotoğrafları pencereye sürükleyin.
3. Soldaki görünümlerden birine tıklayın; yoğunluğu ayarlayın.
4. Sağdaki panellerden ince ayar yapın; **Kadraj** ve **Maskeler**
   bölümleri de oradadır.
5. **Sinema Laboratuvarı** sekmesi film estetiği araçlarını açar.
6. **Dışa Aktar** sekmesinden tek fotoğrafı veya kitaplığın tamamını
   yazın.
7. **Ctrl+Shift+S** ile projeyi kaydedin; sonra kaldığınız yerden
   devam edebilirsiniz.

Tam kısayol listesi **Ayarlar** ekranındadır.

---

## 8. Yeniden derleme

```bash
cd "<proje-klasoru>"
.venv\Scripts\python.exe -m pytest                    # 1171 test
.venv\Scripts\python.exe tools\build_installer.py     # kurulum paketi
```

Gereken: Python 3.11 (`.venv` içinde), Inno Setup 6
(`%LOCALAPPDATA%\Programs\Inno\ISCC.exe`).

Faz doğrulamaları: `tools\phase0_e2e.py` … `tools\phase9_e2e.py`,
`tools\phase8_audit.py`.
