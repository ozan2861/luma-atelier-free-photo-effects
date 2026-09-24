"""Tasarim jetonlarindan Qt stil sayfasi (QSS) uretir.

Hicbir renk veya olcu elle yazilmaz; hepsi `tokens` modulunden gelir.
Boylece tema tek noktadan degisir ve arayuzde kacak renk kalmaz.

Adlandirma kurali: ozel gorunum gereken widget'lara `objectName` veya
`property("variant")` verilir, burada ona gore stil tanimlanir.
"""
from __future__ import annotations

from luma_atelier.core.paths import resources_dir
from luma_atelier.ui.theme.tokens import (
    METRICS,
    MOTION,
    PALETTE,
    RADIUS,
    SPACE,
    TYPE,
    rgba,
)


def _asset(name: str) -> str:
    """Ikon dosyasinin QSS'te kullanilabilir yolu.

    Qt stil sayfasi ters bolu karakterini kacis olarak yorumladigi icin
    Windows yolu duz bolu ile yazilir. Gelistirmede depo klasoru,
    paketlenmis surumde `_internal/resources` kullanilir; ikisi de ayni
    `resources_dir()` cagrisindan gelir.
    """
    return (resources_dir() / "icons" / name).as_posix()

# MOTION su an QSS'te kullanilmiyor (Qt stil sayfalari gecis suresi
# desteklemez); animasyonlar widget tarafinda QPropertyAnimation ile
# yapilir ve ayni jeton degerlerini okur.
_ = MOTION


def build_stylesheet(*, high_contrast: bool = False) -> str:
    """Uygulamanin tamami icin QSS dizesi.

    `high_contrast` temel stili **degistirmez**, uzerine bir katman
    bindirir. Boylece varsayilan gorunum tek yerden korunur ve
    secenek kapatilinca hicbir iz kalmaz.
    """
    if high_contrast:
        return _base_stylesheet() + _HIGH_CONTRAST
    return _base_stylesheet()


