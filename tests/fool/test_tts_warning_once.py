"""Sağlayıcı çözümleyicisi günlüğü DOLDURMAMALI.

Ölçülen hata
------------
``_get_provider`` bir SORGU: "bu yapılandırmada hangi motor konuşur?" Yerel
motor yok ve bulut kapalıyken cevabı ``"none"`` -- ve her seferinde
kullanıcıya dönük uzun bir uyarı basıyordu.

Tek bir günde bu satır **445 kez** düştü. Sonucu yalnızca gürültü değil:
iki ayrı hata avında o satırlar gerçek bir ürün hatası sanıldı ve zaman
oraya harcandı. Yani günlüğü kirletmek teşhisi aktif olarak yanıltıyor.

Mesajın kendisi ilk seferde gerçekten faydalı, o yüzden susturulmuyor --
yalnızca tekrarı kesiliyor. Çağıran hâlâ ``"none"`` alıyor ve kullanıcıya ne
söyleyeceğine kendi karar veriyor; araç zaten aynı metni HATA olarak
döndürüyor.
"""

from __future__ import annotations

import logging

import pytest

import tools.tts_tool as tts_tool


@pytest.fixture(autouse=True)
def _reset_flag():
    tts_tool._WARNED_CLOUD_BLOCKED = False
    yield
    tts_tool._WARNED_CLOUD_BLOCKED = False


def _blocked_config() -> dict:
    """Sağlayıcı seçilmemiş, yerel motor yok, bulut kapalı."""
    return {"provider": "", "allow_cloud_fallback": False}


def _resolve(monkeypatch, config: dict) -> str:
    # Yerel motor YOK: gerçek kurulumdan bağımsız olsun diye sabitleniyor,
    # yoksa test geliştiricinin makinesindeki motorlara göre sonuç değiştirir.
    monkeypatch.setattr(tts_tool, "_installed_local_tts", lambda: [])

    return tts_tool._get_provider(config)


def test_engellenmis_durumda_none_donuyor(monkeypatch):
    # Ön koşul: aşağıdaki testlerin dayanağı.
    assert _resolve(monkeypatch, _blocked_config()) == "none"


def test_uyari_BIR_KEZ_basiliyor(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="tools.tts_tool"):
        for _ in range(25):
            _resolve(monkeypatch, _blocked_config())

    blocked = [r for r in caplog.records if "nothing was spoken" in r.getMessage()]

    assert len(blocked) == 1, f"25 cagri, {len(blocked)} uyari -- gunluk doluyor"


def test_ilk_uyari_HALA_basiliyor(monkeypatch, caplog):
    # Susturmak da yanlış olurdu: kullanıcı sesin neden çıkmadığını bir yerden
    # öğrenmeli.
    with caplog.at_level(logging.WARNING, logger="tools.tts_tool"):
        _resolve(monkeypatch, _blocked_config())

    assert any("nothing was spoken" in r.getMessage() for r in caplog.records)


def test_ACIK_saglayici_hic_uyarmiyor(monkeypatch, caplog):
    # Kullanıcı bir motor seçmişse ortada sorun yok; uyarı o durumda zaten
    # yanlış olurdu.
    with caplog.at_level(logging.WARNING, logger="tools.tts_tool"):
        resolved = _resolve(monkeypatch, {"provider": "chatterbox"})

    assert resolved == "chatterbox"
    assert not [r for r in caplog.records if "nothing was spoken" in r.getMessage()]
