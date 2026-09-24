# CLAUDE GELİŞTİRME PROMPTU — LUMA ATELIER

> Kullanım: Bu dosyayı VS Code'da açtığın proje klasörüne koy ve Claude sohbetine ekle. En alttaki başlangıç mesajını gönder. Bu belge uygulamanın geliştirme talimatıdır; uygulama henüz oluşturulmuş değildir.

---

## 1. Rolün ve yapmanı istediğim ürün

Kıdemli bir Windows masaüstü uygulama geliştiricisi, görüntü işleme mühendisi ve ürün tasarımcısı olarak çalış. Benim kişisel bilgisayarımda kullanacağım, premium görünümlü, gerçekten çalışan bir fotoğraf efekt ve düzenleme uygulaması geliştir.

Çalışma adı **Luma Atelier**. İsmi kod içinde kolay değiştirilebilir tut. Arayüz dili Türkçe olsun. Efektlerin yaygın İngilizce adlarını açıklamalarında gösterebilirsin.

Ana kullanımım şu: Masaüstündeki simgeye çift tıklıyorum, uygulama kendi penceresinde açılıyor, fotoğraflarımı sürükleyip bırakıyorum, onlarca farklı görünümü fotoğrafım üzerinde deneyebiliyorum, istediğim görünümü özelleştiriyorum ve kaliteli çıktı alıyorum. Sinema filmlerinin renk ve görüntü estetiğinden esinlenen efektler için özellikle zengin bir bölüm istiyorum.

Premium; özenli tasarım, akıcı kullanım, iyi sonuç veren efektler, güvenilir kayıt ve kurulum demek. Üyelik, abonelik, ödeme sistemi veya efektlerin kilitlenmesi istemiyorum.

Sadece arayüz maketi, statik ekran veya plan teslim etme. Fazlar boyunca uygulamayı gerçekten geliştir, test et ve sonunda kurulabilir Windows uygulamasını oluştur.

## 2. Varsayımlar ve sınırlar

- Öncelikli hedef Windows 11 x64. Windows 10 uyumluluğunu ayrıca doğrulayabiliyorsan raporla; test etmeden destek sözü verme.
- Uygulama tek kullanıcılı, yerel ve kurulduktan sonra çevrimdışı çalışacak.
- Geliştirme sırasında bağımlılık indirmek gerekebilir; kullanıcı fotoğraflarını internete yükleme.
- Fotoğrafların orijinal dosyalarını değiştirme. Düzenlemeleri ayrı proje ve çıktı dosyaları olarak sakla.
- İlk sürüm fotoğraf düzenleme içindir. Video montajı, zamana bağlı film titremesi, kamera hareketi veya video takibi kapsam dışıdır.
- Yapay zekâ, ücretli API, bulut hesabı veya ayrı ekran kartı temel özelliklerin koşulu olmayacak.
- GPU hızlandırma sonraki optimizasyon olabilir; CPU ile çalışan yol bulunmalı.
- Film görünümü simülasyonları sanatsal yorumlardır. Profesyonel film stoklarının birebir bilimsel emülasyonu olduğunu iddia etme.
- Hedef cihazın donanımını başlangıçta oku ve performans hedeflerini buna göre ölç. Donanım tahminlerini gerçekleşmiş sonuç gibi yazma.

## 3. Çalışma biçimin

1. Önce mevcut klasörü incele. Var olan dosyaları ve kullanıcı çalışmalarını koru.
2. Bu belgeyi gereksinim kaynağı kabul et. Rutin kararlar için sürekli onay isteme; makul varsayımlarını kaydet.
3. Gerçekten kullanıcı kararı gerektiren, maliyetli veya geri döndürülemez işlemlerde kısa ve açık soru sor.
4. Her fazda çalışan bir sonuç üret. Tüm özellikleri tek seferde iskelet halinde oluşturup bırakma.
5. Bir fazın kritik kabul ölçütleri sağlanmadan sonraki faza geçme. Başarısız kontrolü düzelt veya gerçek engeli açıkça bildir.
6. Faz sonunda yapılanları, çalıştırılan kontrolleri, kalan eksikleri ve sıradaki adımı kısa anlat. Yetkin ve süren varsa sonraki faza devam et.
7. Oturum sona ererse `PROGRESS.md` dosyasına tamamlanan fazı, son çalışan komutları, bilinen hataları ve tam sonraki adımı yaz.
8. “Tamamlandı”, “hızlı”, “yüksek kaliteli”, “çevrimdışı çalışıyor” gibi iddiaları kanıt olmadan kullanma.
9. Çalışmayan düğme, sahte ilerleme çubuğu, örnek veriyle çalışan ama gerçek dosyada bozulmuş akış veya sadece adı farklı aynı efekt kabul edilmez.
10. Eksikleri gizlemek için kabul ölçütlerini sessizce azaltma. Önce sorunu çöz; çözülemiyorsa açıkça belirt.

## 4. Teknik yaklaşım

Önerilen başlangıç mimarisi:

