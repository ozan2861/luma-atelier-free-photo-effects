"""Genel koleksiyon: 9 kategori x 10 = 90 hazir gorunum.

Her preset gercek bir tariftir: hangi islemlerin hangi parametrelerle
birlestigi burada yazilir. Renk varyasyonuyla sayi sisirilmez; her
gorunumun kendi karakteri, amaclanan fotograf turu ve farkli islem
birlesimi vardir.

Bicim:
    (kimlik, ad, amac, aciklama, [(islem_id, {parametreler}), ...])
"""
from __future__ import annotations

#: Tip kisaltmasi: (id, ad, amac, aciklama, katmanlar)
PresetDef = tuple[str, str, str, str, list[tuple[str, dict]]]


# ============================================================ DOGAL VE TEMIZ
NATURAL: list[PresetDef] = [
    ("natural-balance", "Natural Balance", "Her tur fotograf",
     "Notr baslangic: hafif kontrast, dengeli ten tonu, dogal renk.",
     [("tone.contrast", {"amount": 20}),
      ("color.vibrance", {"amount": 24}),
      ("tone.shadows_highlights", {"shadows": 16, "highlights": -18}),
      ("tone.black_white_point", {"black": 6, "white": 5})]),

    ("clean-daylight", "Clean Daylight", "Gun isigi, dis mekan",
     "Gunes isigini temizler: beyazlar notr, golgeler acik, renk berrak.",
     [("color.white_balance", {"kelvin": 6200, "tint": -3}),
      ("tone.black_white_point", {"black": 4, "white": 6}),
      ("tone.shadows_highlights", {"shadows": 18, "highlights": -18}),
      ("color.vibrance", {"amount": 10})]),

    ("gentle-contrast", "Gentle Contrast", "Duz isikli sahneler",
     "Ton egrisiyle yumusak S kontrasti; golgeler ezilmez.",
     [("tone.curves", {"rgb": [[0, 0], [0.25, 0.21], [0.75, 0.79], [1, 1]]}),
      ("color.saturation", {"amount": 5})]),

    # Olculu olmasi gerekiyordu ama gorunmez kalmisti (uc sahnede en
    # fazla 0.007 degisim). Keskinlestirme duz yuzeylerde tutunacak bir
    # sey bulamaz; yerel kontrast ve mikro ton bu yuzden yukseltildi.
    ("soft-detail", "Soft Detail", "Portre ve urun",
     "Ayrinti belirginlesir ama sertlesmez: olculu keskinlestirme, "
     "belirgin yerel kontrast ve acilan golge.",
     [("detail.sharpen", {"amount": 72, "radius": 1.6, "threshold": 3}),
      ("detail.clarity", {"amount": 34, "radius": 55}),
      ("tone.shadows_highlights", {"shadows": 22, "highlights": -12}),
      ("tone.black_white_point", {"black": 8, "white": 6})]),

    ("true-color", "True Color", "Belge ve reprodüksiyon",
     "Renkleri olabildigince sadik birakir; yalnizca ton araligini acar.",
     [("tone.black_white_point", {"black": 14, "white": 12}),
      ("tone.curves", {"rgb": [[0.0, 0.0], [0.18, 0.16], [0.5, 0.5],
                               [0.82, 0.84], [1.0, 1.0]]}),
      ("detail.sharpen", {"amount": 60, "radius": 0.9, "threshold": 2}),
      ("color.saturation", {"amount": -6})]),

    ("cool-clean", "Cool Clean", "Mimari, ic mekan",
     "Serin beyaz denge, notr golgeler, modern ve ferah his.",
     [("color.white_balance", {"kelvin": 8200, "tint": -14}),
      ("color.grading", {"shadow_color": [0.40, 0.48, 0.60],
                         "shadow_amount": 34,
                         "midtone_color": [0.47, 0.51, 0.55],
                         "midtone_amount": 20,
                         "highlight_color": [0.50, 0.53, 0.56],
                         "highlight_amount": 20}),
      ("color.hsl", {"orange_sat": -24, "yellow_sat": -18, "blue_sat": 16}),
      ("tone.contrast", {"amount": 18}),
      ("detail.clarity", {"amount": 22, "radius": 70})]),

    # Sinirdaydi (en fazla 0.0116 degisim, gorunurluk esigi 0.012).
    # "Temiz" karakteri korunarak sicaklik ve ton araligi guclendirildi.
    ("warm-clean", "Warm Clean", "Aile, ic mekan",
     "Sicak ama kirli olmayan ton; tenler canli, beyazlar krem, "
     "golgeler acik kalir.",
     [("color.white_balance", {"kelvin": 5150, "tint": 6}),
      ("color.grading", {"highlight_color": [0.62, 0.54, 0.43],
                         "highlight_amount": 38,
                         "shadow_color": [0.52, 0.50, 0.47],
                         "shadow_amount": 18}),
      ("color.vibrance", {"amount": 26, "protect_skin": True}),
      ("tone.shadows_highlights", {"shadows": 14})]),

    ("airy-whites", "Airy Whites", "Dugun, yuksek anahtar",
     "Parlak alanlari acar, golgeleri hafifce kaldirir: havadar gorunum.",
     [("tone.exposure", {"stops": 0.25}),
      ("tone.shadows_highlights", {"shadows": 26, "highlights": -8}),
      ("tone.fade", {"lift": 12, "rolloff": 0, "amount": 100}),
      ("color.saturation", {"amount": -6})]),

    ("rich-natural", "Rich Natural", "Manzara ve seyahat",
     "Doygunluk ve derinlik artar, renkler dogal kalir.",
     [("tone.contrast", {"amount": 22}),
      ("color.vibrance", {"amount": 28}),
      ("detail.clarity", {"amount": 18, "radius": 70}),
      ("lens.vignette", {"amount": -12, "midpoint": 0.7})]),

    ("everyday-polish", "Everyday Polish", "Gunluk telefon fotografi",
     "Hizli iyilestirme: ton araligi, canlilik ve ayrinti bir arada.",
     [("tone.shadows_highlights", {"shadows": 38, "highlights": -32}),
      ("tone.black_white_point", {"black": 12, "white": 10}),
      ("tone.contrast", {"amount": 26}),
      ("color.vibrance", {"amount": 40}),
      ("detail.clarity", {"amount": 24, "radius": 55}),
      ("detail.sharpen", {"amount": 90, "radius": 1.0, "threshold": 3})]),
]


