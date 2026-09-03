"""``[wake]`` extra'sı ile ``lazy_deps`` AYNI paketleri saymalı.

Aynı bağımlılık listesi iki yerde yaşıyor ve ikisi de kurulum yolu:

  * ``pyproject.toml``in ``[wake]`` extra'sı -- masaüstü kurulumu bunu
    ÖNCEDEN kuruyor (``install_desktop_voice_deps``), böylece ilk uyandırma
    denemesi dakikalarca süren bir pip kurulumuna takılmıyor.
  * ``tools/lazy_deps.py`` -- CLI kurulumları ve uygulama içi "Install"
    düğmesi buradan kuruyor.

``pyproject.toml`` bunu kendi yorumunda "mirrored in tools/lazy_deps.py" diye
söz veriyor. Söz tutulmadı.

Ölçülen hata
------------
``sherpa_onnx.text2token`` ``pypinyin``i KOŞULSUZ içe aktarıyor. Eksiklik önce
``lazy_deps``te düzeltildi, extra'ya taşınmadı. Sonuç: temiz bir masaüstü
kurulumu sherpa'yı ``pypinyin`` olmadan alıyor ve her özel uyandırma ifadesi
şu satırla armlanmayı reddediyor::

    Wake word: "emily wake up" - off - No module named 'pypinyin'

Bu depoda tekrar eden kalıp: bir kolda öğrenilen ders kardeşine taşınmıyor. Bu
test o iki kolu birbirine bağlıyor.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _extra_packages(name: str) -> set[str]:
    """``pyproject.toml``daki bir extra'nın paket adları (sürüm/marker'sız)."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    specs = data["project"]["optional-dependencies"][name]

    out = set()
    for spec in specs:
        # Ortam işaretçisi olanlar platforma özel; ada indirgemek yeterli.
        head = spec.split(";", 1)[0]
        pkg = re.split(r"[=<>!~\[]", head, maxsplit=1)[0].strip()
        if pkg:
            out.add(pkg.lower().replace("_", "-"))
    return out


def _lazy_packages(*features: str) -> set[str]:
    from tools.lazy_deps import LAZY_DEPS

    out = set()
    for feature in features:
        for spec in LAZY_DEPS[feature]:
            pkg = re.split(r"[=<>!~\[]", spec, maxsplit=1)[0].strip()
            if pkg:
                out.add(pkg.lower().replace("_", "-"))
    return out


WAKE_FEATURES = ("wake.openwakeword", "wake.sherpa", "wake.porcupine")


class TestWakeAynasi:
    def test_lazy_deps_te_olan_her_paket_extra_da_VAR(self):
        # Bu yön kritik: extra eksikse masaüstü kurulumu paketi hiç almıyor ve
        # eksiklik ancak kullanıcı uyandırma ifadesini denediğinde çıkıyor.
        lazy = _lazy_packages(*WAKE_FEATURES)
        extra = _extra_packages("wake") | _extra_packages("voice")

        missing = sorted(lazy - extra)

        assert not missing, f"[wake]/[voice] extra'sinda eksik: {missing}"

    def test_pypinyin_ACIKCA_iki_yerde_de(self):
        # Ölçülen hatanın kendisi. Genel testin altında ayrıca duruyor ki
        # düştüğünde sebep bir bakışta görünsün.
        assert "pypinyin" in _extra_packages("wake")
        assert "pypinyin" in _lazy_packages("wake.sherpa")

    def test_uc_motorun_da_paketleri_extra_da(self):
        for feature, package in (
            ("wake.openwakeword", "openwakeword"),
            ("wake.sherpa", "sherpa-onnx"),
            ("wake.porcupine", "pvporcupine"),
        ):
            assert package in _lazy_packages(feature)
            assert package in _extra_packages("wake"), f"{package} extra'da yok"

    def test_pyproject_aynayi_HALA_vaat_ediyor(self):
        # Vaat kaldırılırsa bu testin dayanağı da kalmaz; ikisi birlikte
        # değişmeli.
        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        assert "mirrored in tools/lazy_deps.py" in text
