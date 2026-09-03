"""Boşta bırakılan STT modeli için ısıtma YENİDEN kurulmalı.

Ölçülen hata
------------
``stt_warmup.warm()`` şu muhafızla başlıyordu::

    if _state["status"] in ("warming", "warm"):
        return status()

``_state["status"]`` yalnızca ısıtma işi tarafından yazılıyor ve bir daha hiç
düşmüyor. Oysa model boşta kalınca bellekten bırakılıyor
(``tools.transcription_tools._unload_local_model``, 16 GB kartta 300 sn).

Sonuç: ilk başarılı ısıtmadan sonra ``warm()`` KALICI OLARAK işlemsiz. Durum
"warm" diyor, model yok. Kullanıcı bir süre konuşmayınca bir sonraki cümlesi
soğuk yükleme bedelini ödüyor -- ölçüldü, 6,94 sn'ye karşı 0,66 sn.

Seslendirme tarafı bunu çözmüştü (``test_tts_warmup_rearm.py``); bu sınav aynı
güvenceyi konuşma tanıma için tutuyor.
"""

from __future__ import annotations

import pytest

from fool import stt_warmup


@pytest.fixture(autouse=True)
def _clean():
    stt_warmup.reset_for_tests()
    yield
    stt_warmup.reset_for_tests()


def test_model_BOSALTILDIYSA_isitma_yeniden_kosuyor(monkeypatch) -> None:
    calls: list[int] = []

    monkeypatch.setattr(stt_warmup, "_warm_now", lambda: calls.append(1))

    # Ilk isitma.
    monkeypatch.setattr(stt_warmup, "_still_resident", lambda: False)
    stt_warmup.warm(blocking=True)
    assert calls == [1]
    assert stt_warmup.status()["status"] == "warm"

    # Model hala yerlesikken TEKRAR isitmak bos is -- kural korunuyor.
    monkeypatch.setattr(stt_warmup, "_still_resident", lambda: True)
    stt_warmup.warm(blocking=True)
    assert calls == [1], "yerlesik modelde gereksiz isitma"

    # Bosta bosaltma calisti: durum hala "warm" diyor ama model YOK.
    monkeypatch.setattr(stt_warmup, "_still_resident", lambda: False)
    stt_warmup.warm(blocking=True)
    assert calls == [1, 1], "bosaltilmis modelde isitma yeniden kosmali"


def test_yerlesiklik_gercek_modulden_okunuyor(monkeypatch) -> None:
    """``_still_resident`` durum sozlugune degil GERCEGE bakiyor."""
    from tools import transcription_tools as tt

    monkeypatch.setattr(tt, "_local_model", None, raising=False)
    assert stt_warmup._still_resident() is False

    monkeypatch.setattr(tt, "_local_model", object(), raising=False)
    assert stt_warmup._still_resident() is True