# ==================================================================== PORTRE
PORTRAIT: list[PresetDef] = [
    # Renk kaymasi **yoktur**; tek fikir yumusakliktir. Yonlu isik
    # isteyen "Window Light" ayri bir gorunumdur.
    ("soft-portrait", "Soft Portrait", "Portre",
     "Salt yumusaklik: belirgin diffusion, acik golge, renk oldugu gibi. "
     "Ten rengi araligini koruyan reçetedir; cilt rotusu yapmaz.",
     [("light.diffusion", {"strength": 52, "radius": 75, "lift": 30}),
      ("tone.shadows_highlights", {"shadows": 26, "highlights": -18}),
      ("tone.fade", {"lift": 10, "rolloff": 12, "amount": 100}),
      ("color.vibrance", {"amount": 12, "protect_skin": True})]),

    # "Golden Skin" tene sicaklik ekler; bu gorunum **ayrim** kurar:
    # ten sicak kalirken cevre belirgin sekilde serinler. Parlak alanda
    # sicaklik yoktur, golgede mavi vardir.
    ("warm-skin", "Warm Skin", "Portre, gun batimi",
     "Sicak ten / serin cevre ayrimi: golgeler maviye kayar, ten "
     "sicakligini korur.",
     [("color.hsl", {"orange_sat": 20, "orange_lum": 10,
                     "blue_sat": -28, "cyan_sat": -20, "green_sat": -16}),
      ("color.grading", {"shadow_color": [0.38, 0.45, 0.62],
                         "shadow_amount": 42,
                         "highlight_color": [0.52, 0.50, 0.48],
                         "highlight_amount": 12}),
      ("tone.contrast", {"amount": 14})]),

    ("cool-editorial", "Cool Editorial", "Moda, editoryal portre",
     "Serin golgeler ve dusuk doygunluk; dergi sayfasi karakteri.",
     [("color.white_balance", {"kelvin": 6800, "tint": -8}),
      ("color.saturation", {"amount": -16}),
      ("tone.curves", {"rgb": [[0, 0.02], [0.3, 0.27], [0.7, 0.74], [1, 0.98]]}),
      ("detail.clarity", {"amount": 12, "radius": 45})]),

    # Sokak kategorisindeki "Urban Fade" ayni mat aileden ama **serin**;
    # bu portre surumu kasitli olarak **sicak** mat: golgeler kahve-krem,
    # mavi kayma yok.
    ("matte-portrait", "Matte Portrait", "Portre",
     "Sicak mat baski: kalkik siyahlar kahverengiye, parlak alanlar "
     "kreme calar.",
     [("tone.fade", {"lift": 34, "rolloff": 16, "amount": 100}),
      ("color.split_tone", {"shadow_color": [0.42, 0.36, 0.30],
                            "shadow_strength": 40,
                            "highlight_color": [0.97, 0.91, 0.80],
                            "highlight_strength": 30}),
      ("color.saturation", {"amount": -6})]),

    ("beauty-glow", "Beauty Glow", "Guzellik, yakin portre",
     "Parlak alanlardan yayilan yumusak isilti; kontrast dusurulur.",
     [("light.bloom", {"threshold": 0.58, "radius": 110, "intensity": 42}),
      ("light.diffusion", {"strength": 30, "radius": 60, "lift": 28}),
      ("tone.contrast", {"amount": -12})]),

    ("low-key-portrait", "Low Key Portrait", "Studyo, koyu zemin",
     "Koyu, derin golgeler; yalnizca isik alan yuzey one cikar.",
     [("tone.curves", {"rgb": [[0, 0], [0.35, 0.22], [0.75, 0.82], [1, 1]]}),
      ("tone.shadows_highlights", {"shadows": -24, "highlights": -8}),
      ("lens.vignette", {"amount": -38, "midpoint": 0.5, "feather": 0.85}),
      ("color.saturation", {"amount": -8})]),

    ("high-key-portrait", "High Key Portrait", "Beyaz zemin, studyo",
     "Aydinlik ve temiz; golgeler neredeyse kalkar.",
     [("tone.shadows_highlights", {"shadows": 46, "highlights": -40}),
      ("tone.exposure", {"stops": 0.30}),
      ("tone.fade", {"lift": 10, "rolloff": 14, "amount": 100}),
      ("tone.contrast", {"amount": -12}),
      ("light.diffusion", {"strength": 18, "radius": 45, "lift": 24})]),

    # "Golden Hour"dan ayrim: burada hale ve bloom **yok**. Sicaklik
    # global beyaz dengesiyle degil, dogrudan ten renk araligina (turuncu
    # ve kirmizi) uygulanir; gokyuzu ve giysi rengi kaymaz.
    ("golden-skin", "Golden Skin", "Altin saat portre",
     "Bakir ten: sicaklik yalnizca ten renk araliginda, arka plan "
     "oldugu gibi kalir.",
     [("color.hsl", {"orange_sat": 30, "orange_lum": 14, "orange_hue": -6,
                     "red_sat": 20, "red_lum": 8, "yellow_sat": 12}),
      ("color.grading", {"midtone_color": [0.60, 0.51, 0.42],
                         "midtone_amount": 24}),
      ("tone.shadows_highlights", {"shadows": 16, "highlights": -20}),
      ("color.vibrance", {"amount": 10, "protect_skin": True})]),

    ("pastel-portrait", "Pastel Portrait", "Cocuk, aile",
     "Dusuk doygunluk ve acik tonlar; yumusak pastel palet.",
     [("color.saturation", {"amount": -24}),
      ("tone.fade", {"lift": 22, "rolloff": 10, "amount": 100}),
      ("color.grading", {"midtone_color": [0.55, 0.51, 0.53],
                         "midtone_amount": 20}),
      ("light.diffusion", {"strength": 16, "radius": 40, "lift": 18})]),

    ("crisp-editorial", "Crisp Editorial", "Kurumsal portre",
     "Net, kontrastli ve renk dengesi kontrollu; is portresi icin.",
     [("detail.sharpen", {"amount": 95, "radius": 1.1, "threshold": 3}),
      ("detail.clarity", {"amount": 24, "radius": 50}),
      ("tone.contrast", {"amount": 20}),
      ("color.vibrance", {"amount": 8, "protect_skin": True})]),
]


