"""Kucuk resim onbellekleri sinirsiz buyumemeli.

Iki ayri onbellek var ve ikisi de sinirsizdi:

* **Bellek**: uretilen her QPixmap sozlukte tutuluyordu. 4000
  fotograflik bir klasorde gezinmek sureci olculen **1094 MB**
  buyutuyordu ve bu bellek hic geri verilmiyordu.
* **Disk**: `prune_cache()` yazilmisti ama **hicbir yerden
  cagrilmiyordu**; Ayarlar'daki "onbellek siniri" degeri hicbir sey
  yapmiyordu.

Testler kullanici acisindan gozlemlenebilir sonucu olcer: cok sayida
kucuk resim gezildikten sonra bellekteki toplam sinirin altinda kalir
ve en son bakilanlar hala hazirdir; disk onbellegi de sinira iner.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from luma_atelier.services.thumbnails import (
    MEMORY_CACHE_BYTES,
    ThumbnailService,
)

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def service(qapp: QApplication) -> ThumbnailService:
    svc = ThumbnailService()
    yield svc
    svc.clear_memory_cache()


def _thumb() -> QImage:
    image = QImage(320, 213, QImage.Format.Format_RGB888)
    image.fill(0x808080)
    return image


class TestMemoryCacheIsBounded:
    def test_many_thumbnails_stay_under_the_limit(
        self, service: ThumbnailService,
    ) -> None:
        image = _thumb()
        for i in range(4000):
            service._on_ready(f"foto-{i}.jpg", image)

        assert service.memory_bytes() <= MEMORY_CACHE_BYTES * 1.1, (
            f"bellek siniri asildi: {service.memory_bytes() / 1e6:.0f} MB"
        )
        assert len(service._memory) < 4000, "hicbir kayit birakilmamis"

    def test_recently_seen_thumbnails_are_kept(
        self, service: ThumbnailService,
    ) -> None:
        """Sinir, kullanicinin **su an baktigi** resmi atmamali."""
        image = _thumb()
        for i in range(4000):
            service._on_ready(f"foto-{i}.jpg", image)

        assert service.cached("foto-3999.jpg") is not None
        assert service.cached("foto-0.jpg") is None

    def test_touching_an_entry_protects_it(
        self, service: ThumbnailService,
    ) -> None:
        """LRU: yeniden bakilan kayit siranin sonuna gitmeli."""
        image = _thumb()
        service._on_ready("korunacak.jpg", image)
        for i in range(200):
            service._on_ready(f"dolgu-{i}.jpg", image)
            service.cached("korunacak.jpg")      # kullanilmaya devam
        for i in range(200, 400):
            service._on_ready(f"dolgu-{i}.jpg", image)
            service.cached("korunacak.jpg")

        assert service.cached("korunacak.jpg") is not None

    def test_replacing_an_entry_does_not_double_count(
        self, service: ThumbnailService,
    ) -> None:
        image = _thumb()
        service._on_ready("ayni.jpg", image)
        first = service.memory_bytes()
        for _ in range(10):
            service._on_ready("ayni.jpg", image)
        assert service.memory_bytes() == first


class TestDiskCacheIsPruned:
    def test_prune_brings_the_folder_under_the_limit(
        self, service: ThumbnailService, tmp_path: Path,
    ) -> None:
        root = tmp_path / "thumbs"
        (root / "ab").mkdir(parents=True)
        service._cache_root = root
        blob = b"x" * 100_000
        for i in range(40):
            (root / "ab" / f"{i:04d}.png").write_bytes(blob)
        total_before = service.cache_size_bytes()
        assert total_before > 3_000_000

        limit = 1_000_000
        freed = service.prune_cache(limit)

        assert freed > 0
        assert service.cache_size_bytes() <= limit

    def test_prune_uses_the_configured_limit(
        self, service: ThumbnailService, tmp_path: Path,
    ) -> None:
        """Ayarlardan gelen sinir gercekten uygulanmali."""
        root = tmp_path / "thumbs"
        (root / "cd").mkdir(parents=True)
        service._cache_root = root
        for i in range(40):
            (root / "cd" / f"{i:04d}.png").write_bytes(b"y" * 600_000)

        service.set_cache_limit(16 * 1024 * 1024)
        service.prune_cache()

        assert service.cache_size_bytes() <= service.cache_limit()