- Python ve PySide6 / Qt Quick QML: masaüstü uygulaması ve özenli, esnek arayüz.
- NumPy ve OpenCV: gerçek piksel işleme, filtreler ve maskeler.
- Pillow / ImageCms: uygun dosyalarda görüntü okuma, metadata ve ICC dönüşümleri.
- 16-bit TIFF için veri kaybını önleyen uygun bir kütüphane, örneğin tifffile; kullanılan sürümün gerçek yeteneklerini doğrula.
- SQLite: kitaplık, favoriler, son projeler ve uygulama ayarları. Görüntülerin tamamını veritabanına koyma.
- Sürümlenmiş JSON: efekt reçeteleri, presetler, proje verileri ve ayar şemaları.
- PyInstaller onedir veya doğrulanmış eşdeğeri: Python kurmadan çalışacak Windows dağıtımı.
- Inno Setup veya doğrulanmış eşdeğeri: kullanıcı başına kurulum, kaldırma ve kısayollar.

Bu seçim benim zorunlu teknoloji tercihim değil, uygulanabilir başlangıç önerisidir. Mevcut projede güçlü bir mimari varsa koru. Değişiklik gerekiyorsa kullanıcı deneyimi, paketleme ve görüntü kalitesi açısından kısa gerekçe yaz. Birden fazla alternatif uygulama geliştirme.

Bağımlılıkların güncel kararlı ve birlikte çalışan sürümlerini resmî belgelerinden doğrula, sürümleri sabitle. Qt lisans yükümlülüklerini ve üçüncü taraf bildirimlerini paketlemeye dahil et.

Arayüz, görüntü motoru, dosya işlemleri ve proje saklama ayrı modüller olsun. Ağ sunucusu veya tarayıcı açılması günlük kullanımın şartı olmasın. Geliştirme ortamı kapalıyken de uygulama çalışsın.

Başlangıç için şu yapıyı kullanabilir, gerekirse sadeleştirebilirsin:

```text
src/luma_atelier/
  app/
  ui/qml/
  core/
  imaging/effects/
  imaging/color/
  imaging/masks/
  services/
  storage/
resources/
  icons/
  presets/
tests/
packaging/
docs/
README.md
PROGRESS.md
```

## 5. Görsel tasarım ve premium deneyim

Genel karakter: profesyonel fotoğraf stüdyosu, sakin ve rafine. Ana yıldız fotoğraf olsun.

- Koyu grafit zemin, birkaç farklı panel tonu, ince ayırıcılar, kontrollü bakır/kehribar vurgu.
- Okunaklı tipografi, tutarlı boşluklar, kaliteli yerel ikonlar. Lisansı uygun varlıklar kullan.
- Büyük reklam kartları, gereksiz gradyanlar, sürekli animasyonlar ve kalabalık başlangıç ekranı oluşturma.
- Pencere boyutuna uyumlu paneller; 1366×768'de temel işlemler erişilebilir, 1920×1080'de rahat olsun.
- Windows yüzde 100, 125, 150 ve 200 ölçeklendirmelerinde taşma ve bulanıklığı denetle.
- Klavyeyle erişim, görünür odak, yeterli kontrast ve açıklayıcı araç ipuçları sağla.
- Yoğun işlemlerde kısa Türkçe durum mesajları, gerçek ilerleme mümkünse yüzde, değilse dürüst belirsiz ilerleme göstergesi kullan.

### Ekranlar

**Başlangıç:** Fotoğraf ekle, klasör ekle, proje aç, son projeler. Büyük bir sürükle-bırak alanı. İlk kullanımda üç kısa adımlık yardım.

**Kitaplık:** Küçük resimler, çoklu seçim, klasör ve dosya adı arama, favoriler, sıralama. Dosya kaybolursa yeniden konumlandırma.

**Düzenleyici:** Ortada geniş tuval; solda efekt kategorileri ve arama; sağda seçili aracın kontrolleri, histogram ve efekt yığını; altta isteğe bağlı film şeridi. Paneller daraltılabilsin.

**Sinema Laboratuvarı:** Ana gezintide belirgin, ayrı çalışma alanı. Sinematik presetler ve film dokusu kontrolleri burada düzenli biçimde toplansın. Aynı fotoğraf ve proje durumu kullanılsın; ekran değişince düzenlemeler kaybolmasın.

**Dışa Aktarma:** Format, kalite, boyut, hedef klasör, isimlendirme, metadata tercihleri ve kuyruk durumu.

**Ayarlar:** Tema tercihi varsa, önizleme kalitesi, önbellek sınırı, varsayılan kayıt konumu, yerel veri yönetimi, sürüm ve lisanslar.

## 6. Fotoğraf içe aktarma ve düzenleme

- Tekli ve çoklu sürükle-bırak; dosya seçici; klasör içe aktarma. Alt klasör taraması açık bir seçenek olsun.
- JPEG, PNG, WebP ve TIFF temel giriş formatları. Gerçek destek matrisi belgede bulunsun.
- EXIF yönünü doğru uygula; dikey telefon fotoğrafı yanlış dönmesin.
- PNG saydamlığı korunsun. JPEG çıkışında saydam alanın dolgu rengini kullanıcı seçebilsin.
- Bozuk, çok büyük veya desteklenmeyen dosyalar açıkça bildirilsin; kitaplık işleminin tamamı çökmesin.
- Yakınlaştırma, uzaklaştırma, ekrana sığdırma, yüzde 100 görünüm ve tutup kaydırma.
- Orijinal/düzenlenmiş geçişi, sürgülü önce/sonra karşılaştırması ve yan yana görünüm.
- Kırpma, döndürme, yatay/dikey çevirme, ufuk düzeltme; serbest oran, 1:1, 4:5, 3:2, 16:9, 2.39:1.
- Pozlama, kontrast, gölgeler, parlak alanlar, beyaz/siyah noktaları, sıcaklık, tint, saturation, vibrance.
- RGB ve kanal eğrileri; HSL renk aralıkları; gölge/orta ton/parlak alan renk çarkları.
- Temel keskinleştirme, gürültü azaltma ve yerel kontrast.
- En az 50 düzenleme adımı için undo/redo. Slider sürüklemesini yüzlerce ayrı geçmiş adımına dönüştürme.
- Ayarları sıfırlama, tek aracın sıfırlanması, reçeteyi başka fotoğrafa kopyalama.
- Kaydedilmemiş değişiklik göstergesi, otomatik kurtarma kaydı ve proje açma/kaydetme.