# =================================================================== MANZARA
LANDSCAPE: list[PresetDef] = [
    ("alpine-clear", "Alpine Clear", "Dag, kar, yuksek irtifa",
     "Berrak hava hissi: soguk mavi gokyuzu, net ayrinti.",
     [("color.white_balance", {"kelvin": 6600, "tint": -4}),
      ("color.hsl", {"blue_sat": 22, "blue_lum": -12, "aqua_sat": 16}),
      ("detail.clarity", {"amount": 28, "radius": 85}),
      ("tone.black_white_point", {"black": 8, "white": 6})]),

    ("forest-depth", "Forest Depth", "Orman, yesillik",
     "Yesil ayrimi: yapraklar koyulasir ve doygunlasir, golgeler yosun "
     "yesiline caler.",
     [("color.hsl", {"green_sat": 38, "green_lum": -22, "green_hue": -10,
                     "yellow_hue": -18, "yellow_sat": 14,
                     "aqua_sat": 16}),
      ("color.grading", {"shadow_color": [0.36, 0.54, 0.42],
                         "shadow_amount": 44,
                         "highlight_color": [0.52, 0.54, 0.46],
                         "highlight_amount": 18}),
      ("tone.contrast", {"amount": 20}),
      ("detail.clarity", {"amount": 24, "radius": 70})]),

    ("desert-gold", "Desert Gold", "Col, kum, kaya",
     "Kum ve kaya tonlarini bakira cevirir; gokyuzu derinlesir.",
     [("color.white_balance", {"kelvin": 5300, "tint": 10}),
      ("color.hsl", {"orange_sat": 24, "yellow_sat": 18, "blue_lum": -16}),
      ("color.grading", {"highlight_color": [0.62, 0.54, 0.40],
                         "highlight_amount": 30}),
      ("detail.clarity", {"amount": 22, "radius": 90})]),

    # Sokak kategorisindeki "Rainy Street" de mavi-yesil aileden ama
    # **doygunlugu dusuk ve islak**; bu gorunum tam tersi: temiz, doygun
    # ve berrak.
    ("ocean-blue", "Ocean Blue", "Deniz, kiyi",
     "Berrak su: mavi ve turkuaz belirgin doygunlukta, yesiller geri "
     "cekilir.",
     [("color.hsl", {"blue_sat": 44, "blue_lum": 6, "aqua_sat": 40,
                     "aqua_hue": -12, "green_sat": -22,
                     "yellow_sat": -12}),
      ("tone.shadows_highlights", {"shadows": 10, "highlights": -24}),
      ("tone.contrast", {"amount": 14}),
      ("color.vibrance", {"amount": 24}),
      ("lens.vignette", {"amount": -12, "midpoint": 0.75})]),

    ("autumn-copper", "Autumn Copper", "Sonbahar",
     "Sari ve turuncuyu bakira tasir; yesilleri geri ceker.",
     [("color.hsl", {"yellow_hue": -18, "yellow_sat": 22, "orange_sat": 26,
                     "green_sat": -20, "green_hue": 14}),
      ("color.white_balance", {"kelvin": 5500, "tint": 6}),
      ("tone.contrast", {"amount": 16})]),

    # "Peach Fade" ile ayni "soluk" ailede ama **karsit renkte**:
    # burada kayma soguk mavi-gri sis, orada sicak seftali.
    ("misty-hills", "Misty Hills", "Sisli manzara",
     "Soguk mavi-gri sis: uzak katmanlar aciir, yesiller sakinlesir.",
     [("light.diffusion", {"strength": 34, "radius": 110, "lift": 30}),
      ("color.grading", {"shadow_color": [0.40, 0.48, 0.62],
                         "shadow_amount": 40,
                         "highlight_color": [0.48, 0.52, 0.58],
                         "highlight_amount": 26}),
      ("color.hsl", {"green_sat": -24, "cyan_sat": 12, "blue_lum": 8}),
      ("tone.fade", {"lift": 18, "rolloff": 14, "amount": 100}),
      ("color.saturation", {"amount": -16}),
      ("tone.shadows_highlights", {"highlights": -22})]),

    ("sunset-drama", "Sunset Drama", "Gun batimi",
     "Gokyuzu renklerini guclendirir, on plani koyultur.",
     [("tone.curves", {"rgb": [[0, 0], [0.3, 0.24], [0.72, 0.8], [1, 1]]}),
      ("color.grading", {"highlight_color": [0.66, 0.48, 0.36],
                         "highlight_amount": 38,
                         "shadow_color": [0.40, 0.44, 0.58],
                         "shadow_amount": 28}),
      ("color.vibrance", {"amount": 26}),
      ("lens.vignette", {"amount": -22, "midpoint": 0.62})]),

    ("winter-light", "Winter Light", "Kis, kar",
     "Soguk ve acik; karin mavi golgelerini korur.",
     [("color.white_balance", {"kelvin": 7200, "tint": -6}),
      ("tone.shadows_highlights", {"shadows": 22, "highlights": -24}),
      ("color.saturation", {"amount": -12}),
      ("tone.black_white_point", {"black": 2, "white": 8})]),

    ("emerald-valley", "Emerald Valley", "Yesil vadi, tarla",
     "Zumrut yesili vurgusu ve zengin orta ton.",
     [("color.hsl", {"green_hue": -10, "green_sat": 28, "green_lum": 6,
                     "yellow_sat": 14}),
      ("color.grading", {"midtone_color": [0.46, 0.55, 0.48],
                         "midtone_amount": 24}),
      ("detail.clarity", {"amount": 18, "radius": 75}),
      ("color.vibrance", {"amount": 16})]),

    ("earth-tones", "Earth Tones", "Toprak, kirsal",
     "Toprak paleti: kahve, oker ve zeytin tonlari one cikar.",
     [("color.hsl", {"orange_sat": 12, "yellow_hue": -14, "green_sat": -18,
                     "blue_sat": -22}),
      ("color.saturation", {"amount": -8}),
      ("color.split_tone", {"shadow_color": [0.36, 0.33, 0.28],
                            "shadow_strength": 24,
                            "highlight_color": [0.88, 0.82, 0.70],
                            "highlight_strength": 22})]),
]


