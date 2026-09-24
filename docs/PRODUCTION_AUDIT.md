# Üretim Denetimi — Luma Atelier

Bu belge, uygulamanın gerçekten teslim edilebilir olup olmadığını
sorgulayan bağımsız denetimin kaydıdır. Önceki faz raporları burada
**kanıt** değil, **doğrulanması gereken iddia** olarak ele alınır.

Denetim kuralı: bir davranışın doğru olduğunu ancak, o davranışı
kullanıcı açısından gözlemlenebilir biçimde ölçen tekrarlanabilir bir
kontrol varsa yazıyorum. Kod okuması tek başına kanıt sayılmadı;
geçen test de tek başına kanıt sayılmadı (kod ve test aynı yanlış
varsayımı paylaşabilir — nitekim paylaştığı bir örnek aşağıda B‑01).

Durum: **denetim sürüyor.** Aşağıdaki bölümler tamamlandıkça
güncelleniyor. Açık kalemler "Devam noktası" başlığında.

---

## 1. Denetim anındaki durum

| Alan | Değer |
|---|---|
| Kaynak kök | `<proje-klasoru>` |
| Python | 3.11.9 (`.venv`) |
| Ana bağımlılıklar | PySide6 6.9.1, NumPy 2.2.6, OpenCV 4.11.0, Pillow 12.3.0 |
| Test | 1213 geçti, 0 başarısız (denetim sırasında 42 yeni kontrol eklendi) |
| Sürüm kontrolü | Depo git altında **değil** — kaynak durumu dosya özetiyle kaydedilecek |

Kullanıcı verisi koruması: denetim boyunca kullanıcının fotoğrafları,
projeleri, özel presetleri ve ayarları **değiştirilmedi**. Tüm ölçümler
ya sentetik test görüntüleriyle ya da `LUMA_DATA_HOME` ile ayrı bir
geçici veri klasörüne yönlendirilerek yapıldı.

---

## 2. Kapatılan bulgular

### B‑01 · %100 görünüm, dışa aktarılan dosyadan farklı görüntü veriyordu — P1

**Kök neden.** Konuma bağlı efektler ızgaralarını `np.mgrid[0:h, 0:w]`
ile *işlenen dizinin* boyutundan kuruyordu. %100 görünümde yalnızca
ekranda görünen bölge (karo) işlendiği için her biri karoyu "tüm
fotoğraf" sanıyordu: vignette karonun ortasında oluşuyor, tilt‑shift
şeridi kayıyor, ışık sızıntısı karonun köşesinden başlıyor, maske
karonun içine sığdırılıyor, film grain ve toz farklı bir desen
üretiyordu.

**Kullanıcı etkisi.** Kullanıcı %100'e yakınlaşıp kararını ekranda
gördüğüne göre veriyor; dışa aktardığında farklı bir görüntü elde
ediyordu. Maskeli düzenlemede sapma en büyüğüydü.

**Neden testler yakalamadı.** Faz 5 testi "karo ile tam boy render
arasındaki fark 0.0000" diyordu. Yeniden ölçünce görüldü ki o testte
maske karonun **dışında** kalıyordu; test efekti değil tesadüfü
ölçüyordu. Yeni testler bu yüzden her durumda önce "efekt bu bölgede
gerçekten piksel değiştiriyor mu" diye denetliyor.

**Düzeltme.** `RenderContext`'e `tile_origin` / `tile_frame` ve
`frame_size()` / `coords()` / `normalised_coords()` eklendi. Vignette,
tilt‑shift, radyal bulanıklık, ışık sızıntısı, kromatik aberasyon,
maskeler (`Mask.render(..., origin=, frame=)`), film grain, toz‑çizik
ve kağıt dokusu artık **tam kadraj** koordinatını kullanıyor.
`render_tile` karonun kadrajdaki konumunu bağlama yazıyor.

**Kanıt** (1400×900 kaynak, karo 420×320 @ (700,120); ortalama mutlak
fark, 0..1 ölçeğinde):