## 7. Efekt motoru: gerçek algoritmalar ve düzenlenebilir yığın

En az **35 anlamlı görüntü işlemi** oluştur. Parametreleri ve sonuçları gerçekten farklı olan aşağıdaki kapsamı karşıla:

1. Pozlama; 2. kontrast; 3. gölge/parlak alan; 4. beyaz/siyah nokta; 5. beyaz dengesi; 6. saturation; 7. vibrance; 8. RGB/kanal eğrileri; 9. HSL; 10. üç bölgeli color grading; 11. kanal karıştırıcı; 12. siyah-beyaz renk karışımı; 13. split toning; 14. fade/matte; 15. vignette; 16. keskinleştirme; 17. gürültü azaltma; 18. yerel kontrast; 19. Gaussian blur; 20. radyal/yönlü blur; 21. tilt-shift; 22. bloom; 23. halation; 24. diffusion/soft glow; 25. film grain; 26. light leak; 27. toz/çizik; 28. chromatic aberration; 29. anamorfik ışık çizgisi; 30. duotone; 31. bleach bypass; 32. cross-process; 33. posterize; 34. procedürel kâğıt/doku; 35. 3D LUT uygulama.

Bu liste, 120 bağımsız algoritma varmış gibi pazarlanmasın: görüntü işlemleri motorun araçları, presetler ise bunların düzenlenebilir birleşimleridir.

Her efekt için:

- Sabit kimlik, isim, açıklama, kategori ve doğrulanmış parametre şeması.
- Mantıklı başlangıç değerleri, slider sınırları ve sıfırlama davranışı.
- Aç/kapat, yoğunluk/opaklık ve mümkün olan yerde yerel maske.
- Etkili olduğu renk uzayı, parametre birimleri ve kalite/performance notu.
- Deterministik rastgelelik: grain, toz ve light leak için kayıtlı seed.
- Küçük önizleme ile tam çözünürlükte aynı reçeteyi çalıştıran tek işlem mantığı.

Efektler sıralanabilir bir yığında görünsün. Sıra değişikliği sonucu gerçekten değiştirsin. Bazı işlemlerin zorunlu sırası varsa arayüzde ve veri modelinde açıkça sınırla. Normal karışım zorunlu; Screen, Multiply, Soft Light gibi ek modlar ilgili dokularda uygulanabilir.

## 8. En az 120 hazır görünüm

Hedef **90 genel + 30 sinematik = en az 120 preset**. İlk fazda az sayıyla başla; son sürüme kadar tamamla. Sayıyı renk varyasyonlarıyla şişirme. Her presetin karakteri, amaçlanan fotoğraf türü ve ayarlanabilir reçetesi olsun.

### Genel koleksiyon: 9 kategori × 10 preset

| Kategori | Başlangıç preset adları ve karakterleri |
|---|---|
| Doğal ve temiz | Natural Balance, Clean Daylight, Gentle Contrast, Soft Detail, True Color, Cool Clean, Warm Clean, Airy Whites, Rich Natural, Everyday Polish |
| Portre | Soft Portrait, Warm Skin, Cool Editorial, Matte Portrait, Beauty Glow, Low Key Portrait, High Key Portrait, Golden Skin, Pastel Portrait, Crisp Editorial |
| Manzara | Alpine Clear, Forest Depth, Desert Gold, Ocean Blue, Autumn Copper, Misty Hills, Sunset Drama, Winter Light, Emerald Valley, Earth Tones |
| Sokak ve şehir | Urban Steel, Concrete Mood, Rainy Street, Night Walk, Neon City, Vintage Street, Moody Architecture, Subway Contrast, Urban Fade, Amber Street |
| Analog ve vintage | Faded Print, Warm Negative, Cool Negative, Instant Memory, Retro Summer, Dusty Archive, Sepia Paper, Cross Process, Washed 90s, Grainy Diary |
| Siyah-beyaz | Classic Mono, Fine Art Mono, High Contrast Mono, Soft Silver, Matte Mono, Deep Noir, Infrared Inspired Mono, Grainy Reportage, High Key Mono, Warm Selenium |
| Işık ve atmosfer | Golden Hour, Blue Hour, Soft Bloom, Dream Haze, Window Light, Amber Leak, Cool Mist, Backlight Glow, Sunset Flare, Ethereal Light |
| Yaratıcı renk | Cyan Orange, Purple Dream, Duotone Ink, Crimson Shadows, Mint Pastel, Peach Fade, Electric Blue, Copper Teal, Selective Red, Muted Olive |
| Doku ve stil | Paper Print, Fine Grain, Rough Grain, Dust & Scratches, Soft Focus, Tilt Shift Miniature, Chromatic Fringe, Poster Art, Lo-Fi Print, Frosted Blur |

