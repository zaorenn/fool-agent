"""Motora özel ses ayarları arayüzden görülüp değiştirilebiliyor mu.

Bildirilen: "ayarlardan ses modellerinin exaggeration gibi ayarlarını
yapamıyoruz."

Değerler ``config.yaml``da duruyordu ve motor onları okuyordu; eksik olan
YALNIZCA arayüz yoluydu. Buradaki testler o yolun iki ucunu da tutuyor:
panelin gördüğü sayı motorun kullanacağı sayı olmalı, ve panelin sunduğu her
kol gerçekten okunan bir anahtar olmalı.
"""

from __future__ import annotations

import pytest

from fool import voice_models


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Yapılandırmayı BELLEKTE tut -- gerçek dosyaya yazmayalım."""
    store: dict = {}

    def _set(key: str, value) -> None:
        node = store
        parts = key.split(".")

        for part in parts[:-1]:
            node = node.setdefault(part, {})

        node[parts[-1]] = value

    from fool_cli import config as config_module

    monkeypatch.setattr(config_module, "set_config_value", _set, raising=False)
    monkeypatch.setattr(config_module, "load_config_readonly", lambda: store, raising=False)

    return store


# ---------------------------------------------------------------------------
# Katalog kolları
# ---------------------------------------------------------------------------


def test_chatterbox_iki_kolu_sunuyor(config) -> None:
    rows = voice_models.knob_status(voice_models.entry("chatterbox"))

    assert [row["id"] for row in rows] == ["exaggeration", "cfg_weight"]


def test_kolu_olmayan_motor_BOS(config) -> None:
    assert voice_models.knob_status(voice_models.entry("kokoro")) == []


def test_deger_yokken_VARSAYILAN_gosteriliyor(config) -> None:
    """Boş göstermek "ayarlı değil" dedirtirdi; oysa motorun bir varsayılanı
    var ve kaydıracı oynatmak onu hiç görmeden değiştirmek olurdu."""
    rows = voice_models.knob_status(voice_models.entry("chatterbox"))

    assert rows[0]["value"] == rows[0]["default"]


def test_yapilandirmadaki_deger_okunuyor(config) -> None:
    config["tts"] = {"chatterbox": {"exaggeration": 0.9}}

    rows = voice_models.knob_status(voice_models.entry("chatterbox"))

    assert rows[0]["value"] == 0.9


def test_metin_olarak_yazilmis_deger_de_okunuyor(config) -> None:
    config["tts"] = {"chatterbox": {"cfg_weight": "0.3"}}

    rows = voice_models.knob_status(voice_models.entry("chatterbox"))

    assert rows[1]["value"] == 0.3


def test_bozuk_deger_VARSAYILANA_dusuyor(config) -> None:
    config["tts"] = {"chatterbox": {"exaggeration": "quite a lot"}}

    rows = voice_models.knob_status(voice_models.entry("chatterbox"))

    assert rows[0]["value"] == 0.5


def test_aralik_disi_kayitli_deger_KIRPILARAK_gosteriliyor(config) -> None:
    config["tts"] = {"chatterbox": {"exaggeration": 9.0}}

    rows = voice_models.knob_status(voice_models.entry("chatterbox"))

    assert rows[0]["value"] == 2.0


def test_katalog_satirinda_kollar_VAR(config) -> None:
    row = voice_models._catalog_row(voice_models.entry("chatterbox"), {})

    assert [knob["id"] for knob in row["knobs"]] == ["exaggeration", "cfg_weight"]


# ---------------------------------------------------------------------------
# Yazma
# ---------------------------------------------------------------------------


def test_ayarlanan_deger_MOTORUN_ad_alanina_yaziliyor(config) -> None:
    voice_models.set_knob("chatterbox", "exaggeration", 0.8)

    assert config["tts"]["chatterbox"]["exaggeration"] == 0.8


def test_deger_KIRPILIYOR(config) -> None:
    """``cfg_weight=0`` Chatterbox'ta konuşmayı tamamen durduruyor."""
    voice_models.set_knob("chatterbox", "cfg_weight", 0.0)

    assert config["tts"]["chatterbox"]["cfg_weight"] == 0.2


def test_tamsayi_kol_TAMSAYI_yaziliyor(config) -> None:
    """Motor ``range(5.0)`` ile patlar."""
    voice_models.set_knob("styletts2", "diffusion_steps", 8.0)

    stored = config["tts"]["styletts2"]["diffusion_steps"]

    assert stored == 8
    assert isinstance(stored, int)


def test_bilinmeyen_kol_REDDEDILIYOR(config) -> None:
    with pytest.raises(ValueError):
        voice_models.set_knob("chatterbox", "vibe", 1.0)


def test_kolu_olmayan_motorda_REDDEDILIYOR(config) -> None:
    with pytest.raises(ValueError):
        voice_models.set_knob("kokoro", "exaggeration", 1.0)


def test_bilinmeyen_motor_REDDEDILIYOR(config) -> None:
    with pytest.raises(ValueError):
        voice_models.set_knob("nope", "exaggeration", 1.0)


def test_yazilan_deger_geri_OKUNUYOR(config) -> None:
    """Panelin gördüğü sayı, motorun kullanacağı sayı olmalı."""
    voice_models.set_knob("chatterbox", "exaggeration", 0.75)

    rows = voice_models.knob_status(voice_models.entry("chatterbox"))

    assert rows[0]["value"] == 0.75


# ---------------------------------------------------------------------------
# Sunulan her kol GERCEKTEN okunuyor mu
# ---------------------------------------------------------------------------


def test_her_kol_motorun_KENDI_ad_alanindan_okunuyor() -> None:
    """Panelin yalan söylememesi için: motorun okumadığı bir kaydırıcı,
    ayarlıyormuş gibi görünüp hiçbir şey yapmaz. ``tts.<motor>.voice`` yıllarca
    yazılıp hiç okunmamıştı; aynı hata sınıfı."""
    import re
    from pathlib import Path

    folders = {
        "chatterbox": "fool-chatterbox",
        "styletts2": "fool-styletts2",
        "f5tts": "fool-f5tts",
    }

    for entry in voice_models.CATALOG:
        if not entry.knobs:
            continue

        provider = entry.provider_id or entry.id
        source = Path("plugins/tts") / folders[provider] / "__init__.py"
        text = source.read_text(encoding="utf-8")

        for knob in entry.knobs:
            assert re.search(r'["\']' + knob.id + r'["\']', text), (
                provider + " does not read " + knob.id
            )
