"""Tasarim jetonlari - renk, tipografi, bosluk ve yaricap.

Yon: profesyonel fotograf studyosu. Sakin grafit zeminler, birbirinden
ayirt edilebilir panel katmanlari, ince ayiricilar ve *kontrollu* bakir
vurgu. Yildiz fotograftir; arayuz geri cekilir.

Renkler noktrdur (renk yanliligi yok) ki tuvaldeki fotografin renk
algisini bozmasin. Tek doygun renk bakir vurgudur ve yalnizca etkin
durum, odak ve secim icin kullanilir.

Tum QSS bu jetonlardan uretilir; hicbir yerde elle renk kodu yazilmaz.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Palette:
    """Uygulamanin tum renkleri. Hex, #RRGGBB."""

    # --- Zeminler: en arkadan en one dogru katmanlar ---
    canvas_void: str = "#0B0C0D"      # tuval arkasi, en koyu
    bg_base: str = "#131517"          # pencere zemini
    bg_panel: str = "#191C1F"         # yan paneller
    bg_raised: str = "#202428"        # kartlar, girdi alanlari
    bg_overlay: str = "#272C31"       # menu, ipucu, acilir pencere
    bg_hover: str = "#2E343A"
    bg_active: str = "#383F46"

    # --- Ayiricilar ve kenarliklar ---
    border_subtle: str = "#24282C"    # panel ici ince ayirici
    border: str = "#31373D"           # normal kenarlik
    border_strong: str = "#434A52"    # vurgulu kenarlik

    # --- Metin ---
    text_primary: str = "#E8EAEC"
    text_secondary: str = "#A5ADB5"
    text_muted: str = "#6F787F"
    text_disabled: str = "#4B5258"
    text_on_accent: str = "#140E07"

    # --- Bakir vurgu (tek doygun renk) ---
    accent: str = "#C98A4B"
    accent_hover: str = "#DB9A58"
    accent_pressed: str = "#B0763C"
    accent_soft: str = "#3A2C1C"      # secili satir zemini
    accent_dim: str = "#7A5630"

    # --- Durum renkleri ---
    success: str = "#6FA86B"
    warning: str = "#D0A24A"
    danger: str = "#C4635B"
    info: str = "#6B90B8"

    # --- Histogram kanallari (tuvalde okunakli, cig degil) ---
    hist_red: str = "#D0605E"
    hist_green: str = "#6DB06A"
    hist_blue: str = "#5F8FCB"
    hist_luma: str = "#B9C0C6"

    # --- Kontrol parcalari ---
    # Kaydiricinin bos yolu. bg_base panel zemininden (bg_panel) neredeyse
    # ayirt edilemiyordu ve kullanici degerin nerede oldugunu goremiyordu;
    # bu yuzden ayri, belirgin bir ton tanimli.
    track_empty: str = "#333A41"
    track_empty_disabled: str = "#23272B"

    # --- Tuval yardimcilari ---
    grid_line: str = "#FFFFFF"        # rehber cizgileri (dusuk opaklikla)
    crop_shade: str = "#0B0C0D"       # kirpma disi karartma
    mask_overlay: str = "#C0392B"     # maske gorunumu


@dataclass(frozen=True)
class Typography:
    """Tipografi olcegi.

    Windows'ta Segoe UI Variable / Segoe UI her kurulumda bulunur, iyi
    hinting'e sahiptir ve lisans sorunu yaratmaz. Sayisal alanlarda
    tabular rakam icin Consolas kullanilir (slider degerleri titremesin).
    """

    family: str = '"Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif'
    family_text: str = '"Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif'
    family_mono: str = '"Cascadia Mono", Consolas, "Courier New", monospace'

    size_display: int = 26   # baslangic ekrani basligi
    size_title: int = 17     # bolum basligi
    size_heading: int = 14   # panel basligi
    size_body: int = 13      # normal metin
    size_label: int = 12     # kontrol etiketi
    size_caption: int = 11   # yardimci metin
    size_micro: int = 10     # rozet, sayac

    weight_regular: int = 400
    weight_medium: int = 500
    weight_semibold: int = 600

    # Buyuk harfli bolum basliklarinda harf araligi (px)
    tracking_overline: float = 0.8


@dataclass(frozen=True)
class Spacing:
    """4 px tabanli bosluk olcegi.

    Ayni degeri her yerde kullanmak yerine ritim kurulur: panel ici
    yogun (8), gruplar arasi ferah (20), bolumler arasi belirgin (32).
    """

    xxs: int = 2
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 20
    xxl: int = 28
    xxxl: int = 40

    panel_padding: int = 16
    group_gap: int = 20
    section_gap: int = 32
    row_gap: int = 10


@dataclass(frozen=True)
class Radius:
    none: int = 0
    xs: int = 3
    sm: int = 5
    md: int = 8
    lg: int = 12
    xl: int = 16
    pill: int = 999


@dataclass(frozen=True)
class Metrics:
    """Sabit olcuier. 1366x768'de de sigmasi icin olculu tutuldu."""

    titlebar_height: int = 44
    nav_height: int = 48
    statusbar_height: int = 28
    left_panel_width: int = 300
    #: Olculen gercek alt sinir: gorunum tarayicisinin filtre satiri ve
    #: "Yigina ekle" / "Kaydet" dugmeleri 284 px istiyor. Daha kucuk bir
    #: deger vermek `setMinimumWidth` ile dogal alt siniri ezer ve panel
    #: tasardi; kesilen dugme metni islev kaybidir.
    left_panel_min: int = 288
    right_panel_width: int = 336
    right_panel_min: int = 276
    filmstrip_height: int = 104
    control_height: int = 30
    control_height_sm: int = 24
    slider_track: int = 4
    slider_handle: int = 14
    icon_sm: int = 14
    icon_md: int = 18
    icon_lg: int = 22
    thumb_size: int = 132
    preset_card_width: int = 148
    focus_ring: int = 2

    # Pencere
    #: Olculen gercek alt sinir: gezinti seridi kompakt kipte bile
    #: menu cubugu + 6 sekme + eylemler icin 1256 px istiyor. 1100 px
    #: ilan etmek serit tasmasi demekti; 1280x720 hem gercek degeri
    #: karsiliyor hem yaygin bir ekran tabani.
    window_min_width: int = 1280
    window_min_height: int = 720
    window_default_width: int = 1520
    window_default_height: int = 940


@dataclass(frozen=True)
class Motion:
    """Hareket suresi (ms).

    Kisa ve amacli. Surekli donen/nefes alan animasyon yok; hareket
    yalnizca durum degisimini aciklar.
    """

    instant: int = 0
    fast: int = 110
    normal: int = 180
    slow: int = 260


PALETTE: Final[Palette] = Palette()
TYPE: Final[Typography] = Typography()
SPACE: Final[Spacing] = Spacing()
RADIUS: Final[Radius] = Radius()
METRICS: Final[Metrics] = Metrics()
MOTION: Final[Motion] = Motion()


def rgba(hex_color: str, alpha: float) -> str:
    """#RRGGBB + opaklik -> QSS rgba() dizesi."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha:.3f})"


def mix(a: str, b: str, t: float) -> str:
    """Iki hex rengi dogrusal karistirir (t=0 -> a, t=1 -> b)."""
    ah, bh = a.lstrip("#"), b.lstrip("#")
    out = []
    for i in (0, 2, 4):
        av, bv = int(ah[i:i + 2], 16), int(bh[i:i + 2], 16)
        out.append(round(av + (bv - av) * max(0.0, min(1.0, t))))
    return "#" + "".join(f"{v:02X}" for v in out)