Portre presetlerini yüz algılama veya cilt rötuşu yapıyor gibi sunma; ilk sürümde bunlar renk/ton/diffusion reçeteleridir. Infrared Inspired gerçek kızılötesi veri üretmez. Selective Red renk aralığı maskesiyle çalışır.

### Preset deneyimi

- Küçük resimleri kullanıcının seçtiği fotoğraf üzerinde oluştur; sabit örnek fotoğraf gösterme.
- Sadece görünür kartları öncelikli üret, sonuçları önbellekle.
- Kart hover/odak önizlemesi geçici olsun, projeyi değiştirmesin.
- Tıklama sonucu tutarlı olsun: mevcut seçili preset grubunu değiştir; ayrıca “Yığına ekle” seçeneği sun. Tekrar tıklama yanlışlıkla etkileri katlamasın.
- Genel yoğunluk ayarı, favori, arama, kategori, son kullanılanlar.
- “Bu görünüm nasıl oluşuyor?” alanında kullanılan efektleri göster.
- Kullanıcı kendi görünümünü adlandırıp kaydedebilsin, JSON olarak dışa/içe aktarabilsin. İçe aktarılan veri doğrulansın; kod çalıştırılmasın.
- Preset kaydı; kimlik, sürüm, kategori, etiketler, Türkçe açıklama, işlem sırası, parametreler, seed ve yoğunluk bilgisini içersin.

## 9. Sinema Laboratuvarı

Bu bölüm ürünün ayırt edici özelliği olsun. Film estetiği sadece bir LUT ya da siyah şerit olarak uygulanmasın; renk, kontrast, parlak alan geçişi ve doku birlikte düzenlenebilsin.

### 30 sinematik görünüm

1. Teal & Amber — soğuk gölgeler, sıcak parlak alanlar.
2. Soft Blockbuster — kontrollü kontrast ve yumuşak renk ayrımı.
3. Desert Epic — kum, altın ve bakır tonları.
4. Neon Rain — mavi/magenta gece atmosferi.
5. Emerald Thriller — yeşil gölgeler ve gerilim hissi.
6. Steel Thriller — çelik mavisi, az doygunluk.
7. Classic Noir — güçlü siyah-beyaz ayrımı.
8. Silver Screen — yumuşak klasik siyah-beyaz.
9. Bleach Drama — düşük doygunluk, güçlü kontrast.
10. Golden Memory — sıcak, nostaljik ve yumuşak.
11. Pastel Cinema — hafif kontrast, pastel palet.
12. Winter Drama — soğuk, açık ve sakin tonlar.
13. Nordic Mystery — soluk renkler, serin gölgeler.
14. Vintage Western — toprak ve sıcak tozlu tonlar.
15. Night Tungsten — sıcak ışıklar, serin çevre.
16. Moonlit Blue — mavi gece yorumu; gerçek yeniden aydınlatma iddiası yok.
17. Urban Crime — kirli yeşil, amber ve sıkı kontrast.
18. Indie Matte — kalkık siyahlar, düşük doygunluk.
19. Festival Natural — ölçülü renk ve doğal tenler.
20. Dream Sequence — diffusion ve bloom.
21. Romantic Diffusion — yumuşak ışık, sıcak tenler.
22. Bronze Action — bronz parlak alanlar ve koyu gölgeler.
23. Ocean Suspense — cyan/mavi ağırlıklı gerilim.
24. Crimson Night — kırmızı ışık vurgulu koyu atmosfer.
25. Olive War Drama — mat zeytin ve toprak renkleri.
26. Retro Sci-Fi — cyan/amber renk ayrımı ve analog doku.
27. 16mm Diary — belirgin grain ve yumuşak ayrıntı.
28. 35mm Warm Print — sıcak baskı benzeri ton geçişi.
29. 35mm Cool Print — serin baskı benzeri ton geçişi.
30. Monochrome Documentary — doğal kontrastlı, grenli belgesel görünümü.

Adlar yaratıcı yönü tarif eder. Ticari LUT paketlerini, tescilli preset dosyalarını, film afişlerini veya başka uygulamanın arayüzünü kopyalama. Marka/film stoku adı altında doğrulanmamış birebir emülasyon sunma.

### Ayrı kontrol grupları

- **Renk:** Lift/Gamma/Gain veya anlaşılır gölge/orta ton/parlak alan çarkları; balance ve blend.
- **Film tonu:** Kontrast pivotu, toe/shoulder benzeri eğri kontrolü, highlight roll-off ve film fade.
- **Grain:** Miktar, boyut, renkli/monokrom ve tonlara göre dağılım. Yalnızca sabit beyaz gürültü bindirme yaklaşımıyla yetinme.
- **Halation:** Parlak kaynakların çevresindeki sıcak saçılma. Eşik, yarıçap, yoğunluk ve renk kontrolü; bloom'dan farklı bir sonuç üretmeli.
- **Bloom:** Parlak alanların yumuşak ışık yayılımı; eşik, yarıçap, yoğunluk.
- **Diffusion:** Kontrastı ve parlaklık yayılımını kontrollü etkileyen mist benzeri görünüm.
- **Lens:** Vignette, chromatic aberration ve ışık kaynağına bağlı anamorfik çizgi. Gerekirse çizginin merkezini kullanıcı seçebilsin.
- **Analog doku:** Light leak, toz, çizik, doku yoğunluğu; renkleri ve seed değiştirilebilir olsun.
- **Kadraj:** 1.85:1 ve 2.39:1 rehberleri. Rehber, gerçekten kırpma ve görüntüye siyah bant ekleme farklı açık seçenekler olsun. Önizleme rehberi dışa aktarmaya yanlışlıkla işlenmesin.
- **LUT:** `.cube` içe aktarma, yoğunluk ayarı, desteklenen boyutlar ve hata kontrolü. Başlangıçta SDR/sRGB uyumlu yaratıcı 3D LUT'ları destekle. Log kamera dönüşümü veya ACES desteğini doğrulamadan sunma.