def _base_stylesheet() -> str:
    """Uygulamanin tamami icin QSS dizesi."""
    p, t, s, r, m = PALETTE, TYPE, SPACE, RADIUS, METRICS

    return f"""
/* ==================================================================
   TEMEL
   ================================================================== */
* {{
    outline: 0;
}}

QWidget {{
    background-color: {p.bg_base};
    color: {p.text_primary};
    font-family: {t.family_text};
    font-size: {t.size_body}px;
    font-weight: {t.weight_regular};
}}

QWidget:disabled {{
    color: {p.text_disabled};
}}

/* Etiketler, onay kutulari ve secenekler kendi zeminlerini cizmez;
   ustunde durduklari yuzeyin rengini alirlar. Bu kural olmadan
   kart/panel icindeki her metin koyu bir kutu gibi gorunur. */
QLabel, QCheckBox, QRadioButton, QGroupBox {{
    background-color: transparent;
}}

QMainWindow, QDialog {{
    background-color: {p.bg_base};
}}

QToolTip {{
    background-color: {p.bg_overlay};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {r.sm}px;
    padding: {s.xs}px {s.sm}px;
    font-size: {t.size_caption}px;
}}

/* ==================================================================
   PANELLER VE YUZEYLER
   ================================================================== */
QFrame#SidePanel, QWidget#SidePanel {{
    background-color: {p.bg_panel};
    border: none;
}}

QFrame#PanelCard, QWidget#PanelCard {{
    background-color: {p.bg_raised};
    border: 1px solid {p.border_subtle};
    border-radius: {r.md}px;
}}

QFrame#Divider {{
    background-color: {p.border_subtle};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}

QFrame#DividerVertical {{
    background-color: {p.border_subtle};
    border: none;
    max-width: 1px;
    min-width: 1px;
}}

QWidget#CanvasHost {{
    background-color: {p.canvas_void};
}}

/* ==================================================================
   TIPOGRAFI SINIFLARI
   ================================================================== */
QLabel#DisplayTitle {{
    font-family: {t.family};
    font-size: {t.size_display}px;
    font-weight: {t.weight_semibold};
    color: {p.text_primary};
}}

QLabel#SectionTitle {{
    font-family: {t.family};
    font-size: {t.size_title}px;
    font-weight: {t.weight_semibold};
    color: {p.text_primary};
}}

QLabel#PanelHeading {{
    font-size: {t.size_heading}px;
    font-weight: {t.weight_semibold};
    color: {p.text_primary};
}}

QLabel#Overline {{
    font-size: {t.size_caption}px;
    font-weight: {t.weight_semibold};
    color: {p.text_muted};
    letter-spacing: {t.tracking_overline}px;
}}

QLabel#Caption, QLabel#Hint {{
    font-size: {t.size_caption}px;
    color: {p.text_secondary};
}}

QLabel#Muted {{
    font-size: {t.size_caption}px;
    color: {p.text_muted};
}}

QLabel#ValueReadout {{
    font-family: {t.family_mono};
    font-size: {t.size_label}px;
    color: {p.text_secondary};
}}

QLabel#DangerText {{ color: {p.danger}; }}
QLabel#WarningText {{ color: {p.warning}; }}
QLabel#SuccessText {{ color: {p.success}; }}

/* ==================================================================
   DUGMELER
   ================================================================== */
QPushButton {{
    background-color: {p.bg_raised};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {r.sm}px;
    padding: 0 {s.md}px;
    min-height: {m.control_height}px;
    font-size: {t.size_label}px;
    font-weight: {t.weight_medium};
}}

QPushButton:hover {{
    background-color: {p.bg_hover};
    border-color: {p.border_strong};
}}

QPushButton:pressed {{
    background-color: {p.bg_active};
}}

QPushButton:disabled {{
    background-color: {p.bg_panel};
    color: {p.text_disabled};
    border-color: {p.border_subtle};
}}

QPushButton:focus {{
    border: {m.focus_ring}px solid {p.accent};
}}

QPushButton#PrimaryButton {{
    background-color: {p.accent};
    color: {p.text_on_accent};
    border: 1px solid {p.accent};
    font-weight: {t.weight_semibold};
}}
QPushButton#PrimaryButton:hover  {{ background-color: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton#PrimaryButton:pressed {{ background-color: {p.accent_pressed}; }}
QPushButton#PrimaryButton:disabled {{
    background-color: {p.accent_soft};
    color: {p.text_disabled};
    border-color: {p.accent_soft};
}}
QPushButton#PrimaryButton:focus {{ border: {m.focus_ring}px solid {p.text_primary}; }}

QPushButton#GhostButton {{
    background-color: transparent;
    border-color: transparent;
    color: {p.text_secondary};
}}
QPushButton#GhostButton:hover {{
    background-color: {p.bg_hover};
    color: {p.text_primary};
}}
QPushButton#GhostButton:pressed {{ background-color: {p.bg_active}; }}
QPushButton#GhostButton:focus {{ border: {m.focus_ring}px solid {p.accent}; }}

QPushButton#DangerButton {{
    background-color: transparent;
    border-color: {p.danger};
    color: {p.danger};
}}
QPushButton#DangerButton:hover {{ background-color: {rgba(p.danger, 0.14)}; }}

QPushButton:checked {{
    background-color: {p.accent_soft};
    border-color: {p.accent_dim};
    color: {p.accent_hover};
}}

QToolButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: {r.sm}px;
    padding: {s.xs}px;
    color: {p.text_secondary};
}}
QToolButton:hover {{ background-color: {p.bg_hover}; color: {p.text_primary}; }}
QToolButton:pressed {{ background-color: {p.bg_active}; }}
QToolButton:checked {{
    background-color: {p.accent_soft};
    color: {p.accent_hover};
    border-color: {p.accent_dim};
}}
QToolButton:focus {{ border: {m.focus_ring}px solid {p.accent}; }}
QToolButton:disabled {{ color: {p.text_disabled}; }}

/* ==================================================================
   GIRDI ALANLARI
   ================================================================== */
QLineEdit, QPlainTextEdit, QTextEdit {{
    background-color: {p.bg_base};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {r.sm}px;
    padding: 0 {s.sm}px;
    min-height: {m.control_height}px;
    selection-background-color: {p.accent_dim};
    selection-color: {p.text_primary};
}}
QLineEdit:hover {{ border-color: {p.border_strong}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: {m.focus_ring}px solid {p.accent};
}}
QLineEdit:disabled {{ background-color: {p.bg_panel}; color: {p.text_disabled}; }}
QLineEdit[searchField="true"] {{
    background-color: {p.bg_raised};
    border-radius: {r.pill}px;
    padding-left: {s.md}px;
}}

QSpinBox, QDoubleSpinBox {{
    background-color: {p.bg_base};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {r.sm}px;
    padding: 0 {s.xs}px 0 {s.sm}px;
    min-height: {m.control_height}px;
    font-family: {t.family_mono};
    font-size: {t.size_label}px;
    selection-background-color: {p.accent_dim};
}}
QSpinBox:focus, QDoubleSpinBox:focus {{ border: {m.focus_ring}px solid {p.accent}; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    background-color: transparent;
    border: none;
    width: 16px;
    margin-right: 2px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    background-color: transparent;
    border: none;
    width: 16px;
    margin-right: 2px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {p.bg_hover};
    border-radius: {r.xs}px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{_asset('chevron-up-muted.png')}"); width: 9px; height: 9px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{_asset('chevron-down-muted.png')}"); width: 9px; height: 9px;
}}
QSpinBox::up-arrow:hover, QDoubleSpinBox::up-arrow:hover {{
    image: url("{_asset('chevron-up.png')}");
}}
QSpinBox::down-arrow:hover, QDoubleSpinBox::down-arrow:hover {{
    image: url("{_asset('chevron-down.png')}");
}}
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled {{
    image: url("{_asset('chevron-up-disabled.png')}");
}}
QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {{
    image: url("{_asset('chevron-down-disabled.png')}");
}}

QComboBox {{
    background-color: {p.bg_raised};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {r.sm}px;
    padding: 0 {s.sm}px;
    min-height: {m.control_height}px;
    font-size: {t.size_label}px;
}}
QComboBox:hover {{ border-color: {p.border_strong}; }}
QComboBox:focus {{ border: {m.focus_ring}px solid {p.accent}; }}
/* drop-down'a konum verilmez: `subcontrol-position` eklendiginde Qt
   oku hem alt kontrolde hem de varsayilan yerde ciziyor ve iki ok
   goruluyordu. */
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: url("{_asset('chevron-down.png')}");
    width: 11px; height: 11px;
}}
QComboBox::down-arrow:disabled {{ image: url("{_asset('chevron-down-disabled.png')}"); }}
QComboBox QAbstractItemView {{
    background-color: {p.bg_overlay};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {r.sm}px;
    padding: {s.xs}px;
    selection-background-color: {p.accent_soft};
    selection-color: {p.accent_hover};
    outline: 0;
}}

/* ==================================================================
   KAYDIRICILAR
   ================================================================== */
/* Qt, QSlider'in kendi yuksekligini alt parcalara dagitir. Widget'a
   sabit yukseklik verilmezse groove tum satiri kaplar ve "kalin kutu"
   gorunumu olusur. Alt parcalarda kenarlik kullanilmaz; kenarlik
   yaricapla birlesince yolun tamami cerceveli gorunuyordu. */
QSlider:horizontal {{
    min-height: {m.slider_handle + 6}px;
    max-height: {m.slider_handle + 6}px;
    background: transparent;
}}
QSlider::groove:horizontal {{
    height: {m.slider_track}px;
    background-color: {p.track_empty};
    border: none;
    border-radius: {m.slider_track // 2}px;
}}
QSlider::sub-page:horizontal {{
    background-color: {p.accent};
    border: none;
    border-radius: {m.slider_track // 2}px;
}}
QSlider::add-page:horizontal {{
    background-color: {p.track_empty};
    border: none;
    border-radius: {m.slider_track // 2}px;
}}
QSlider::handle:horizontal {{
    background-color: {p.text_primary};
    border: none;
    width: {m.slider_handle}px;
    height: {m.slider_handle}px;
    margin: -{(m.slider_handle - m.slider_track) // 2}px 0;
    border-radius: {m.slider_handle // 2}px;
}}
QSlider::handle:horizontal:hover {{ background-color: {p.accent_hover}; }}
QSlider::handle:horizontal:pressed {{ background-color: {p.accent}; }}
QSlider:focus::handle:horizontal {{
    background-color: {p.accent_hover};
    border: {m.focus_ring}px solid {p.text_primary};
}}
QSlider::groove:horizontal:disabled {{ background-color: {p.bg_panel}; }}
QSlider::sub-page:horizontal:disabled {{ background-color: {p.border}; }}
QSlider::handle:horizontal:disabled {{ background-color: {p.text_disabled}; }}

/* ==================================================================
   ONAY KUTULARI VE SECENEKLER
   ================================================================== */
QCheckBox, QRadioButton {{
    spacing: {s.sm}px;
    color: {p.text_secondary};
    font-size: {t.size_label}px;
    min-height: {m.control_height_sm}px;
}}
QCheckBox:hover, QRadioButton:hover {{ color: {p.text_primary}; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px; height: 15px;
    background-color: {p.bg_base};
    border: 1px solid {p.border_strong};
}}
QCheckBox::indicator {{ border-radius: {r.xs}px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {p.accent}; }}
QCheckBox::indicator:checked {{
    background-color: {p.accent};
    border-color: {p.accent};
    image: url("{_asset('check.png')}");
}}
QCheckBox::indicator:checked:disabled {{
    background-color: {p.border};
    border-color: {p.border};
    image: url("{_asset('check-disabled.png')}");
}}
QRadioButton::indicator:checked {{
    background-color: {p.bg_base};
    border: 4px solid {p.accent};
}}
QCheckBox:focus, QRadioButton:focus {{ color: {p.text_primary}; }}

/* ==================================================================
   LISTELER, AGACLAR, TABLOLAR
   ================================================================== */
QListView, QTreeView, QTableView, QListWidget, QTreeWidget {{
    background-color: {p.bg_panel};
    alternate-background-color: {p.bg_raised};
    color: {p.text_primary};
    border: 1px solid {p.border_subtle};
    border-radius: {r.sm}px;
    outline: 0;
    selection-background-color: {p.accent_soft};
    selection-color: {p.accent_hover};
}}
QListView::item, QTreeView::item, QListWidget::item {{
    padding: {s.xs}px {s.sm}px;
    border-radius: {r.xs}px;
    min-height: {m.control_height_sm}px;
}}
QListView::item:hover, QTreeView::item:hover, QListWidget::item:hover {{
    background-color: {p.bg_hover};
}}
QListView::item:selected, QTreeView::item:selected, QListWidget::item:selected {{
    background-color: {p.accent_soft};
    color: {p.accent_hover};
}}
QHeaderView::section {{
    background-color: {p.bg_raised};
    color: {p.text_muted};
    border: none;
    border-bottom: 1px solid {p.border_subtle};
    padding: {s.xs}px {s.sm}px;
    font-size: {t.size_caption}px;
    font-weight: {t.weight_semibold};
}}

/* ==================================================================
   KAYDIRMA CUBUKLARI
   ================================================================== */
QScrollBar:vertical {{
    background: transparent;
    width: 11px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: {p.border};
    border-radius: 5px;
    min-height: 32px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background-color: {p.border_strong}; }}
QScrollBar::handle:vertical:pressed {{ background-color: {p.accent_dim}; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 11px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background-color: {p.border};
    border-radius: 5px;
    min-width: 32px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{ background-color: {p.border_strong}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; border: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ background-color: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background-color: transparent; }}

/* ==================================================================
   SEKMELER
   ================================================================== */
QTabWidget::pane {{
    border: 1px solid {p.border_subtle};
    border-radius: {r.md}px;
    background-color: {p.bg_panel};
    top: -1px;
}}
QTabBar::tab {{
    background-color: transparent;
    color: {p.text_muted};
    border: none;
    border-bottom: 2px solid transparent;
    padding: {s.sm}px {s.md}px;
    margin-right: {s.xs}px;
    font-size: {t.size_label}px;
    font-weight: {t.weight_medium};
}}
QTabBar::tab:hover {{ color: {p.text_primary}; }}
QTabBar::tab:selected {{
    color: {p.accent_hover};
    border-bottom: 2px solid {p.accent};
}}
QTabBar:focus {{ border: none; }}

/* ==================================================================
   AYIRICI (SPLITTER)
   ================================================================== */
QSplitter::handle {{ background-color: {p.border_subtle}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QSplitter::handle:hover {{ background-color: {p.accent_dim}; }}

/* ==================================================================
   ILERLEME
   ================================================================== */
QProgressBar {{
    background-color: {p.bg_base};
    border: none;
    border-radius: 3px;
    min-height: 6px;
    max-height: 6px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {p.accent};
    border-radius: 3px;
}}
QProgressBar[variant="thick"] {{ min-height: 10px; max-height: 10px; border-radius: 5px; }}
QProgressBar[variant="thick"]::chunk {{ border-radius: 5px; }}

/* ==================================================================
   MENU
   ================================================================== */
/* Menu cubugu gezinti seridinin icinde durdugu icin kendi zeminini
   cizmez; aksi halde seridin ustunde koyu bir blok gorunuyordu. */
QMenuBar {{
    background: transparent;
    color: {p.text_secondary};
    border: none;
    padding: 0;
    font-size: {t.size_label}px;
}}
QMenuBar::item {{
    padding: {s.sm}px {s.md}px;
    margin: 0 1px;
    background: transparent;
    border-radius: {r.xs}px;
    color: {p.text_muted};
}}
QMenuBar::item:selected {{ background-color: {p.bg_hover}; color: {p.text_primary}; }}
QMenuBar::item:pressed {{ background-color: {p.bg_active}; color: {p.text_primary}; }}
QMenu {{
    background-color: {p.bg_overlay};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {r.md}px;
    padding: {s.xs}px;
}}
QMenu::item {{
    padding: {s.sm}px {s.xl}px {s.sm}px {s.md}px;
    border-radius: {r.xs}px;
    font-size: {t.size_label}px;
}}
QMenu::item:selected {{ background-color: {p.accent_soft}; color: {p.accent_hover}; }}
QMenu::item:disabled {{ color: {p.text_disabled}; }}
QMenu::separator {{ height: 1px; background-color: {p.border_subtle}; margin: {s.xs}px {s.sm}px; }}

/* ==================================================================
   DURUM CUBUGU
   ================================================================== */
QStatusBar {{
    background-color: {p.bg_panel};
    color: {p.text_muted};
    border-top: 1px solid {p.border_subtle};
    font-size: {t.size_caption}px;
    min-height: {m.statusbar_height}px;
}}
QStatusBar::item {{ border: none; }}

/* ==================================================================
   GRUP KUTUSU
   ================================================================== */
/* Baslik cerceve cizgisinin uzerinde durur; kesik gorunmemesi icin
   altindaki yuzeyin rengiyle doldurulur. Yuzey farkliysa
   `surface` ozelligi ile bildirilir. */
QGroupBox {{
    background-color: transparent;
    border: 1px solid {p.border_subtle};
    border-radius: {r.md}px;
    margin-top: {s.md}px;
    padding: {s.lg}px {s.md}px {s.md}px {s.md}px;
    font-size: {t.size_caption}px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: {s.md}px;
    top: {s.xs}px;
    padding: 0 {s.sm}px;
    background-color: {p.bg_base};
    color: {p.text_muted};
    font-weight: {t.weight_semibold};
    letter-spacing: {t.tracking_overline}px;
}}
QGroupBox[surface="panel"]::title {{ background-color: {p.bg_panel}; }}
QGroupBox[surface="raised"]::title {{ background-color: {p.bg_raised}; }}
"""