| efekt | düzeltmeden önce | sonra |
|---|---|---|
| radyal maske + pozlama | 0.3524 | 0.0000 |
| film grain %100 | 0.1700 | 0.0000 |
| vignette −100 | 0.0981 | 0.0000 |
| kağıt dokusu | — | 0.0001 |
| tilt‑shift, ışık sızıntısı, toz, radyal bulanıklık | — | 0.0000 |

Regresyon kontrolü: `tests/test_tile_position.py` (15 kontrol).

### B‑02 · Geniş yarıçaplı efektlerde karo sınırında dikiş — P1

**Kök neden.** `render_tile` sabit 96 piksel kenar payı kullanıyordu.
Bloom 400 px, anamorfik 1200 px, gaussian 300 px yarıçapa kadar komşu
piksel okuyabiliyor; pay yetersiz kalınca karo kenarında görünür bir
dikiş oluşuyordu.

**Kullanıcı etkisi.** %100 görünümde parlak kaynakların çevresindeki
hale, dışa aktarılan dosyadakinden belirgin biçimde farklıydı.

**Düzeltme.** İşlemler artık okudukları en uzak komşu mesafesini
bildiriyor (`Operation.neighbourhood`); `Recipe.tile_reach()` bunları
toplar (bulanıklıklar birbirini beslediği için en büyüğü yetmez) ve
`render_tile` payı buna göre büyütür. Genişletilmiş bölge 12 MP'yi
aşarsa pay bütçeye kırpılır — uygulama saniyelerce kilitlenmesin diye.

**Kanıt** (1800×1200 kaynak, karo 420×320; karo kenar şeridindeki en
büyük fark):

| efekt | 96 px pay | tarife göre pay |
|---|---|---|
| anamorfik uzunluk 800 | 0.4598 | 0.0000 |
| halation r=150 | 0.1275 | 0.0022 |
| bloom r=300 | 0.0990 | 0.0013 |
| gaussian r=200 | 0.0644 | 0.0015 |

Kalan ≤0.0022 sapma `downsampled_blur`'ün küçült‑bulanıklaştır‑büyüt
ızgarasının karoda birebir aynı hizalanmamasından geliyor; 0..255
ölçeğinde yarım seviyenin altında.

### B‑03 · Kenar payı büyüyünce %100 görünüm arayüzü donduruyordu — P1

**Kök neden.** Karo doğrudan GUI iş parçacığında üretiliyordu. B‑02
düzeltmesiyle pay büyüdüğü için süre de büyüdü.

**Ölçüm** (6000×4000 kaynak, 1600×900 karo, bu makine):

| tarif | pay | medyan | en kötü |
|---|---|---|---|
| yalın (pozlama) | 96 px | 79 ms | 82 ms |
| bloom 300 + halation 150 + grain | 697 px | 1287 ms | 1310 ms |
| preset "Dream Sequence" | 630 px | 1363 ms | 1379 ms |
| anamorfik 1200 (uç değer) | 900 px | 2950 ms | 2986 ms |

**Düzeltme.** `RenderService.request_tile()` eklendi: karo havuzda
üretiliyor, sonuç jetonla doğrulanıp `tileReady` ile geliyor. Kullanıcı
beklerken kaydırdıysa gelen karo ekrana basılmıyor. Gizli görünüm
(açık olmayan Sinema Laboratuvarı) artık karo istemiyor — aynı iş iki
kez yapılıyordu.

Regresyon kontrolü: `tests/test_detail_tile.py::TestAsyncTileDelivery`
(karo aynı pikselleri getiriyor; geçersiz kalan karo ekrana basılmıyor).

### B‑04 · Vignette hiç uygulanmıyordu (denetim sırasında oluşan hata) — P1

Karo koordinat düzeltmesini uygularken bir yama `_radial_distance`
çağrısını `float(params["center_x"], ctx)` haline getirdi. Katman her
render'da `TypeError` ile düşüyor, üst katmandaki geniş `except`
bunu yalnızca günlüğe yazıp sessizce atlıyordu — yani **vignette
çalışmıyordu ve kullanıcıya hiçbir şey söylenmiyordu**.