# ============================================================ SOKAK VE SEHIR
STREET: list[PresetDef] = [
    # Sinema koleksiyonundaki "Steel Thriller" ile ayni aile. Bu surum
    # kasitli olarak *dokuya* yaslanir: renk kaydirmasi hafif, yerel
    # kontrast yuksek. Sinematik surum ise derin graded ve ezik ayakli.
    ("urban-steel", "Urban Steel", "Sehir, mimari",
     "Beton ve cam icin dokulu gri-mavi: renk geri cekilir, yuzey "
     "ayrintisi one cikar.",
     [("color.grading", {"shadow_color": [0.45, 0.48, 0.53],
                         "shadow_amount": 20}),
      ("color.saturation", {"amount": -18}),
      ("detail.clarity", {"amount": 46, "radius": 38}),
      ("detail.sharpen", {"amount": 42, "radius": 1.1, "threshold": 3}),
      ("tone.black_white_point", {"black": 10, "white": 8}),
      ("tone.contrast", {"amount": 16})]),

    ("concrete-mood", "Concrete Mood", "Beton, brutalist mimari",
     "Gri yuzeyleri dokulu gosterir; renk geri cekilir.",
     [("color.saturation", {"amount": -34}),
      ("detail.clarity", {"amount": 38, "radius": 45}),
      ("tone.curves", {"rgb": [[0, 0.03], [0.4, 0.36], [0.8, 0.84], [1, 0.99]]}),
      ("texture.grain", {"amount": 14, "size": 1.8})]),

    # "Ocean Blue" berrak ve doygundur; bu gorunum **soluk ve islak**:
    # renk geri ceker, yansimalar parlar.
    ("rainy-street", "Rainy Street", "Yagmur, islak zemin",
     "Islak asfalt: renk soluklasir, yansimalar parlar, hava serinler.",
     [("color.white_balance", {"kelvin": 7400, "tint": -6}),
      ("light.bloom", {"threshold": 0.60, "radius": 100, "intensity": 54}),
      ("color.saturation", {"amount": -26}),
      ("tone.fade", {"lift": 14, "rolloff": 12, "amount": 100}),
      ("tone.shadows_highlights", {"shadows": 20, "highlights": -22})]),

    ("night-walk", "Night Walk", "Gece sokak",
     "Karanlikta ayrinti acar, isik kaynaklarina hale verir.",
     [("tone.shadows_highlights", {"shadows": 34, "highlights": -26}),
      ("light.halation", {"threshold": 0.66, "radius": 40, "intensity": 46}),
      ("detail.denoise", {"luminance": 26, "colour": 42, "detail": 60}),
      ("color.grading", {"shadow_color": [0.42, 0.46, 0.58],
                         "shadow_amount": 24})]),

    ("neon-city", "Neon City", "Neon isikli gece",
     "Magenta ve cyan neon ayrimi; isiklar parlar.",
     [("color.grading", {"shadow_color": [0.36, 0.42, 0.66],
                         "shadow_amount": 38,
                         "highlight_color": [0.66, 0.40, 0.62],
                         "highlight_amount": 30}),
      ("color.vibrance", {"amount": 32}),
      ("light.bloom", {"threshold": 0.62, "radius": 100, "intensity": 55}),
      ("light.anamorphic", {"threshold": 0.85, "length": 240,
                            "thickness": 5, "intensity": 34})]),

    ("vintage-street", "Vintage Street", "Sokak, belgesel",
     "Eski baski hissi: soluk renk, hafif grain.",
     [("tone.fade", {"lift": 20, "rolloff": 12, "amount": 100}),
      ("color.saturation", {"amount": -18}),
      ("color.split_tone", {"shadow_color": [0.40, 0.42, 0.34],
                            "shadow_strength": 24,
                            "highlight_color": [0.92, 0.86, 0.70],
                            "highlight_strength": 26}),
      ("texture.grain", {"amount": 24, "size": 2.4})]),

    ("moody-architecture", "Moody Architecture", "Mimari, ic mekan",
     "Koyu ve grafik; cizgiler ve golgeler one cikar.",
     [("tone.curves", {"rgb": [[0, 0], [0.32, 0.20], [0.72, 0.80], [1, 1]]}),
      ("color.saturation", {"amount": -28}),
      ("detail.clarity", {"amount": 34, "radius": 55}),
      ("lens.vignette", {"amount": -26, "midpoint": 0.6})]),

    ("subway-contrast", "Subway Contrast", "Metro, tunel, ic mekan",
     "Yapay isikta sert kontrast ve temiz beyaz denge.",
     [("color.white_balance", {"kelvin": 4200, "tint": -10}),
      ("tone.contrast", {"amount": 34}),
      ("tone.black_white_point", {"black": 14, "white": 6}),
      ("detail.denoise", {"luminance": 20, "colour": 34, "detail": 55})]),

    # "Matte Portrait" sicak mattir; bu surum **serin ve dokulu**.
    ("urban-fade", "Urban Fade", "Sokak, gundelik",
     "Serin mat sokak estetigi: soluk gri-mavi tonlar, yuzey dokusu "
     "acikta.",
     [("tone.fade", {"lift": 26, "rolloff": 18, "amount": 100}),
      ("color.grading", {"shadow_color": [0.40, 0.46, 0.58],
                         "shadow_amount": 44,
                         "highlight_color": [0.50, 0.52, 0.54],
                         "highlight_amount": 24}),
      ("detail.clarity", {"amount": 28, "radius": 45}),
      ("color.saturation", {"amount": -24})]),

    ("amber-street", "Amber Street", "Aksam sokagi, sokak lambasi",
     "Sokak lambasinin kehribar tonu; golgeler mavi kalir.",
     [("color.grading", {"highlight_color": [0.66, 0.52, 0.36],
                         "highlight_amount": 40,
                         "shadow_color": [0.38, 0.44, 0.60],
                         "shadow_amount": 30}),
      ("light.halation", {"threshold": 0.72, "radius": 34, "intensity": 38}),
      ("tone.contrast", {"amount": 18}),
      ("texture.grain", {"amount": 16, "size": 2.0})]),
]


