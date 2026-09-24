"""Calisan yapinin kimligi: surum, derleme kimligi, kaynak ozeti.

Neden gerekli
-------------
"Masaustu kisayolunun actigi kurulu surum son test edilen kodu iceriyor
mu?" sorusu, surum numarasina bakarak cevaplanamaz: surum numarasi
degismeden kaynak defalarca degisir. Bu yuzden derleme sirasinda
`resources/build_info.json` yazilir ve icinde:

* `build_id`  : derleme zamani + kaynak ozetinin ilk hanelerinden
* `source_digest` : paketlenen tum kaynak dosyalarin SHA-256 ozeti
* `built_at`  : UTC zaman damgasi
* `python`, `dependencies` : uretim ortami

bulunur. Uygulama bunu "Hakkinda" penceresinde ve `--self-test`
ciktisinda gosterir; kurulum bildirimi (`BUILD_MANIFEST.md`) ayni
degerleri tasir. Ikisi eslesiyorsa kurulu paketin hangi kaynaktan
geldigi kanitlanmis olur.

Dosya yoksa (kaynaktan calistirma) `DEV_BUILD` dondurulur; "gelistirme"
oldugunu gizlemek, olmayan bir izlenebilirligi varmis gibi gostermek
olurdu.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: Derleme bilgisi dosyasinin kaynaklar icindeki adi
BUILD_INFO_NAME = "build_info.json"


@dataclass(frozen=True)
class BuildInfo:
    """Calisan yapinin kimligi."""

    build_id: str = "gelistirme"
    built_at: str = ""
    source_digest: str = ""
    python: str = ""
    dependencies: dict[str, str] = field(default_factory=dict)

    @property
    def is_development(self) -> bool:
        return self.build_id == "gelistirme"

    def summary(self) -> str:
        """Arayuzde gosterilecek tek satir."""
        if self.is_development:
            return "kaynaktan çalışıyor (derleme kimliği yok)"
        return f"derleme {self.build_id} · {self.built_at}"


DEV_BUILD = BuildInfo()


@lru_cache(maxsize=1)
def build_info() -> BuildInfo:
    """Paketlenmis derleme bilgisini okur; yoksa gelistirme dondurur."""
    from luma_atelier.core.paths import resources_dir

    path = resources_dir() / BUILD_INFO_NAME
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return DEV_BUILD
    except (OSError, ValueError) as exc:
        log.warning("Derleme bilgisi okunamadi (%s); gelistirme varsayiliyor",
                    exc)
        return DEV_BUILD
    if not isinstance(raw, dict):
        return DEV_BUILD
    deps = raw.get("dependencies")
    return BuildInfo(
        build_id=str(raw.get("build_id") or "gelistirme"),
        built_at=str(raw.get("built_at") or ""),
        source_digest=str(raw.get("source_digest") or ""),
        python=str(raw.get("python") or ""),
        dependencies={str(k): str(v) for k, v in deps.items()}
        if isinstance(deps, dict) else {},
    )


def write_build_info(target: Path, info: dict[str, Any]) -> Path:
    """Derleme bilgisini yazar (yalnizca uretim betigi kullanir)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return target
