"""Motorlar ve ses varlıkları PROFİL başına değil MAKİNE başına.

Ölçülen hata
------------
``sidecar_root()`` ve ``voice_dir()`` doğrudan ``FOOL_HOME`` altına
yazıyordu. Masaüstü bir profili çalıştırırken ``FOOL_HOME`` o profilin
dizinini gösteriyor, yani her profil kendi motor kurulumunu istiyordu.

Kullanıcının makinesinde ölçüldü::

    fool/sidecars/                       6 motor kurulu
    fool/profiles/persona/sidecars/   YOK

Sonuç: ``persona`` profilinde konuşma "Chatterbox kurulu degil" ile
düşüyordu -- oysa Chatterbox kurulu, bir dizin yukarıda. Kullanıcı motoru
seçmiş, ayarlarda kurulu görünüyor, ve hiç ses çıkmıyor.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    root = tmp_path / "fool"
    (root / "profiles" / "persona").mkdir(parents=True)

    def use(path: Path) -> None:
        monkeypatch.setenv("FOOL_HOME", str(path))
        import fool_constants

        monkeypatch.setattr(fool_constants, "get_hermes_home", lambda: str(path), raising=False)

    return root, use


def test_profil_evi_KOKE_cozuluyor(home) -> None:
    root, use = home
    from fool.machine_assets import machine_home

    use(root / "profiles" / "persona")
    assert machine_home() == root.resolve()


def test_kok_ev_oldugu_gibi_kaliyor(home) -> None:
    root, use = home
    from fool.machine_assets import machine_home

    use(root)
    assert machine_home() == root.resolve()


def test_sidecar_koku_profilden_BAGIMSIZ(home) -> None:
    root, use = home
    from fool import sidecar

    use(root)
    at_root = sidecar.sidecar_root()

    use(root / "profiles" / "persona")
    at_profile = sidecar.sidecar_root()

    assert at_root == at_profile, "profil kendi motorlarini istemek zorunda kalirdi"


def test_ses_dizini_profilden_BAGIMSIZ(home) -> None:
    root, use = home
    from fool import voice_models

    use(root)
    at_root = voice_models.voice_dir()

    use(root / "profiles" / "persona")
    at_profile = voice_models.voice_dir()

    assert at_root == at_profile, "her profil ayni gigabaytlari yeniden indirirdi"


def test_profiles_ALTINDA_olmayan_dizin_kok_sayiliyor(home, tmp_path) -> None:
    """``profiles`` adı yalnızca gerçek profil kabında anlamlı."""
    _, use = home
    from fool.machine_assets import machine_home

    other = tmp_path / "elsewhere" / "fool"
    other.mkdir(parents=True)
    use(other)

    assert machine_home() == other.resolve()