Bu, denetimin kendi hatasıydı ve düzeltildi; ama asıl bulguyu da
gösteriyor: `Recipe.apply` içindeki katman bazlı `except` gerçek bir
hatayı kullanıcıdan gizleyebiliyor. Bu kalem "Açık bulgular" altında
izleniyor (A‑01).

### B‑05 · Kromatik aberasyon karonun merkezine göre saçılıyordu — P1

`chromatic_aberration` kanal ölçeklemesinin merkezi olarak işlenen
dizinin ortasını alıyordu. Karo işlenirken saçılma yanlış yöne
gidiyordu. Kadraj merkezine bağlandı; regresyon kontrolü
`tests/test_tile_position.py` içinde.

### B‑06 · Bir efekt çalışmadığında kullanıcıya hiçbir şey söylenmiyordu — P2

`Recipe.apply` tek katmanın hatasında render'i çökertmiyor — bu doğru
davranış. Ama hata yalnızca günlüğe yazılıyordu: B‑04'te vignette her
render'da düşerken uygulama sessizce çalışmaya devam etti.

**Düzeltme.** `Recipe.apply(..., failures=[...])` atlanan katmanları
bildiriyor; `RenderResult.failed_layers` bunu taşıyor ve düzenleyici
durum çubuğunda "Bu efektler uygulanamadı ve atlandı: …" yazıyor.
Regresyon: `tests/test_layer_failures.py`.

### B‑07 · Sıcaklık kaydırıcısı ters yöndeydi — P2

2500 K amber, 11000 K mavi veriyordu. Kaydırıcının **kendi ipucu**
("Düşük değer soğuk (mavi), yüksek değer sıcak (amber)") ve Lightroom,
Capture One, Camera Raw'daki yaygın davranış bunun tersi.

**Kullanıcı etkisi.** Kaydırıcı beklenenin tersine hareket ediyordu;
preset dosyalarındaki sayılar da fotoğrafçıya ters okunuyordu
("Golden Hour: 5300 K" bir ısıtma değil soğutma değeri gibi).

**Düzeltme ve veri koruması.** Yön düzeltildi. Görünümün değişmemesi
için 26 yerleşik presetin değeri 6500 K ekseninde yansıtıldı
(K → 6500²/K). Kazanç `log(K/6500)` ile orantılı olduğu için bu
**birebir aynı** sonucu verir: 26 presetin tamamında ölçülen kazanç
farkı 0.000000. Kullanıcının eski dosyaları için tarif şeması v2'ye
çıkarıldı; v1 tarifleri yüklenirken aynı yansıtma uygulanıyor, yani
kayıtlı projeler ve özel presetler aynı görünmeye devam ediyor.
Regresyon: `tests/test_white_balance_direction.py`.

### B‑08 · Kontrast, 1.0 üzeri başlık payını yok ediyordu — P2

`tone.contrast` pozitif yönde tanh omzunu tüm değere uyguluyordu;
1.5 ve 4.0 girdileri aynı çıkıyordu (~1.0). Bloom, halation ve
anamorfik çizgi parlak kaynakların gerçek şiddetini bu paydan okur.

**Düzeltme.** 0..1 gövdesi eskisi gibi işleniyor (presetlerin görünümü
birebir korunuyor: 0.2 → 0.1364, 0.8 → 0.8458 değerleri değişmedi),
1.0 üzeri pay doğrusal geçiriliyor. Ölçüm: amount=50'de 1.5 → 1.6524,
4.0 → 5.2149; artık ayırt edilebiliyor ve sıralama korunuyor.
Regresyon: `tests/test_headroom.py` (kontrast sonrası bloom halesinin
kaybolmadığını da ölçüyor).

### B‑09 · 16‑bit TIFF'te renk profili hiç uygulanmıyordu — P1

**Kök neden.** 16‑bit TIFF'ler `tifffile` ile okunuyor ve o dalda ICC
dönüşümü atlanıyordu. Pillow dalında da yüksek bit derinlikli modlar
("I;16" ve benzeri) bilerek atlanıyordu — Pillow'un renk yönetimi
16‑bit RGB görüntüyü doğrudan çeviremiyor. Buna rağmen metadata
profili okuduğunu bildiriyordu (`assumed_srgb=False`).

