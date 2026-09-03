"""Isıtma, motor boşaltıldıktan SONRA yeniden çalışmalı.

Ölçülen hata
------------
``warm()`` iki muhafızla korunuyordu ve ikincisi kalıcıydı::

    if _state.get("status") == "warm" and _state.get("provider") == target:
        return status()

``status`` bir kez ``"warm"`` yazılıyor ve bir daha hiç düşmüyor. Oysa motor
boşta 300 sn sonra boşaltılıyor (``engine_host.SELECTED_IDLE_UNLOAD_SECONDS``,
kullanıcının kendi isteği). Yani İLK başarılı ısıtmadan sonra ``warm()``
kalıcı olarak hiçbir şey yapmıyordu: durum "sıcak" diyor, süreç ölü.

Kullanıcıya görünen: her uzun aradan sonra ilk cümle yeniden soğuk yükleme
bekliyor. Ölçüldü -- kokoro soğuk 29,43 sn, sıcak 1,07 sn.

Sessiz sınıf: hata yok, log yok, yalnızca ısıtma diye bir şey yok.
"""

from __future__ import annotations

import pytest

from fool import tts_warmup


@pytest.fixture(autouse=True)
def _clean():
    tts_warmup.reset_for_tests()
    yield
    tts_warmup.reset_for_tests()


def _pretend_warm(provider: str) -> None:
    """``_run`` başarıyla bitmiş gibi durumu kur."""
    tts_warmup._state.update(status="warm", error="", provider=provider)


# ---------------------------------------------------------------------------
# Yerleşim kontrolü
# ---------------------------------------------------------------------------

def test_motor_AYAKTAYKEN_yeniden_isitilmiyor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gereksiz ısıtma yükle-boşalt döngüsü yaratırdı."""
    started: list[str] = []

    monkeypatch.setattr(tts_warmup, "_still_resident", lambda _p: True)
    monkeypatch.setattr(tts_warmup, "_warm_now", lambda p: started.append(p))

    _pretend_warm("kokoro")
    tts_warmup.warm("kokoro")

    assert started == []


def test_motor_BOSALTILDIYSA_yeniden_isitiliyor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Asıl hata buydu: durum "sıcak" kalıyor, süreç ölü."""
    started: list[str] = []

    monkeypatch.setattr(tts_warmup, "_still_resident", lambda _p: False)
    monkeypatch.setattr(tts_warmup, "_warm_now", lambda p: started.append(p))

    _pretend_warm("kokoro")
    tts_warmup.warm("kokoro")

    if tts_warmup._thread is not None:
        tts_warmup._thread.join(timeout=5)

    assert started == ["kokoro"]


def test_saglayici_DEGISTIYSE_yine_isitiliyor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Eski motorun sıcak olması yeni motor için bir şey ifade etmiyor."""
    started: list[str] = []

    monkeypatch.setattr(tts_warmup, "_still_resident", lambda _p: True)
    monkeypatch.setattr(tts_warmup, "_warm_now", lambda p: started.append(p))

    _pretend_warm("kokoro")
    tts_warmup.warm("chatterbox")

    if tts_warmup._thread is not None:
        tts_warmup._thread.join(timeout=5)

    assert started == ["chatterbox"]


# ---------------------------------------------------------------------------
# ``_still_resident`` kendisi
# ---------------------------------------------------------------------------

def test_yerlesim_motor_barindiricisina_soruluyor(monkeypatch: pytest.MonkeyPatch) -> None:
    from fool import engine_host, voice_preview

    monkeypatch.setattr(voice_preview, "entry_for_provider", lambda _p: "kokoro")
    monkeypatch.setattr(engine_host, "is_running", lambda name: name == "kokoro")

    assert tts_warmup._still_resident("kokoro") is True


def test_bilinmeyen_saglayici_YERLESIK_DEGIL(monkeypatch: pytest.MonkeyPatch) -> None:
    from fool import voice_preview

    monkeypatch.setattr(voice_preview, "entry_for_provider", lambda _p: "")

    assert tts_warmup._still_resident("bilinmeyen") is False


def test_hata_YUTULUYOR_ve_isitmaya_izin_veriyor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Yanlış tarafa düşmenin bedeli fazladan bir (korumalı) ısıtma çağrısı;
    diğer tarafta sessizce ölü bir ısıtma yolu var."""
    from fool import voice_preview

    def _boom(_provider: str) -> str:
        raise RuntimeError("katalog okunamadi")

    monkeypatch.setattr(voice_preview, "entry_for_provider", _boom)

    assert tts_warmup._still_resident("kokoro") is False