Varsayılanlar ölçülü olsun; yüzler turunculaşmasın, siyahlar her presette ezilmesin, parlaklıklar gereksiz kliplenmesin. Basit ten rengi aralığı koruması eklersen bunun maske tabanlı bir yardımcı olduğunu açıkça belirt.

## 10. Yerel maskeler ve kalite

- Fırça/silgi, doğrusal gradyan, radyal gradyan, parlaklık aralığı ve renk aralığı maskeleri.
- Feather, tersine çevirme, maske görünümü, ekleme ve çıkarma.
- Maske koordinatları fotoğraf uzayında tutulsun; zoom/pan veya önizleme boyutu maskeyi kaydırmasın.
- Kırpma/döndürme sonrası maskeler doğru dönüşümü izlesin.
- Maskeleri projede kaydet ve yeniden açınca aynı sonucu üret.
- İlk sürümde otomatik özne seçimi zorunlu değil. Manuel maskeleri göstermelik bırakma.

Renk yönetimi ve render koşulları:

- Fotoğrafı uygun giriş profiliyle yorumla. ICC profili olmayan RGB dosyada sRGB varsayımını kaydet.
- Motor içinde float32 gibi yeterli hassasiyet kullan; her efekt adımında 8-bit'e dönüp bantlaşma üretme.
- Başlangıç çalışma hedefi SDR/sRGB olsun. Lineer ışık gerektiren işlemlerde doğru dönüşüm yap; sanatsal ton işlemlerinin uzayını ayrıca tanımla.
- 16-bit giriş desteği varsa okuma zincirinde sessiz 8-bit kayıp olmasın; test et.
- Önizleme ekran profilini uygun şekilde ele alsın; bilinçli olarak desteklenmeyen HDR/CMYK girdilerine anlaşılır yanıt ver.
- Alpha ve premultiplied-alpha dönüşümlerinde kenar halelerini test et.
- Önizleme, yüzde 100 kontrolü ve tam boy render aynı motor ve parametreleri kullansın.
- Blur/halation yarıçapı ile grain boyutunu tutarlı görüntü koordinatlarında tanımla. Önizleme farklı çözünürlükte diye efekt karakteri tamamen değişmesin.
- Küçük önizleme, özellikle grain için tam boy detayın yaklaşık temsili olabilir; yüzde 100 görünüm gerçek kaliteyi gösterebilsin.
- Büyük fotoğraflarda tile/chunk gerekiyorsa filtre çevre paylarını koru; karo sınırları görünmesin. Global istatistik gerektiren işlemleri ayrı analiz et.

## 11. Performans ve güvenilirlik

- Görüntü hesaplarını UI iş parçacığında yapma. Uygun worker ve görev kuyruğu kur; Python/GIL etkisini ölçerek süreç veya thread seç.
- Hızlı slider hareketlerinde eski görevler iptal edilsin ya da sonuçları geçersiz sayılsın. Son istek ekranda kalmalı.
- Önizleme için yaklaşık 1600–2048 piksel uzun kenar ve gerektiğinde daha düşük etkileşim kalitesi kullan; fare bırakılınca kaliteyi yükselt.
- Önizleme tamponlarının yaşam süresini güvenli yönet; boşalan NumPy belleğini kullanan QImage üretme.
- Sınırlandırılmış RAM ve disk önbelleği; tüm presetleri ve tüm fotoğrafları tam boy belleğe alma.
- 24 MP fotoğraf açma, basit ayar yanıtı, ağır sinematik render ve toplu export için ölçüm kaydet.
- Başlangıç hedefi: 16 GB RAM'li güncel bir bilgisayarda basit önizlemeler yaklaşık 150–300 ms, ağır birleşimler yaklaşık 1 saniye civarında. Bunlar hedef; cihazda ölçmeden garanti verme.
- Hedef karşılanmıyorsa darboğazı ölç, çözünürlük/önbellek/algoritma yaklaşımını iyileştir, gerçek sonucu yaz.
- Export sırasında UI kullanılabilsin; kuyruk iptal edilebilsin.
- Fotoğraf verisini veya kişisel dosya yollarını dışarı gönderen telemetri olmasın.
- Hataları yerel log'a yaz; kullanıcıya log klasörünü açma olanağı ver.
- Otomatik kurtarma yazıları atomik olsun; kesinti eski sağlam kaydı bozmamalı.

## 12. Proje, preset ve dışa aktarma

Proje dosyası `.luma` uzantılı sürümlenmiş bir paket olabilir. Manifest, kaynak bağlantıları, efekt yığını, maskeler, seed, uygulama sürümü ve küçük önizleme içersin.

