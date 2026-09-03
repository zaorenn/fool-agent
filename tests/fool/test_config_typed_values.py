"""Zaten tipli bir değer ``set_config_value``'yu çökertmemeli.

Ölçülen hata
------------
``set_config_value`` metin bekliyor ve gövdesinde ``value.lower()`` /
``value.isdigit()`` çağırıyor. Gerçek bir sayı gönderen bir çağıran ilk satırda
patlıyordu::

    File "fool/voice_models.py", line 1324, in set_knob
        set_config_value(f"tts.{...}.{knob.id}", stored)
    AttributeError: 'float' object has no attribute 'lower'

Kullanıcıya görünen: ses ayarlarındaki HER kaydırıcıyı oynatmak
"Could not change that setting -- 500: Internal Server Error". Chatterbox'ın
yoğunluk (``exaggeration``) ve tempo (``cfg_weight``) ayarları hiç
değiştirilemiyordu.

İmza ``value: str`` diyor, yani çağıran taraf da hatalıydı; ama düz bir float'ta
``AttributeError`` ile patlayan bir yardımcı ayak kapanı. Kapı burada duruyor ve
bu SINIF hatayı bitiriyor.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from fool_cli import config as config_module


@pytest.fixture()
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FOOL_HOME", str(tmp_path))
    config_module._LOAD_CONFIG_CACHE.clear()

    return tmp_path


def _read(home: Path) -> dict:
    path = home / "config.yaml"

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def test_float_deger_COKMUYOR(home: Path) -> None:
    """Kaydırıcıların gönderdiği şey tam olarak bu."""
    config_module.set_config_value("tts.chatterbox.exaggeration", 1.9, force=True)

    assert _read(home)["tts"]["chatterbox"]["exaggeration"] == 1.9


def test_int_ve_bool_de_gecerli(home: Path) -> None:
    config_module.set_config_value("tts.chatterbox.steps", 5, force=True)
    config_module.set_config_value("voice.auto_tts", True, force=True)

    cfg = _read(home)

    assert cfg["tts"]["chatterbox"]["steps"] == 5
    assert cfg["voice"]["auto_tts"] is True


def test_METIN_yolu_aynen_duruyor(home: Path) -> None:
    """Kapı yalnızca zaten tipli değerleri atlıyor; metin çevirisi bozulmamalı."""
    config_module.set_config_value("tts.chatterbox.exaggeration", "1.9", force=True)
    config_module.set_config_value("voice.auto_tts", "true", force=True)

    cfg = _read(home)

    assert cfg["tts"]["chatterbox"]["exaggeration"] == 1.9
    assert cfg["voice"]["auto_tts"] is True


def test_kapinin_kendisi_KODDA(home: Path) -> None:
    """Kapı kalkarsa 500'ler sessizce geri gelir."""
    source = Path("fool_cli/config.py").read_text(encoding="utf-8")

    assert "isinstance(value, (bool, int, float))" in source
    assert "ZATEN TIPLI bir deger cevrilmiyor" in source