**Kullanıcı etkisi.** Geniş gamutlu (ProPhoto, Adobe RGB) 16‑bit bir
TIFF açıldığında renkler yanlış görünüyordu. Ölçüm: ProPhoto profilli
test kartında kanal başına **69/255** sapma — kırmızı (220,40,40)
yerine (151,67,38).

**Düzeltme.** Gömülü profilden sRGB'ye giden 52³ düğümlü bir kafes
lcms ile kuruluyor ve float veriye trilineer interpolasyonla
uygulanıyor. Kafes düğümleri 8‑bit'te birebir temsil edilebilecek
şekilde seçildi (255/51 = 5). Pikselin kendi hassasiyeti korunuyor;
yalnızca eşleme eğrisi örneklenmiş oluyor. Ölçülen hata **69/255 →
2/255**; sRGB profilli dosyalarda 0/255 (kimlik kafesi atlanıyor).
Yükleme maliyeti 40 ms.

`ImageMetadata.icc_applied` eklendi: profilin *okunmuş* olması
uygulandığı anlamına gelmiyor. Uygulanamadıysa `assumed_srgb` artık
doğru biçimde True.

### B‑10 · Çıktı dosyası yanlış renk profiliyle etiketleniyordu — P1

Yükleyici pikselleri sRGB'ye çeviriyor, dışa aktarım ise **kaynağın**
profilini geri gömüyordu. Sonuç iki kez yanlıştı: sRGB pikseller Adobe
RGB etiketiyle yazılıyor, dosya başka bir programda yine kaymış
renklerle açılıyordu.

**Düzeltme.** `_output_profile()`: dönüşüm yapıldıysa sRGB etiketi,
yapılamadıysa kaynağın profili yazılıyor. Regresyon testi çıktı
dosyasını *başka bir program gibi* açıp etiketli profili uyguluyor ve
başlangıçtaki sRGB renklerini geri alıyor (hata ≤ 6/255).


---

## 3. Açık bulgular

| No | Bulgu | Öncelik | Durum |
|---|---|---|---|
| A‑01 | Küçük resim bellek önbelleği sınırsız; `prune_cache()` çağrılmıyor | P2 | doğrulandı, düzeltilmedi |
| A‑02 | Üç ayar toplanıyor ama hiç uygulanmıyor (`confirm_large_export`, `remember_window`, `keyboard_hints`) | P2 | doğrulandı, düzeltilmedi |
| A‑03 | Kaldırıcı `UserDataDir()` yanlış klasörü gösteriyor; `[InstallDelete]` yok | P2 | doğrulandı, düzeltilmedi |
| A‑04 | `.luma` dosya ilişkilendirmesi çalışmıyor | P2 | doğrulandı, düzeltilmedi |
| A‑05 | Paket içinde kullanılmayan `psutil` | P3 | doğrulandı, düzeltilmedi |
| A‑06 | Pakette sürüm/derleme kimliği ve derleme bildirimi yok | P2 | doğrulandı, düzeltilmedi |

---

## 4. Devam noktası

Sırada (bu sırayla):

1. Görüntü doğruluğu: alfa kenarlarında komşu okuyan efektler,
   NaN/Inf ve taşma taraması, 38 işlemin nötr/uç değer sözleşmesi.
2. Bellek: süreç RSS + yerel ayırmalarla, önbellek ısınması ile sızıntı
   ayrılarak.
4. Dosya/kullanıcı verisi dayanıklılığı (`tools/audit_reliability.py`
   yeniden çalıştırılacak) ve yarış durumları
   (`tools/audit_races.py` çıktı üretmedi, incelenecek).
5. Gerçek kullanıcı akışı: her düğme, menü ve kısayol.
6. Performans: soğuk/ısınmış başlangıç, medyan ve p95, uzun oturum.
7. Paketleme: sürüm kimliği, derleme bildirimi, kaldırıcı yolları,
   temiz ortam kurulumu.
8. Bağımlılıklar, lisans bildirimleri, ağ ve günlük incelemesi.
