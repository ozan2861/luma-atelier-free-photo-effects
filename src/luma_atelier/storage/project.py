"""`.luma` proje paketi: kaydetme, acma, kaynak yeniden bulma, kurtarma.

Bicim
-----
`.luma` bir **ZIP** paketidir:

    manifest.json      surum, uygulama surumu, olusturma zamani
    project.json       kaynak bagi, tarif, maskeler, geometri, seed
    preview.jpg        kucuk onizleme (kitaplikta ve acma ekraninda)
    sources/           yalnizca *tasinabilir* projede: kaynak kopyalari

Neden ZIP: tek dosya olarak tasinir, icerigi insan tarafindan
incelenebilir, kismi okuma yapilabilir (onizleme icin tum dosyayi
acmaya gerek yok) ve standart araclarla acilir.

Guvenlik
--------
* Proje dosyasi yalnizca **veri** okur; kod calistirilmaz.
* ZIP icindeki yollar dogrulanir (zip-slip saldirisina karsi).
* Bilinmeyen efektler saklanir, silinmez.
* Kaydetme atomiktir: once gecici dosya, sonra tasima. Kesinti eski
  saglam kaydi bozmaz.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from luma_atelier.core.branding import (
    APP_NAME,
    APP_VERSION,
    PROJECT_EXTENSION,
    PROJECT_FORMAT_VERSION,
)
from luma_atelier.imaging.recipe import Recipe, RecipeError

log = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"
PROJECT_NAME = "project.json"
PREVIEW_NAME = "preview.jpg"
SOURCES_DIR = "sources"

#: Dosya secici suzgeci
PROJECT_FILTER = (
    f"{APP_NAME} projesi (*{PROJECT_EXTENSION});;Tüm dosyalar (*)"
)

#: Onizleme uzun kenari
PREVIEW_LONG_EDGE = 640
#: Proje dosyasi ust siniri (kotu niyetli dosyalara karsi)
MAX_PROJECT_BYTES = 2 * 1024 * 1024 * 1024
MAX_PROJECT_JSON_BYTES = 8 * 1024 * 1024
MAX_PREVIEW_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 256
MAX_EMBEDDED_SOURCE_BYTES = MAX_PROJECT_BYTES


class ProjectError(Exception):
    """Proje okunamadi veya yazilamadi. Mesaj Turkce ve kullaniciya gosterilir."""


@dataclass
class SourceRef:
    """Projenin bagli oldugu kaynak fotograf."""

    path: Path
    sha256: str = ""
    width: int = 0
    height: int = 0
    #: Tasinabilir projede paket icindeki dosya adi
    embedded_name: str = ""

    @property
    def is_embedded(self) -> bool:
        return bool(self.embedded_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "name": self.path.name,
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
            "embedded": self.embedded_name,
        }

    @staticmethod
    def from_dict(data: Any) -> SourceRef:
        if not isinstance(data, dict):
            raise ProjectError("Kaynak bilgisi okunamadı")
        raw = str(data.get("path", ""))
        if not raw:
            raise ProjectError("Projede kaynak fotoğraf yolu yok")
        return SourceRef(
            path=Path(raw),
            sha256=str(data.get("sha256", "")),
            width=int(data.get("width", 0) or 0),
            height=int(data.get("height", 0) or 0),
            embedded_name=str(data.get("embedded", "")),
        )


@dataclass
class Project:
    """Acik bir proje."""

    source: SourceRef
    recipe: Recipe
    version: int = PROJECT_FORMAT_VERSION
    app_version: str = APP_VERSION
    created: float = field(default_factory=time.time)
    modified: float = field(default_factory=time.time)
    path: Path | None = None
    portable: bool = False
    #: Paket icinden cikarilan kaynak (tasinabilir projede)
    extracted_source: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "app_version": self.app_version,
            "created": self.created,
            "modified": self.modified,
            "portable": self.portable,
            "source": self.source.to_dict(),
            "recipe": self.recipe.to_dict(),
        }


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _preview_bytes(image: np.ndarray) -> bytes:
    """Kucuk onizlemeyi JPEG bayt dizisi olarak uretir."""
    import cv2

    from luma_atelier.imaging import pixels as px

    work = np.clip(px.ensure_working(image)[..., :3], 0.0, 1.0)
    h, w = work.shape[:2]
    scale = min(1.0, PREVIEW_LONG_EDGE / max(h, w))
    if scale < 1.0:
        work = cv2.resize(work, (max(1, int(w * scale)), max(1, int(h * scale))),
                          interpolation=cv2.INTER_AREA)
    bgr = cv2.cvtColor(px.to_uint8(work), cv2.COLOR_RGB2BGR)
    ok, buffer = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    return buffer.tobytes() if ok else b""


def save_project(path: str | Path, source: Path, recipe: Recipe,
                 preview: np.ndarray | None = None, *,
                 portable: bool = False,
                 existing: Project | None = None) -> Project:
    """Projeyi `.luma` paketi olarak yazar.

    Atomik: once ayni klasorde gecici dosyaya yazilir, basarili biterse
    nihai ada tasinir. Kesinti eski saglam kaydi bozmaz.

    Args:
        portable: True ise kaynak fotografin kopyasi pakete gomulur.
    """
    target = Path(path)
    if target.suffix.lower() != PROJECT_EXTENSION:
        target = target.with_suffix(PROJECT_EXTENSION)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ProjectError(
            f"Klasör olusturulamadi: {target.parent} ({exc.strerror or exc})"
        ) from exc

    source = Path(source)
    ref = SourceRef(
        path=source,
        sha256=file_sha256(source),
        width=int(preview.shape[1]) if preview is not None else 0,
        height=int(preview.shape[0]) if preview is not None else 0,
    )
    if portable and source.exists():
        ref.embedded_name = f"{SOURCES_DIR}/{source.name}"

    now = time.time()
    project = Project(
        source=ref, recipe=recipe, path=target, portable=portable,
        created=existing.created if existing else now, modified=now,
    )

    manifest = {
        "format": "luma-project",
        "version": PROJECT_FORMAT_VERSION,
        "application": APP_NAME,
        "app_version": APP_VERSION,
        "created": project.created,
        "modified": project.modified,
        "portable": portable,
    }

    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.stem}-", suffix=".part", dir=str(target.parent)
    )
    os.close(tmp_fd)
    tmp_path = Path(tmp_name)

    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(MANIFEST_NAME,
                        json.dumps(manifest, ensure_ascii=False, indent=2))
            zf.writestr(PROJECT_NAME,
                        json.dumps(project.to_dict(), ensure_ascii=False,
                                   indent=2))
            if preview is not None:
                data = _preview_bytes(preview)
                if data:
                    zf.writestr(PREVIEW_NAME, data)
            if portable:
                if not source.exists():
                    raise ProjectError(
                        f"Taşınabilir proje için kaynak gerekli ama bulunamadı: "
                        f"{source.name}"
                    )
                zf.write(source, ref.embedded_name)
        os.replace(tmp_path, target)
    except ProjectError:
        tmp_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        if getattr(exc, "errno", None) == 28:
            raise ProjectError("Diskte yeterli yer yok.") from exc
        raise ProjectError(
            f"Proje yazilamadi: {target.name} ({exc.strerror or exc})"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        tmp_path.unlink(missing_ok=True)
        raise ProjectError(f"Proje yazilamadi: {target.name} ({exc})") from exc

    log.info("Proje kaydedildi: %s (tasinabilir=%s)", target, portable)
    return project


def estimate_portable_size(source: Path) -> int:
    """Tasinabilir projenin yaklasik boyutu (bayt).

    Kullaniciya "ne kadar yer kaplayacak" diye gostermek icin.
    """
    try:
        return source.stat().st_size
    except OSError:
        return 0


def project_preview(path: str | Path) -> bytes | None:
    """Paketten yalnizca onizlemeyi okur (tum dosyayi acmadan)."""
    try:
        with zipfile.ZipFile(Path(path)) as zf:
            matches = [info for info in zf.infolist()
                       if info.filename == PREVIEW_NAME]
            if len(matches) == 1 and matches[0].file_size <= MAX_PREVIEW_BYTES:
                return zf.read(matches[0])
    except (OSError, RuntimeError, zipfile.BadZipFile):
        return None
    return None


def _safe_member(name: str) -> bool:
    """ZIP icindeki yol guvenli mi? (zip-slip korumasi)"""
    if name.startswith(("/", "\\")) or ".." in Path(name).parts:
        return False
    try:
        Path(name)
    except (ValueError, OSError):
        return False
    return True


def load_project(path: str | Path, *,
                 extract_dir: Path | None = None) -> Project:
    """`.luma` paketini okur.

    Tasinabilir projede gomulu kaynak `extract_dir` altina cikarilir.

    Raises:
        ProjectError: dosya yok, bozuk, surum desteklenmiyor veya
            icerik gecersiz.
    """
    p = Path(path)
    if not p.exists():
        raise ProjectError(f"Proje dosyası bulunamadı: {p.name}")
    try:
        size = p.stat().st_size
    except OSError as exc:
        raise ProjectError(f"Proje okunamadı: {p.name}") from exc
    if size == 0:
        raise ProjectError(f"Proje dosyası boş: {p.name}")
    if size > MAX_PROJECT_BYTES:
        raise ProjectError(f"Proje dosyası çok büyük: {p.name}")

    try:
        with zipfile.ZipFile(p) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ARCHIVE_MEMBERS:
                raise ProjectError(f"{p.name}: paket cok fazla dosya iceriyor.")
            project_infos = [info for info in infos
                             if info.filename == PROJECT_NAME]
            if not project_infos:
                raise ProjectError(
                    f"{p.name}: geçerli bir Luma projesi değil "
                    "(project.json bulunamadı)."
                )
            if len(project_infos) != 1:
                raise ProjectError(f"{p.name}: birden fazla proje verisi var.")
            project_info = project_infos[0]
            if project_info.file_size > MAX_PROJECT_JSON_BYTES:
                raise ProjectError(f"{p.name}: proje verisi cok buyuk.")
            raw = json.loads(zf.read(project_info).decode("utf-8"))
            if not isinstance(raw, dict):
                raise ProjectError(f"{p.name}: proje verisi nesne olmali.")

            version = raw.get("version", PROJECT_FORMAT_VERSION)
            if not isinstance(version, int):
                raise ProjectError("Proje surumu sayi olmali")
            if version > PROJECT_FORMAT_VERSION:
                raise ProjectError(
                    f"Bu proje daha yeni bir surumle olusturulmus "
                    f"(v{version}, bu surum v{PROJECT_FORMAT_VERSION}). "
                    "Uygulamayı guncelleyin."
                )

            source = SourceRef.from_dict(raw.get("source"))
            try:
                recipe = Recipe.from_dict(raw.get("recipe", {}))
            except RecipeError as exc:
                raise ProjectError(f"{p.name}: tarif okunamadı ({exc})") from exc

            extracted: Path | None = None
            if source.embedded_name:
                if not _safe_member(source.embedded_name):
                    raise ProjectError(
                        f"{p.name}: paket içinde guvensiz dosya yolu."
                    )
                embedded_infos = [info for info in infos
                                  if info.filename == source.embedded_name]
                if len(embedded_infos) > 1:
                    raise ProjectError(
                        f"{p.name}: gomulu kaynak birden fazla kez tanimli."
                    )
                if embedded_infos:
                    embedded_info = embedded_infos[0]
                    if embedded_info.file_size > MAX_EMBEDDED_SOURCE_BYTES:
                        raise ProjectError(
                            f"{p.name}: gomulu kaynak cok buyuk."
                        )
                    folder = extract_dir or Path(
                        tempfile.mkdtemp(prefix="luma_project_")
                    )
                    folder.mkdir(parents=True, exist_ok=True)
                    extracted = folder / Path(source.embedded_name).name
                    with zf.open(embedded_info) as src, \
                            extracted.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                else:
                    log.warning("Taşınabilir proje ama gömülü kaynak yok: %s",
                                source.embedded_name)

    except zipfile.BadZipFile as exc:
        raise ProjectError(f"{p.name}: dosya bozuk veya Luma projesi değil.") \
            from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProjectError(f"{p.name}: proje verisi okunamadı ({exc}).") from exc
    except ProjectError:
        raise
    except OSError as exc:
        raise ProjectError(f"Proje okunamadı: {p.name} ({exc})") from exc

    return Project(
        source=source, recipe=recipe, version=version,
        app_version=str(raw.get("app_version", "")),
        created=float(raw.get("created", 0.0) or 0.0),
        modified=float(raw.get("modified", 0.0) or 0.0),
        path=p, portable=bool(raw.get("portable", False)),
        extracted_source=extracted,
    )


def resolve_source(project: Project, *,
                   search_dirs: list[Path] | None = None) -> tuple[Path | None, str]:
    """Projenin kaynak fotografini bulur.

    Returns:
        (yol, durum). Durum "ok", "embedded", "relocated", "missing"
        veya "changed" olabilir. "changed" dosya bulundu ama icerigi
        kayittakinden farkli demektir - kullaniciya bildirilir.
    """
    if project.extracted_source is not None and project.extracted_source.exists():
        return project.extracted_source, "embedded"

    original = project.source.path
    if original.exists():
        if project.source.sha256:
            current = file_sha256(original)
            if current and current != project.source.sha256:
                return original, "changed"
        return original, "ok"

    # Ayni adi projenin yaninda ve verilen klasorlerde ara
    candidates: list[Path] = []
    if project.path is not None:
        candidates.append(project.path.parent / original.name)
    for folder in search_dirs or []:
        candidates.append(Path(folder) / original.name)

    for candidate in candidates:
        if candidate.exists():
            if project.source.sha256:
                if file_sha256(candidate) == project.source.sha256:
                    return candidate, "relocated"
                continue
            return candidate, "relocated"

    return None, "missing"


# ============================================================ OTOMATIK KURTARMA
AUTOSAVE_SUFFIX = ".autosave.luma"


def autosave_path(source: Path) -> Path:
    """Bir fotograf icin otomatik kurtarma dosyasinin yolu."""
    from luma_atelier.core.paths import autosave_dir

    digest = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:16]
    return autosave_dir() / f"{source.stem}-{digest}{AUTOSAVE_SUFFIX}"


def write_autosave(source: Path, recipe: Recipe,
                   preview: np.ndarray | None = None) -> Path | None:
    """Kurtarma kaydini atomik olarak yazar.

    Basarisiz olursa None doner ve gunluge yazar; kurtarma yazimi
    kullanicinin calismasini **hicbir kosulda** kesmez.
    """
    try:
        target = autosave_path(source)
        save_project(target, source, recipe, preview, portable=False)
        return target
    except Exception:  # noqa: BLE001
        log.exception("Otomatik kurtarma yazilamadi")
        return None


def find_autosave(source: Path) -> Path | None:
    """Bu fotograf icin kurtarma kaydi var mi?"""
    path = autosave_path(source)
    return path if path.exists() else None


def clear_autosave(source: Path) -> None:
    """Kurtarma kaydini siler (proje duzgun kaydedilince)."""
    try:
        autosave_path(source).unlink(missing_ok=True)
    except OSError:
        log.debug("Kurtarma kaydi silinemedi")


def list_autosaves() -> list[Path]:
    from luma_atelier.core.paths import autosave_dir

    try:
        return sorted(autosave_dir().glob(f"*{AUTOSAVE_SUFFIX}"))
    except OSError:
        return []
