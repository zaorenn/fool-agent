"""Hafıza ve ses duygusu NORMAL modda da olmalı.

İstenen: "hafıza normal modda da olmalı, yada ses duygusu falan."

İkisi de kilitliydi ve ikisi de yanlış gerekçeyle:

* ``memory.provider`` varsayılanı YOKTU. Taze bir kurulum hafızasız
  çalışıyordu ve kullanıcı bunu ancak "neden hiçbir şey hatırlamıyorsun" diye
  sorunca öğreniyordu.
* Teslimat etiketi ipucu ``relationship`` bloğunun İÇİNDEYDİ, yani yalnızca
  persona profilinde. Gerekçesi "sıradan ajanın cevabı okunuyor,
  seslendirilmiyor" idi -- oysa sesli sohbet ve çentik sıradan ajanla da
  kullanılıyor.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def provider_for(monkeypatch):
    def _run(config: dict) -> str | None:
        from fool_cli import config as config_module
        from plugins import memory as memory_module

        monkeypatch.setattr(config_module, "load_config", lambda: config, raising=False)

        return memory_module._get_active_memory_provider()

    return _run


def test_anahtar_YOKKEN_recall(provider_for) -> None:
    """Yerel, kurulum istemeyen ve model istemedikçe hiçbir şey yazmayan tek
    sağlayıcı; varsayılan olabilecek tek aday."""
    assert provider_for({}) == "recall"
    assert provider_for({"memory": {}}) == "recall"


def test_ACIK_secim_korunuyor(provider_for) -> None:
    assert provider_for({"memory": {"provider": "honcho"}}) == "honcho"


def test_ACIKCA_bos_birakmak_KAPALI_demek(provider_for) -> None:
    """Kullanıcının kararı geri alınmıyor."""
    assert provider_for({"memory": {"provider": ""}}) is None
    assert provider_for({"memory": {"provider": "   "}}) is None


def test_bulut_saglayicilar_varsayilan_OLMUYOR(provider_for) -> None:
    """Kimlik bilgisi isteyen bir sağlayıcıyı sessizce varsayılan yapmak,
    kullanıcının konuşmasını kurmadığı bir servise göndermek olurdu."""
    assert provider_for({}) not in {"honcho", "mem0"}


# ---------------------------------------------------------------------------
# Ses duygusu
# ---------------------------------------------------------------------------


def test_etiket_ipucu_SESE_bagli_personaya_degil() -> None:
    from pathlib import Path

    source = Path("plugins/memory/recall/__init__.py").read_text(encoding="utf-8")
    body = source[source.index("def system_prompt_block") : source.index("def _curiosity_line")]

    assert "prompt_hint" in body
    # Ipucu SES kapisinin arkasinda...
    assert body.index("if _voice_in_use():") < body.index("prompt_hint")
    # ...ve ILISKI kapisindan tamamen bagimsiz.
    persona = body.index("if self._relationship_enabled():")
    assert "prompt_hint" not in body[persona:]


def test_motor_yokken_ipucu_VERILMIYOR(monkeypatch) -> None:
    """Motoru olmayan kullanıcıya etiket sözlüğü vermek promptu bedelsiz
    şişirirdi."""
    from plugins.memory import recall as recall_module

    monkeypatch.setattr("tools.tts_tool._get_provider", lambda _cfg: "none", raising=False)

    assert recall_module._voice_in_use() is False


def test_motor_VARKEN_ipucu_veriliyor(monkeypatch) -> None:
    from plugins.memory import recall as recall_module

    monkeypatch.setattr("tools.tts_tool._get_provider", lambda _cfg: "piper", raising=False)

    assert recall_module._voice_in_use() is True


def test_cozucu_OKUNAMAZSA_ipucu_verilmiyor(monkeypatch) -> None:
    from plugins.memory import recall as recall_module

    def _boom(_cfg):
        raise RuntimeError("okunamadi")

    monkeypatch.setattr("tools.tts_tool._get_provider", _boom, raising=False)

    assert recall_module._voice_in_use() is False
