"""Tasarim sistemi galerisi - tum kontrolleri tek ekranda cizip PNG verir.

Stil degisikliklerini gercek piksellerde dogrulamak icin. DPI ve pencere
genisligi parametre oldugundan Faz 8'in olcekleme denetimlerinde de
kullanilir.

Kullanim:
    python tools/widget_gallery.py [cikti.png] [--dpi 1.0] [--width 1180]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def build_gallery():  # noqa: ANN201 - Qt tipi ice aktarma sonrasi belli
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QCheckBox, QComboBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
        QLabel, QLineEdit, QListWidget, QProgressBar, QPushButton, QRadioButton,
        QSlider, QSpinBox, QTabWidget, QToolButton, QVBoxLayout, QWidget,
    )

    from luma_atelier.ui.theme.tokens import SPACE

    root = QWidget()
    root.setObjectName("GalleryRoot")
    outer = QVBoxLayout(root)
    outer.setContentsMargins(SPACE.xl, SPACE.xl, SPACE.xl, SPACE.xl)
    outer.setSpacing(SPACE.lg)

    def overline(text: str) -> QLabel:
        lb = QLabel(text.upper())
        lb.setObjectName("Overline")
        return lb

    # --- Tipografi ---
    outer.addWidget(overline("Tipografi"))
    typo = QVBoxLayout()
    typo.setSpacing(SPACE.xs)
    for name, text in [
        ("DisplayTitle", "Luma Atelier"),
        ("SectionTitle", "Sinema Laboratuvari"),
        ("PanelHeading", "Ton ve Renk"),
        ("", "Normal govde metni - fotografin uzerindeki ayarlar"),
        ("Caption", "Yardimci aciklama metni"),
        ("Muted", "Ikincil, sessiz bilgi"),
        ("ValueReadout", "+1.25 stop"),
    ]:
        lb = QLabel(text)
        if name:
            lb.setObjectName(name)
        typo.addWidget(lb)
    outer.addLayout(typo)

    div = QFrame(); div.setObjectName("Divider"); outer.addWidget(div)

    # --- Dugmeler ---
    outer.addWidget(overline("Dugmeler"))
    btns = QHBoxLayout(); btns.setSpacing(SPACE.sm)
    b1 = QPushButton("Birincil eylem"); b1.setObjectName("PrimaryButton")
    b2 = QPushButton("Ikincil")
    b3 = QPushButton("Hayalet"); b3.setObjectName("GhostButton")
    b4 = QPushButton("Sil"); b4.setObjectName("DangerButton")
    b5 = QPushButton("Devre disi"); b5.setEnabled(False)
    b6 = QPushButton("Secili"); b6.setCheckable(True); b6.setChecked(True)
    tb = QToolButton(); tb.setText("Araç"); tb.setCheckable(True); tb.setChecked(True)
    for b in (b1, b2, b3, b4, b5, b6, tb):
        btns.addWidget(b)
    btns.addStretch(1)
    outer.addLayout(btns)

    # --- Girdiler ---
    outer.addWidget(overline("Girdiler"))
    grid = QGridLayout(); grid.setSpacing(SPACE.sm)
    le = QLineEdit(); le.setPlaceholderText("Preset ara...")
    le.setProperty("searchField", True)
    le2 = QLineEdit("Dosya adi oneki")
    sp = QSpinBox(); sp.setRange(0, 100); sp.setValue(92); sp.setSuffix(" %")
    cb = QComboBox(); cb.addItems(["JPEG", "PNG", "WebP", "TIFF 16-bit"])
    grid.addWidget(QLabel("Arama"), 0, 0); grid.addWidget(le, 0, 1)
    grid.addWidget(QLabel("Onek"), 0, 2); grid.addWidget(le2, 0, 3)
    grid.addWidget(QLabel("Kalite"), 1, 0); grid.addWidget(sp, 1, 1)
    grid.addWidget(QLabel("Format"), 1, 2); grid.addWidget(cb, 1, 3)
    outer.addLayout(grid)

    # --- Kaydiricilar ---
    outer.addWidget(overline("Kaydiricilar"))
    for label, lo, hi, val in [("Pozlama", -300, 300, 55),
                               ("Kontrast", -100, 100, -22),
                               ("Doygunluk", -100, 100, 0)]:
        row = QHBoxLayout(); row.setSpacing(SPACE.md)
        name = QLabel(label); name.setMinimumWidth(80)
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(lo, hi); sl.setValue(val)
        ro = QLabel(f"{val/100:+.2f}"); ro.setObjectName("ValueReadout")
        ro.setMinimumWidth(56)
        ro.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(name); row.addWidget(sl, 1); row.addWidget(ro)
        outer.addLayout(row)

    # --- Secim ve durum ---
    outer.addWidget(overline("Secim ve durum"))
    sel = QHBoxLayout(); sel.setSpacing(SPACE.lg)
    c1 = QCheckBox("Alt klasorleri tara"); c1.setChecked(True)
    c2 = QCheckBox("Metadata koru")
    r1 = QRadioButton("Rehber"); r1.setChecked(True)
    r2 = QRadioButton("Gercekten kirp")
    for w in (c1, c2, r1, r2):
        sel.addWidget(w)
    sel.addStretch(1)
    outer.addLayout(sel)

    pb = QProgressBar(); pb.setRange(0, 100); pb.setValue(64)
    outer.addWidget(pb)

    # --- Yuzeyler ---
    outer.addWidget(overline("Yuzeyler"))
    surf = QHBoxLayout(); surf.setSpacing(SPACE.md)

    card = QFrame(); card.setObjectName("PanelCard")
    cl = QVBoxLayout(card); cl.setContentsMargins(SPACE.md, SPACE.md, SPACE.md, SPACE.md)
    ct = QLabel("Yigin karti"); ct.setObjectName("PanelHeading")
    cd = QLabel("Yukseltilmis yuzey, ince kenarlik"); cd.setObjectName("Caption")
    cl.addWidget(ct); cl.addWidget(cd)
    surf.addWidget(card, 1)

    gb = QGroupBox("Film tonu")
    gl = QVBoxLayout(gb)
    gl.addWidget(QLabel("Grup kutusu icerigi"))
    surf.addWidget(gb, 1)

    lw = QListWidget()
    for item in ["Teal & Amber", "Soft Blockbuster", "Desert Epic", "Neon Rain"]:
        lw.addItem(item)
    lw.setCurrentRow(1)
    lw.setMaximumHeight(120)
    surf.addWidget(lw, 1)
    outer.addLayout(surf)

    tabs = QTabWidget()
    for t in ("Duzenleyici", "Sinema", "Disa aktar"):
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.addWidget(QLabel(f"{t} sekmesi icerigi"))
        tabs.addTab(page, t)
    tabs.setCurrentIndex(1)
    tabs.setMaximumHeight(110)
    outer.addWidget(tabs)

    outer.addStretch(1)
    return root


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("output", nargs="?", default="gallery.png")
    ap.add_argument("--dpi", type=float, default=1.0,
                    help="Olcek faktoru (1.0, 1.25, 1.5, 2.0)")
    ap.add_argument("--width", type=int, default=1180)
    ap.add_argument("--height", type=int, default=980)
    args = ap.parse_args()

    os.environ["QT_SCALE_FACTOR"] = str(args.dpi)
    from PySide6.QtWidgets import QApplication

    from luma_atelier.ui.theme.stylesheet import build_stylesheet

    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(build_stylesheet())
    w = build_gallery()
    w.resize(args.width, args.height)
    w.show()
    app.processEvents()
    pm = w.grab()
    ok = pm.save(args.output, "PNG")
    print(f"{args.output} yazildi={ok} ({pm.width()}x{pm.height()}, dpi={args.dpi})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