# ========================================================= ANALOG VE VINTAGE
ANALOG: list[PresetDef] = [
    ("faded-print", "Faded Print", "Eski baski taramasi",
     "Zamanla solmus baski: siyahlar kalkik, renk zayif.",
     [("tone.fade", {"lift": 34, "rolloff": 20, "amount": 100}),
      ("color.saturation", {"amount": -26}),
      ("color.split_tone", {"shadow_color": [0.46, 0.44, 0.38],
                            "shadow_strength": 30,
                            "highlight_color": [0.94, 0.88, 0.76],
                            "highlight_strength": 28}),
      ("texture.grain", {"amount": 20, "size": 2.6})]),

    ("warm-negative", "Warm Negative", "35 mm sicak negatif",
     "Sicak negatif karakteri: yumusak omuz, kehribar parlak alan.",
     [("film.tone_curve", {"toe": 38, "shoulder": 48, "strength": 14}),
      ("color.white_balance", {"kelvin": 4800, "tint": 14}),
      ("color.grading", {"highlight_color": [0.70, 0.55, 0.36],
                         "highlight_amount": 44,
                         "shadow_color": [0.54, 0.48, 0.42],
                         "shadow_amount": 28}),
      ("color.hsl", {"orange_sat": 20, "blue_sat": -24}),
      ("texture.grain", {"amount": 26, "size": 2.2, "colour": True})]),

    ("cool-negative", "Cool Negative", "35 mm serin negatif",
     "Serin negatif: mavi golgeler, kontrollu kontrast.",
     [("film.tone_curve", {"toe": 26, "shoulder": 34, "strength": 20}),
      ("color.white_balance", {"kelvin": 8400, "tint": -16}),
      ("color.grading", {"shadow_color": [0.34, 0.46, 0.66],
                         "shadow_amount": 46,
                         "highlight_color": [0.48, 0.52, 0.58],
                         "highlight_amount": 24}),
      ("color.hsl", {"blue_sat": 22, "aqua_sat": 16, "orange_sat": -22}),
      ("texture.grain", {"amount": 24, "size": 2.2, "colour": True})]),

    ("instant-memory", "Instant Memory", "Aninda kamera baskisi",
     "Aninda film: dusuk kontrast, kayik renk, kose karartmasi.",
     [("tone.fade", {"lift": 30, "rolloff": 18, "amount": 100}),
      ("style.cross_process", {"strength": 34, "shadow_shift": -18,
                               "saturation": 10, "amount": 70}),
      ("lens.vignette", {"amount": -26, "midpoint": 0.55}),
      ("texture.grain", {"amount": 18, "size": 3.0})]),

    ("retro-summer", "Retro Summer", "Tatil, yaz",
     "70'ler tatil kartpostali: sicak, doygun, hafif sizintili.",
     [("color.white_balance", {"kelvin": 5200, "tint": 8}),
      ("color.vibrance", {"amount": 26}),
      ("texture.light_leak", {"intensity": 26, "color": [1.0, 0.62, 0.28],
                              "size": 0.7}),
      ("tone.fade", {"lift": 16, "rolloff": 8, "amount": 100})]),

    ("dusty-archive", "Dusty Archive", "Arsiv, eski belge",
     "Tozlu arsiv kutusu hissi: benekler, cizikler, soluk renk.",
     [("texture.dust", {"dust": 38, "scratches": 26, "dust_size": 3.5}),
      ("color.saturation", {"amount": -30}),
      ("tone.fade", {"lift": 24, "rolloff": 14, "amount": 100}),
      ("texture.paper", {"strength": 26, "scale": 5, "warmth": 24})]),

    ("sepia-paper", "Sepia Paper", "Portre, eski fotograf",
     "Sepya baski: tek renk ton, kagit dokusu.",
     [("color.monochrome", {"amount": 100, "orange": 14, "yellow": 10}),
      ("color.split_tone", {"shadow_color": [0.32, 0.26, 0.18],
                            "shadow_strength": 46,
                            "highlight_color": [0.96, 0.88, 0.70],
                            "highlight_strength": 42}),
      ("texture.paper", {"strength": 32, "scale": 6, "warmth": 34}),
      ("texture.grain", {"amount": 18, "size": 2.4})]),

    ("cross-process-look", "Cross Process", "Yaratici, moda",
     "Yanlis banyo kimyasi: yesil golge, sari parlak alan.",
     [("style.cross_process", {"strength": 78, "shadow_shift": -24,
                               "saturation": 22, "amount": 100}),
      ("tone.contrast", {"amount": 18}),
      ("texture.grain", {"amount": 14, "size": 2.0})]),

    ("washed-90s", "Washed 90s", "90'lar aile albumu",
     "Yikanmis 90'lar rengi: dusuk doygunluk, magenta kayma.",
     [("color.grading", {"midtone_color": [0.56, 0.48, 0.54],
                         "midtone_amount": 26,
                         "shadow_color": [0.48, 0.48, 0.52],
                         "shadow_amount": 20}),
      ("color.saturation", {"amount": -20}),
      ("tone.fade", {"lift": 26, "rolloff": 14, "amount": 100}),
      ("texture.grain", {"amount": 22, "size": 2.8, "colour": True})]),

    ("grainy-diary", "Grainy Diary", "Gunluk, belgesel",
     "Yuksek ISO gunluk hissi: belirgin tane, orta kontrast.",
     [("texture.grain", {"amount": 52, "size": 2.6, "roughness": 62,
                         "colour": True}),
      ("tone.contrast", {"amount": 14}),
      ("color.saturation", {"amount": -12}),
      ("tone.fade", {"lift": 14, "amount": 100})]),
]