- Normal kayıt orijinale referans verebilir. Kaynak taşınırsa kullanıcıdan yeni konum seçmesini iste.
- “Taşınabilir proje olarak kaydet” kaynak fotoğrafların kopyalarını da içerebilsin; kapladığı alanı belirt.
- Projeyi açıp yeniden kaydetmek görüntüde ek kalite kaybı yaratmasın; tariften yeniden render et.
- Sürüm uyuşmazlıklarını ele al; bilinmeyen efektleri sessizce silme.

Dışa aktarmada:

- JPEG, PNG ve WebP zorunlu; doğrulanmış 16-bit TIFF çıktısı son sürüm hedefi.
- Orijinal çözünürlük, uzun kenar veya özel boyut. En-boy oranını koruma seçeneği.
- JPEG/WebP kalite ayarı; PNG'ye sahte kayıplı kalite slider'ı koyma.
- Dosya adında önek/sonek ve sıra numarası; çakışmada güvenli yeni ad veya açık karar.
- Kaynağın üzerine yazmayı varsayılan yapma; sıfır orijinal kaybı hedefle.
- Metadata koruma/kaldırma seçeneği, GPS için ayrı tercih. Yeniden boyutlandırma sonrası eski EXIF yönü ve boyut bilgilerini düzelt.
- Çıktıya doğru ICC profili yaz; formatın desteklemediği metadata için dürüst davran.
- Toplu uygulama ve export kuyruğu: başarı, hata, iptal ve tekrar deneme durumları.
- Geçici dosyaya yazıp başarılı bitişte nihai ada taşı; iptal edilen export yarım dosyayı bitmiş gibi göstermesin.
- Dışa aktarılan dosyayı tekrar açıp boyut, renk, efekt ve saydamlık açısından doğrula.

## 13. Windows kurulum ve masaüstü kısayolu

Bu özellik projenin tamamlanma şartıdır.

- Uygulama gerçek `.exe` ile açılmalı; Python, VS Code, terminal veya geliştirme sunucusunu elle başlatmam gerekmemeli.
- Dağıtımı kullanıcı başına kuracak bir `LumaAtelier-Setup.exe` oluştur.
- Varsayılan kurulum konumu uygun kullanıcı uygulama klasörü olsun; kullanıcı verilerini kurulum klasörüne yazma.
- Başlat menüsü girişi ve varsayılan seçili “Masaüstü kısayolu oluştur” seçeneği ekle.
- Windows Known Folder mekanizmasını kullan; masaüstü yolu OneDrive'a taşınmış veya Türkçe olabilir. Yolu sabit `Desktop` varsayımıyla oluşturma.
- Kısayolun `.ico` simgesi, hedefi ve çalışma klasörü doğru olsun.
- Kurulum sonunda uygulamayı aç seçeneği bulunsun. Normal açılışta arka planda siyah terminal penceresi görünmesin.
- Uygulama verileri, cache ve log için Windows'un uygun kullanıcı veri konumlarını kullan.
- Güncelleme/yeniden kurma ayarları ve presetleri korusun. Kaldırma kişisel fotoğrafları silmesin.
- Installer oluşturulduğunu gerçekten dosyayla doğrula; geliştirici betiği veya `.bat` kısayolu son teslimin yerine geçmez.
- İmza sertifikası yoksa imzalıymış gibi sunma. Antivirüs/SmartScreen'i kapatmayı önerme; imza durumunu kısa raporla.

## 14. Fazlara ayrılmış geliştirme planı

### Faz 0 — Keşif ve teknik doğrulama

Ortamı, donanımı, proje durumunu ve kurulum araçlarını incele. `docs/ARCHITECTURE.md`, `docs/ACCEPTANCE.md` ve `PROGRESS.md` oluştur. Giriş/çıkış formatlarını, renk hattını, veri şemalarını ve paketleme yaklaşımını netleştir. Bir QML penceresi ve küçük görüntü motoru denemesiyle seçilen bileşenlerin uyumunu doğrula.

**Kabul:** Gerçek dosyanın açıldığı, bir ayarın işlendiği, export edildiği ve küçük paketlenmiş uygulamanın çalıştığı uçtan uca teknik deneme. Paketleme riskini projenin sonuna bırakma.

### Faz 1 — Uygulama kabuğu ve kitaplık

Premium tasarım sistemini, ana pencereyi, sürükle-bırak akışını, dosya seçiciyi, çoklu fotoğraf kitaplığını ve zoom/pan tuvalini geliştir. Boş, yükleniyor ve hata durumlarını tamamla.

**Kabul:** Farklı boyutlarda JPEG/PNG/WebP/TIFF açılır; dikey EXIF ve saydamlık doğru görünür; fotoğraflar arasında geçilir; pencere boyutlandırma sorunsuzdur.

### Faz 2 — Çekirdek görüntü motoru

Temel ton/renk ayarları, histogram, kırpma/döndürme, non-destructive tarif, worker sistemi, undo/redo ve önce/sonra karşılaştırmasını geliştir. İlk güvenilir JPEG/PNG export'u ekle.

**Kabul:** Bir fotoğraf açılır, ayarlanır, geri alınır, yeniden uygulanır ve tam boy kaydedilir. Kaynak dosya hash'i değişmez. Ayarlar görünümde ve çıktıda çalışır.

### Faz 3 — Efekt sistemi ve ilk 30 preset

Efekt kayıt sistemi, yığın, yoğunluk, sıralama, favori, arama ve fotoğrafa özgü küçük resimleri oluştur. En az altı kategoriden toplam 30 özenli preset ekle.

