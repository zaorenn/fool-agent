"""Sürüm numarası TEK olmalı.

Ölçülen hata
------------
Depoda beş ayrı sürüm vardı ve hiçbiri diğerini tutmuyordu::

    fool_cli/__init__.py            0.20.2
    pyproject.toml                  0.20.3
    apps/desktop/package.json       0.20.4
    package.json (kök)              1.0.0
    apps/bootstrap-installer        0.0.1

``scripts/release.py::update_version_files`` ÜÇÜNÜ kilitli tutmak için
yazılmış -- ama ``Release 0.20.4`` commit'i yalnızca masaüstü
``package.json``ını değiştirmiş, yani betik atlanmış. Sonucu kullanıcıya
gösteriliyor: Hakkında panosu CANLI ajan sürümünü okuyor, paketleme
üstverisi ise ``package.json``ı -- yani aynı kurulum kendini iki farklı
sürüm olarak tanıtabiliyor.

Bu sınav, betiği atlamayı bir dahaki sefere GÖRÜNÜR yapıyor.

Kök ``package.json`` bilerek DIŞARIDA: o bir çalışma alanı kökü, bir
ürün değil.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _python_package_version() -> str:
    text = (REPO_ROOT / "fool_cli" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    assert match, "fool_cli/__init__.py icinde __version__ yok"
    return match.group(1)


def _pyproject_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    assert match, "pyproject.toml icinde version yok"
    return match.group(1)


def _desktop_version() -> str:
    payload = json.loads(
        (REPO_ROOT / "apps" / "desktop" / "package.json").read_text(encoding="utf-8")
    )
    return str(payload["version"])


def test_uc_izlenen_surum_AYNI() -> None:
    versions = {
        "fool_cli/__init__.py": _python_package_version(),
        "pyproject.toml": _pyproject_version(),
        "apps/desktop/package.json": _desktop_version(),
    }

    assert len(set(versions.values())) == 1, (
        "surumler ayrismis -- release.py atlanmis olabilir: " + repr(versions)
    )


def test_surum_semver_bicimi() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", _desktop_version()), _desktop_version()