# =============================================================== SIYAH-BEYAZ
MONO: list[PresetDef] = [
    ("classic-mono", "Classic Mono", "Her tur fotograf",
     "Klasik siyah-beyaz: dengeli kanal karisimi, orta kontrast.",
     [("color.monochrome", {"amount": 100, "red": 10, "orange": 12,
                            "blue": -14, "green": -6}),
      ("tone.curves", {"rgb": [[0, 0], [0.28, 0.24], [0.72, 0.78], [1, 1]]}),
      ("tone.contrast", {"amount": 22})]),

    ("fine-art-mono", "Fine Art Mono", "Sergi baskisi",
     "Genis ton araligi ve yumusak gecisler; galeri baskisi icin.",
     [("color.monochrome", {"amount": 100, "yellow": 10, "green": 6}),
      ("tone.curves", {"rgb": [[0, 0.02], [0.25, 0.24], [0.75, 0.78],
                               [1, 0.98]]}),
      ("detail.clarity", {"amount": 14, "radius": 90})]),

    ("high-contrast-mono", "High Contrast Mono", "Grafik, mimari",
     "Sert siyah-beyaz ayrim; ara tonlar azalir.",
     [("color.monochrome", {"amount": 100, "red": 12, "blue": -16}),
      ("tone.curves", {"rgb": [[0, 0], [0.3, 0.14], [0.7, 0.88], [1, 1]]}),
      ("detail.clarity", {"amount": 26, "radius": 50})]),

    ("soft-silver", "Soft Silver", "Portre",
     "Yumusak gumus tonu; golgeler acik, parlak alanlar kontrollu.",
     [("color.monochrome", {"amount": 100, "orange": 12, "yellow": 8}),
      ("tone.shadows_highlights", {"shadows": 22, "highlights": -18}),
      ("tone.contrast", {"amount": -6}),
      ("light.diffusion", {"strength": 16, "radius": 45, "lift": 20})]),

    ("matte-mono", "Matte Mono", "Sokak, gunluk",
     "Mat siyah-beyaz: siyahlar kalkik, cagdas gorunum.",
     [("color.monochrome", {"amount": 100}),
      ("tone.fade", {"lift": 32, "rolloff": 12, "amount": 100}),
      ("texture.grain", {"amount": 18, "size": 2.0})]),

    ("deep-noir", "Deep Noir", "Gece, portre, gerilim",
     "Derin siyahlar ve sert isik; film noir karakteri.",
     [("color.monochrome", {"amount": 100, "red": 14, "blue": -20}),
      ("tone.curves", {"rgb": [[0, 0], [0.38, 0.16], [0.78, 0.86], [1, 1]]}),
      ("lens.vignette", {"amount": -42, "midpoint": 0.52, "feather": 0.8}),
      ("texture.grain", {"amount": 26, "size": 2.2})]),

    ("infrared-mono", "Infrared Inspired Mono", "Manzara, bitki ortusu",
     "Kizilotesi *esinli* yorum: yesiller parlar, gokyuzu koyulur. "
     "Gercek kizilotesi veri uretmez; kanal karisimiyla elde edilir.",
     [("color.channel_mixer", {"rr": 60, "rg": 120, "rb": -40,
                               "gr": 40, "gg": 110, "gb": -30,
                               "br": 30, "bg": 90, "bb": -10}),
      ("color.monochrome", {"amount": 100, "green": 40, "yellow": 24,
                            "blue": -34}),
      ("tone.contrast", {"amount": 26}),
      ("light.bloom", {"threshold": 0.7, "radius": 80, "intensity": 30})]),

    ("grainy-reportage", "Grainy Reportage", "Haber, belgesel",
     "Yuksek ISO haber fotografi: belirgin tane, sert kontrast.",
     [("color.monochrome", {"amount": 100, "red": 8}),
      ("texture.grain", {"amount": 62, "size": 2.8, "roughness": 70}),
      ("tone.contrast", {"amount": 28}),
      ("detail.clarity", {"amount": 22, "radius": 55})]),

    ("high-key-mono", "High Key Mono", "Portre, studyo",
     "Aydinlik siyah-beyaz; golgeler minimumda.",
     [("color.monochrome", {"amount": 100}),
      ("tone.exposure", {"stops": 0.4}),
      ("tone.shadows_highlights", {"shadows": 40, "highlights": -20}),
      ("tone.contrast", {"amount": -14})]),

    ("warm-selenium", "Warm Selenium", "Baski, portre",
     "Selenyum tonlamasi: sicak golgeler, serin parlak alanlar.",
     [("color.monochrome", {"amount": 100, "orange": 10}),
      ("color.split_tone", {"shadow_color": [0.44, 0.34, 0.30],
                            "shadow_strength": 32,
                            "highlight_color": [0.86, 0.90, 0.96],
                            "highlight_strength": 24}),
      ("tone.contrast", {"amount": 14})]),
]


# ========================================================== ISIK VE ATMOSFER
LIGHT: list[PresetDef] = [
    # Bu gorunum **isigin kendisi** hakkinda: gunes yonlu parlar,
    # golgeler acilir, parlak alanlar hale yapar. Portre kategorisindeki
    # "Golden Skin" ise ayni saati *tene* gore ele alir.
    ("golden-hour", "Golden Hour", "Gun batimi, manzara ve portre",
     "Altin saatin isigi: yonlu parlama, acilan golge ve parlak "
     "alanlarda hale.",
     [("color.white_balance", {"kelvin": 5300, "tint": 6}),
      ("light.halation", {"threshold": 0.58, "radius": 70,
                          "intensity": 64}),
      ("light.bloom", {"threshold": 0.70, "radius": 130, "intensity": 30}),
      ("tone.shadows_highlights", {"shadows": 30, "highlights": -16}),
      ("color.grading", {"highlight_color": [0.68, 0.55, 0.36],
                         "highlight_amount": 40}),
      ("color.vibrance", {"amount": 16})]),

    ("blue-hour", "Blue Hour", "Alacakaranlik, sehir",
     "Gun batiminden sonraki mavi sessizlik.",
     [("color.white_balance", {"kelvin": 7600, "tint": -6}),
      ("color.grading", {"shadow_color": [0.36, 0.44, 0.64],
                         "shadow_amount": 38,
                         "midtone_color": [0.44, 0.50, 0.62],
                         "midtone_amount": 22}),
      ("tone.shadows_highlights", {"shadows": 20, "highlights": -16})]),

    ("soft-bloom", "Soft Bloom", "Portre, cicek",
     "Parlak alanlardan yayilan yumusak isik.",
     [("light.bloom", {"threshold": 0.6, "radius": 130, "intensity": 58}),
      ("tone.contrast", {"amount": -10}),
      ("color.saturation", {"amount": 6})]),

    # Sinema koleksiyonundaki "Dream Sequence" ile ayni yumusaklik
    # ailesinde. Bu surum kasitli olarak **notr ve olculu**: renk
    # kaymasi yok, bloom hafif. Sinematik surum menekse kaymali ve
    # halation'li, belirgin sekilde gercek disi.
    ("dream-haze", "Dream Haze", "Ruya gibi sahneler",
     "Notr ve olculu sis: diffusion one cikar, renk oldugu gibi kalir.",
     [("tone.shadows_highlights", {"highlights": -24, "shadows": 22}),
      ("light.diffusion", {"strength": 60, "radius": 70, "lift": 20}),
      ("light.bloom", {"threshold": 0.80, "radius": 110, "intensity": 18}),
      ("color.saturation", {"amount": -6}),
      ("tone.fade", {"lift": 12, "rolloff": 10, "amount": 100})]),

    # "Soft Portrait" salt yumusakliktir; bu gorunum **yonludur**:
    # kenarlara dogru dusen isik (vignette) ve serin golge, pencereden
    # gelen tek yonlu isigi taklit eder.
    ("window-light", "Window Light", "Ic mekan portre",
     "Pencereden gelen tek yonlu isik: kenarlara dogru dusen parlaklik, "
     "serin golge, acik ten.",
     [("tone.shadows_highlights", {"shadows": 42, "highlights": -30}),
      ("lens.vignette", {"amount": -34, "midpoint": 0.48, "feather": 0.8}),
      ("color.grading", {"shadow_color": [0.42, 0.47, 0.58],
                         "shadow_amount": 34,
                         "highlight_color": [0.56, 0.55, 0.52],
                         "highlight_amount": 18}),
      ("tone.black_white_point", {"black": 6, "white": 10})]),

    ("amber-leak", "Amber Leak", "Analog his",
     "Kehribar isik sizintisi; kenardan yayilan sicak parlama.",
     [("texture.light_leak", {"intensity": 46, "color": [1.0, 0.58, 0.24],
                              "size": 0.75, "softness": 72}),
      ("tone.fade", {"lift": 14, "amount": 100}),
      ("color.vibrance", {"amount": 12})]),

    ("cool-mist", "Cool Mist", "Sabah sisi",
     "Serin sis: dusuk doygunluk, mavi golgeler, acik tonlar.",
     [("light.diffusion", {"strength": 40, "radius": 85, "lift": 36}),
      ("color.white_balance", {"kelvin": 7200, "tint": -5}),
      ("color.saturation", {"amount": -22}),
      ("tone.fade", {"lift": 20, "amount": 100})]),

    ("backlight-glow", "Backlight Glow", "Arkadan isikli portre",
     "Arkadan gelen isigin sacilmasi ve kontur parlamasi.",
     [("light.bloom", {"threshold": 0.66, "radius": 120, "intensity": 66}),
      ("light.halation", {"threshold": 0.74, "radius": 44, "intensity": 40}),
      ("tone.shadows_highlights", {"shadows": 28, "highlights": -14})]),

    ("sunset-flare", "Sunset Flare", "Gun batimi, lens parlamasi",
     "Gunes parlamasi ve anamorfik cizgi.",
     [("light.anamorphic", {"threshold": 0.8, "length": 380, "thickness": 7,
                            "intensity": 44, "color": [1.0, 0.72, 0.42]}),
      ("light.halation", {"threshold": 0.7, "radius": 46, "intensity": 44}),
      ("color.white_balance", {"kelvin": 5200, "tint": 6}),
      ("tone.fade", {"lift": 12, "amount": 100})]),

    ("ethereal-light", "Ethereal Light", "Soyut, atmosferik",
     "Ruhani, ucucu isik: yuksek bloom, dusuk kontrast, pastel kayma.",
     [("light.bloom", {"threshold": 0.5, "radius": 180, "intensity": 78}),
      ("light.diffusion", {"strength": 34, "radius": 100, "lift": 34}),
      ("color.grading", {"highlight_color": [0.56, 0.52, 0.58],
                         "highlight_amount": 26}),
      ("tone.contrast", {"amount": -18})]),
]