**Kabul:** Her preset gerçek tarif içerir; hover kalıcı değişiklik yapmaz; tekrar tıklama yığını yanlışlıkla çoğaltmaz; arama ve favoriler yeniden açılışta korunur.

### Faz 4 — Sinema Laboratuvarı

Halation, bloom, diffusion, grain, film tonu, LUT, lens ve kadraj araçlarını geliştir. Ayrı çalışma alanını ve 30 sinematik görünümü tamamla.

**Kabul:** Araçlar bağımsız ayarlanır; halation ve bloom ayırt edilir; seed ile çıktı tekrarlanır; kimlik LUT'u rengi bozmaz; tüm sinematik presetler gerçek fotoğrafta export edilir.

### Faz 5 — Maskeler ve proje kalıcılığı

Manuel/parametrik maskeleri, proje kaydet/aç, kaynak yeniden bulma, taşınabilir proje, özel preset kaydı ve otomatik kurtarmayı tamamla.

**Kabul:** Maskeli ve çok efektli proje kapatılıp açıldığında aynı sonucu verir. Zoom/kırpma/döndürme maskeyi yanlış konuma taşımaz. Kurtarma, normal kaydın yerine sessizce geçmez.

### Faz 6 — Koleksiyonu 120'ye tamamlama

Genel koleksiyonu 90 presete çıkar; 30 sinematik ile toplam en az 120 olsun. Portre, doğa, şehir, gece ve saydam örneklerde kalite denetimi yap. Benzer reçeteleri gözden geçir ve gereksiz tekrarları düzelt.

**Kabul:** Kimlikler benzersizdir, şemalar geçerlidir, tüm presetler batch smoke testinden geçer. Temsilî fotoğraflarda karşılaştırma sayfaları hazırlanır ve gözle incelenir. Sayı kontrolü görsel çeşitlilik kanıtının yerine geçmez.

### Faz 7 — Tam kalite export ve toplu işleme

Format seçenekleri, 16-bit TIFF, renk profili, metadata, batch kuyruğu, iptal, hata izolasyonu ve isimlendirmeyi tamamla. Büyük fotoğraf bellek kullanımını ölç.

**Kabul:** 20 fotoğraflık kuyrukta bir bozuk dosya diğerlerinin sonucunu engellemez; iptal tutarlıdır; çıktı yeniden açılır; boyut ve bit derinliği doğrudur; orijinaller korunur.

### Faz 8 — Görsel kalite, erişilebilirlik ve performans

Arayüzü farklı çözünürlük/DPI değerlerinde incele. Kesilen metinleri, odak sorunlarını, panel taşmalarını ve yavaş işlemleri düzelt. Bir çalışma oturumunda dosya açma, düzenleme, preset değiştirme ve export akışını tekrar et; bellek eğilimini izle.

**Kabul:** Ana akışta taşma veya kilitlenme yok; klavye işlemleri çalışır; gerçek cihaz üzerinde gecikme ve RAM ölçümleri raporlanır. Performans sorunu varsa saklanmaz.

### Faz 9 — Kurulum ve son teslim

Son Windows paketini ve installer'ı oluştur. Masaüstü ve Başlat menüsü kısayollarını doğrula. Mümkünse Python/VS Code bulunmayan temiz bir Windows ortamında dene. Ortam yoksa çalıştırmadığın testi açıkça işaretle; temiz kurulum testi yapılmış gibi yazma.

**Kabul:** Kurulum → masaüstü simgesi → uygulama → fotoğraf ekleme → sinematik preset → ayar → export → kapatma → yeniden açma akışı doğrulanır. Temel kullanım internet olmadan çalışır. Kaldırma kullanıcı fotoğraflarını silmez.

## 15. Test stratejisi

Testleri yalnızca sayısal kapsama için yazma; görüntü kalitesi, veri kaybı ve kullanıcı akışındaki riskleri hedefle.

- Identity/zero intensity: Nötr ayarlar ve yüzde 0 yoğunluk orijinali tolerans içinde korur.
- Renk testleri: Gradyan, gri rampa, renk yamaları; NaN/Inf, klipleme ve bantlaşma kontrolleri.
- LUT testleri: Identity LUT, bilinen kanal dönüşümü, domain/size kontrolü, bozuk dosya.
- Seed testleri: Aynı seed ve tarif aynı çözünürlükte aynı sonucu verir.
- Alpha/EXIF/ICC testleri: Saydam kenar, döndürülmüş telefon fotoğrafı ve gömülü profil.
- 16-bit testi: Yalnızca dosya etiketi 16-bit olmasın; piksellerin ton hassasiyeti de korunsun.
- Render tutarlılığı: Tam boy çıktıdan küçültülen görüntü ile önizleme karşılaştırılır. Kabul toleransları ve grain gibi çözünürlüğe bağlı istisnalar belgelenir.
- Maske testleri: Feather, inversion, crop/rotate ve proje açma sonrası koordinatlar.
- Kalıcılık testleri: Proje sürümleme, eksik kaynak, bozuk kayıt ve kurtarma.
- Export testleri: İptal, ad çakışması, yazma izni hatası, disk doluluğu, yarım dosya temizliği.
- Windows testleri: Türkçe karakterli/boşluklu yollar, Unicode dosya adı, taşınmış masaüstü, kurulum klasörüne yazma yetkisi olmaması.
- Entegrasyon testi: Import → preset → maske → proje kaydı → yeniden aç → export.
- Görsel denetim: Yalnızca sayısal testlerle yetinme; portre, manzara, gece, mimari ve gradyanlarda gerçek çıktıları incele. Kendi oluşturduğun veya kullanım hakkı açık örnekler kullan.

Rapor; çalıştırılan testleri, sonuçlarını ve çalıştırılamayan kontrolleri ayırsın. Ekran görüntüsü veya test sonucu uydurma.

## 16. Son teslimde beklediklerim

1. Çalışan kaynak kod ve sabitlenmiş bağımlılıklar.
2. Windows kurulum dosyası ve varsa taşınabilir paket.
3. Çalıştığı doğrulanmış masaüstü kısayolu.
4. En az 120 preset, en az 35 gerçek görüntü işlemi ve ayrı Sinema Laboratuvarı.
5. Orijinalleri koruyan proje ve export akışı.
6. Türkçe kısa kullanım kılavuzu: kurulum, fotoğraf açma, efekt, sinema bölümü, proje kaydı ve çıktı alma.
7. `README.md`: geliştirme, test ve paketleme adımları.
8. `docs/TEST_REPORT.md`: testler, gerçek ölçümler, kullanılan test ortamı ve bilinen sınırlamalar.
9. `docs/PRESET_CATALOG.md`: kategori, preset, kısa açıklama ve ilgili efektler.
10. Üçüncü taraf lisans bildirimleri ve kaynak referansları.

Son mesajında kurulumu nereden açacağımı, masaüstü kısayolunun durumunu ve varsa gerçek eksikleri basit Türkçeyle anlat. Geliştirici komutlarını günlük kullanım için bana mecbur bırakma.

## 17. İlk sürümden sonraki isteğe bağlı özellikler

Zorunlu fazlar tamamlanmadan bunlara girme: RAW geliştirme, HEIC/AVIF, otomatik özne maskesi, yerel AI gürültü azaltma, gelişmiş perspektif düzeltme, referans fotoğraftan renk eşleme, LUT dışa aktarma, GPU hızlandırma ve eklenti sistemi. Bunların hiçbiri temel uygulamayı eksik bırakmanın bahanesi olmasın.

## 18. Araştırma referansları

Aşağıdaki ürünler kapsam için ilham kaynağıdır; onların kapalı algoritmalarını birebir uyguladığımızı iddia etme. Bu belgedeki sayılar, mimari ve fazlar benim uygulamam için tasarım hedefleridir, kaynak ürünlerin özellik sayıları değildir.

- [Adobe Lightroom Classic — ton ve renk düzenleme](https://helpx.adobe.com/gr_en/lightroom-classic/help/image-tone-color.html): ton ayarları, renk çarkları ve gölge/orta ton/parlak alan ayrımı.
- [Blackmagic Design DaVinci Resolve — Photo](https://www.blackmagicdesign.com/uk/products/davinciresolve/photo): fotoğraf renk işleme ve Film Look Creator içindeki halation, bloom, grain ve vignette yaklaşımı.
- [DaVinci Resolve 19 — resmî yeni özellikler kılavuzu](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_19_New_Features_Guide.pdf): film görünümünün renk ve fiziksel doku bileşenlerini birlikte ele alma yaklaşımı. Eski sürüm referansıdır; güncel sürüm bilgisi olarak kullanılmasın.
- [DxO Nik Color Efex](https://www.dxo.com/en/nik-collection/nik-color-efex/): yaratıcı renk filtrelerinin keşfi ve birleşimleri.
- [DxO Nik Analog Efex](https://www.dxo.com/en/nik-collection/nik-analog-efex/): analog görünüm, renk kayması ve doku çeşitliliği.
- [Qt for Python — PyInstaller dağıtımı](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html): önerilen Windows paketleme yaklaşımı için teknik başlangıç referansı.

Araştırma tarihi: 17 Eylül 2026. Geliştirmeye başlarken kütüphane uyumluluğunu ve resmî kurulum belgelerini yeniden doğrula.

---

## Claude'a gönderilecek başlangıç mesajı

Bu dosyanın tamamını oku ve Luma Atelier uygulamasını tarif edilen gereksinimlere göre geliştir. Önce proje klasörünü ve ortamı incele, sonra Faz 0'dan başla. Her fazda çalışan sonuç üret, kabul ölçütlerini doğrula ve ilerlemeyi PROGRESS.md dosyasına kaydet. Yalnızca plan veya arayüz maketiyle durma. Rutin teknik kararları sen ver; gerçek engel veya kullanıcı kararı gereken durumları açıkça belirt. Nihai hedefim, kendi Windows bilgisayarımda masaüstü simgesinden açılan, Türkçe arayüzlü, çevrimdışı çalışan, en az 120 hazır görünümü ve ayrı Sinema Laboratuvarı bulunan kurulabilir bir fotoğraf uygulaması.

## Yeni oturumda devam mesajı

Ana gereksinim dosyasını ve PROGRESS.md dosyasını oku. Önce önceki oturumdan kalan uygulamanın durumunu doğrula. Tamamlanmış fazları yeniden yazmadan ilk eksik kabul ölçütünden devam et. Bitmemiş özellikleri gizleme; her faz sonunda testleri ve ilerleme kaydını güncelle. Kurulabilir Windows uygulaması ve çalışan masaüstü kısayolu teslim edilene kadar belirlenen kapsamı takip et.