# ============================================================ YARATICI RENK
CREATIVE: list[PresetDef] = [
    ("cyan-orange", "Cyan Orange", "Aksiyon, portre",
     "Klasik tamamlayici renk ayrimi: cyan golge, turuncu ten.",
     [("color.grading", {"shadow_color": [0.34, 0.52, 0.60],
                         "shadow_amount": 42,
                         "highlight_color": [0.66, 0.52, 0.38],
                         "highlight_amount": 38}),
      ("color.vibrance", {"amount": 20}),
      ("tone.contrast", {"amount": 16})]),

    ("purple-dream", "Purple Dream", "Moda, gece",
     "Mor ve lila kayma; ruya gibi bir renk dunyasi.",
     [("color.grading", {"shadow_color": [0.46, 0.38, 0.62],
                         "shadow_amount": 40,
                         "highlight_color": [0.62, 0.50, 0.64],
                         "highlight_amount": 30}),
      ("color.hsl", {"purple_sat": 24, "magenta_sat": 18, "blue_hue": 16}),
      ("light.bloom", {"threshold": 0.66, "radius": 110, "intensity": 34})]),

    ("duotone-ink", "Duotone Ink", "Afis, grafik",
     "Iki renkli baski: lacivert golge, krem parlak alan.",
     [("style.duotone", {"shadow_color": [0.08, 0.12, 0.30],
                         "highlight_color": [0.98, 0.90, 0.68],
                         "contrast": 18, "amount": 100})]),

    ("crimson-shadows", "Crimson Shadows", "Gerilim, gece",
     "Kirmizi golgeler ve koyu atmosfer.",
     [("color.grading", {"shadow_color": [0.62, 0.36, 0.38],
                         "shadow_amount": 40,
                         "highlight_color": [0.54, 0.50, 0.48],
                         "highlight_amount": 18}),
      ("tone.curves", {"rgb": [[0, 0], [0.35, 0.22], [0.75, 0.82], [1, 1]]}),
      ("lens.vignette", {"amount": -30, "midpoint": 0.58})]),

    ("mint-pastel", "Mint Pastel", "Urun, minimal",
     "Nane yesili pastel palet; temiz ve modern.",
     [("color.saturation", {"amount": -34}),
      ("color.hsl", {"green_sat": 24, "aqua_sat": 20, "orange_sat": -30,
                     "red_sat": -26}),
      ("color.grading", {"midtone_color": [0.40, 0.58, 0.52],
                         "midtone_amount": 38,
                         "highlight_color": [0.50, 0.57, 0.54],
                         "highlight_amount": 26}),
      ("tone.fade", {"lift": 24, "rolloff": 10, "amount": 100})]),

    # Manzara kategorisindeki "Misty Hills" ile karistirilmamali:
    # burada kayma **sicak seftali**, orada **soguk sis**. Ayrim renk
    # yonunde, siddette degil.
    ("peach-fade", "Peach Fade", "Portre, yaz",
     "Belirgin seftali kaymasi: parlak alanlar mercan, golgeler sicak "
     "krem. Yaz portrelerinin nostaljik tonu.",
     [("color.grading", {"highlight_color": [0.78, 0.48, 0.40],
                         "highlight_amount": 54,
                         "midtone_color": [0.62, 0.50, 0.46],
                         "midtone_amount": 26,
                         "shadow_color": [0.58, 0.48, 0.44],
                         "shadow_amount": 30}),
      ("color.hsl", {"orange_sat": 22, "orange_lum": 8, "red_sat": 14}),
      ("tone.fade", {"lift": 30, "rolloff": 16, "amount": 100}),
      ("color.saturation", {"amount": -8})]),

    ("electric-blue", "Electric Blue", "Gece, moda",
     "Elektrik mavisi vurgusu ve yuksek doygunluk.",
     [("color.hsl", {"blue_sat": 40, "blue_lum": 8, "aqua_sat": 26,
                     "orange_sat": -14}),
      ("color.grading", {"shadow_color": [0.32, 0.42, 0.70],
                         "shadow_amount": 44}),
      ("tone.contrast", {"amount": 22}),
      ("color.vibrance", {"amount": 18})]),

    # Sinema koleksiyonundaki "Teal & Amber" dengeli ve olculudur.
    # Bu yaratici surum bakiri **cok daha ileri** goturur: parlak alanlar
    # belirgin metalik turuncu, golgeler derin turkuaz.
    ("copper-teal", "Copper Teal", "Yaratici portre",
     "Abartili bakir-turkuaz: metalik sicak parlak alan, derin turkuaz "
     "golge.",
     [("color.grading", {"shadow_color": [0.22, 0.54, 0.60],
                         "shadow_amount": 62,
                         "midtone_color": [0.58, 0.48, 0.40],
                         "midtone_amount": 30,
                         "highlight_color": [0.80, 0.48, 0.22],
                         "highlight_amount": 58}),
      ("film.tone_curve", {"toe": 22, "shoulder": 30, "strength": 12}),
      ("color.vibrance", {"amount": 14})]),

    ("selective-red", "Selective Red", "Vurgu, grafik",
     "Kirmizi disindaki renkleri geri ceker. Renk araligi maskesiyle "
     "calisir; nesne tanima yapmaz.",
     [("color.hsl", {"orange_sat": -70, "yellow_sat": -80, "green_sat": -90,
                     "aqua_sat": -90, "blue_sat": -85, "purple_sat": -60,
                     "red_sat": 30}),
      ("tone.contrast", {"amount": 16})]),

    ("muted-olive", "Muted Olive", "Doga, moda",
     "Sessiz zeytin paleti; dusuk doygunluk, toprak kayma.",
     [("color.hsl", {"green_hue": 16, "green_sat": -26, "yellow_hue": -10,
                     "yellow_sat": -18}),
      ("color.grading", {"midtone_color": [0.50, 0.52, 0.44],
                         "midtone_amount": 28}),
      ("color.saturation", {"amount": -20}),
      ("tone.fade", {"lift": 14, "amount": 100})]),
]


# ============================================================= DOKU VE STIL
TEXTURE: list[PresetDef] = [
    ("paper-print", "Paper Print", "Baski taklidi",
     "Kagida basilmis his: lif dokusu ve hafif sicaklik.",
     [("texture.paper", {"strength": 44, "scale": 5, "fibre": 62,
                         "warmth": 22}),
      ("tone.fade", {"lift": 12, "rolloff": 6, "amount": 100}),
      ("color.saturation", {"amount": -10})]),

    ("fine-grain", "Fine Grain", "Portre, dusuk ISO film",
     "Ince, sik tane; gorunumu bozmadan film hissi verir.",
     [("texture.grain", {"amount": 30, "size": 1.4, "roughness": 34}),
      ("tone.contrast", {"amount": 10})]),

    ("rough-grain", "Rough Grain", "Belgesel, yuksek ISO",
     "Iri ve sert tane; ham ve dogrudan bir his.",
     [("texture.grain", {"amount": 70, "size": 4.2, "roughness": 78,
                         "colour": True}),
      ("tone.contrast", {"amount": 18}),
      ("color.saturation", {"amount": -14})]),

    ("dust-scratches", "Dust & Scratches", "Eski film taramasi",
     "Toz benekleri ve dikey cizikler; arsiv gorunumu.",
     [("texture.dust", {"dust": 52, "scratches": 42, "dust_size": 3.0,
                        "amount": 100}),
      ("texture.grain", {"amount": 24, "size": 2.4}),
      ("tone.fade", {"lift": 16, "amount": 100})]),

    ("soft-focus", "Soft Focus", "Portre, cicek",
     "Yumusak odak: net katman uzerinde bulanik katman.",
     [("light.diffusion", {"strength": 58, "radius": 70, "lift": 26}),
      ("blur.gaussian", {"radius": 14, "amount": 28}),
      ("tone.contrast", {"amount": -8})]),

    ("tilt-shift-miniature", "Tilt Shift Miniature", "Sehir, yuksekten",
     "Minyatur etkisi: dar net serit, guclu doygunluk.",
     [("blur.tilt_shift", {"radius": 60, "position": 0.55, "width": 0.22,
                           "feather": 0.16, "amount": 100}),
      ("color.vibrance", {"amount": 34}),
      ("tone.contrast", {"amount": 20})]),

    ("chromatic-fringe", "Chromatic Fringe", "Yaratici, lo-fi",
     "Kenarlarda renk ayrilmasi; oyuncakli lens hissi.",
     [("lens.chromatic_aberration", {"amount": 55, "edge_only": True}),
      ("lens.vignette", {"amount": -24, "midpoint": 0.6}),
      ("color.vibrance", {"amount": 16})]),

    ("poster-art", "Poster Art", "Afis, grafik",
     "Ton sayisi azaltilir; serigrafi/afis gorunumu.",
     [("style.posterize", {"levels": 6, "softness": 18, "amount": 100}),
      ("color.vibrance", {"amount": 26}),
      ("tone.contrast", {"amount": 22})]),

    ("lo-fi-print", "Lo-Fi Print", "Zine, lo-fi",
     "Dusuk kaliteli baski hissi: sinirli ton, kagit dokusu, tane.",
     [("style.posterize", {"levels": 12, "softness": 34, "amount": 70}),
      ("texture.paper", {"strength": 36, "scale": 4, "warmth": 16}),
      ("texture.grain", {"amount": 34, "size": 2.6}),
      ("color.saturation", {"amount": -16})]),

    ("frosted-blur", "Frosted Blur", "Soyut, arka plan",
     "Buzlu cam etkisi: genel bulaniklik ve isik yayilimi.",
     [("blur.gaussian", {"radius": 20, "amount": 52}),
      ("blur.motion", {"mode": "radial", "strength": 26,
                       "protect_center": 34, "amount": 100}),
      ("light.bloom", {"threshold": 0.66, "radius": 140, "intensity": 32}),
      ("tone.fade", {"lift": 18, "rolloff": 10, "amount": 100})]),
]


CATEGORY_PRESETS: dict[str, list[PresetDef]] = {
    "natural": NATURAL,
    "portrait": PORTRAIT,
    "landscape": LANDSCAPE,
    "street": STREET,
    "analog": ANALOG,
    "mono": MONO,
    "light": LIGHT,
    "creative": CREATIVE,
    "texture": TEXTURE,
}
