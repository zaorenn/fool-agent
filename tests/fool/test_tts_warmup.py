"""Friend "dakikalarca model uyandırılıyor" diyordu, ayarlar 2,5 saniyede konuşuyordu.

Ölçülen fark motorun sıcak olup olmaması:

    kokoro     soğuk 24,17 sn   sıcak 0,32 sn
    styletts2  soğuk 67,21 sn   sıcak 0,86 sn

Ayarlar panelinde motor zaten sıcaktı (kullanıcı az önce önizleme yapmıştı).
Friend penceresi ise ısıtmayı HİÇ çağırmıyordu -- ``warmStt`` yalnızca
tanımayı ısıtıyordu ve o çağrı da yalnızca notch'ta vardı.

Isıtmanın tehlikeli tarafı, ISTEM YOLUNU BLOKLAMAK ve HATA YAYMAK. İkisi de
ısıtmanın amacına aykırı: bu bir iyileştirme, bir gereklilik değil.
"""

from __future__ import annotations

import threading
import time

import pytest

from fool import tts_warmup


@pytest.fixture(autouse=True)
def _clean():
    tts_warmup.reset_for_tests()
    yield
    tts_warmup.reset_for_tests()


def _wait(timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and tts_warmup.status()["status"] == "warming":
        time.sleep(0.01)
    return tts_warmup.status()


# ---------------------------------------------------------------------------
# Bloklamıyor
# ---------------------------------------------------------------------------

def test_warm_HEMEN_donuyor(monkeypatch) -> None:
    """Isıtma çağrısı sentezi bekleseydi, kazanç sıfır olurdu: kullanıcı
    beklemeyi yine ödemiş olurdu, sadece başka bir yerde."""
    gate = threading.Event()
    monkeypatch.setattr(tts_warmup, "_warm_now", lambda provider: gate.wait(5))

    started = time.monotonic()
    state = tts_warmup.warm("kokoro")
    elapsed = time.monotonic() - started
    gate.set()

    assert elapsed < 0.5, f"warm() blokladi: {elapsed:.2f}s"
    assert state["status"] == "warming"


def test_hata_YAYILMIYOR(monkeypatch) -> None:
    """Isıtma başarısız olduysa ilk gerçek cümle modeli kendisi yükler.
    Burada hata göstermek, hiçbir şey bozulmamışken telaş yaratırdı."""

    def _boom(provider: str) -> None:
        raise RuntimeError("motor coktu")

    monkeypatch.setattr(tts_warmup, "_warm_now", _boom)

    tts_warmup.warm("kokoro")

    assert _wait()["status"] == "failed"


def test_basarili_isitma_warm_yaziyor(monkeypatch) -> None:
    monkeypatch.setattr(tts_warmup, "_warm_now", lambda provider: None)
    tts_warmup.warm("kokoro")

    assert _wait()["status"] == "warm"


# ---------------------------------------------------------------------------
# İki kez yüklememek
# ---------------------------------------------------------------------------

def test_ikinci_cagri_YENI_is_baslatmiyor(monkeypatch) -> None:
    """İki ısıtma aynı motoru iki kez yüklemeye çalışır ve tek-motor kuralı
    yüzünden yükle-boşalt döngüsüne girerdi (bkz. fool/engine_host.py)."""
    calls: list[str] = []
    gate = threading.Event()

    def _slow(provider: str) -> None:
        calls.append(provider)
        gate.wait(5)

    monkeypatch.setattr(tts_warmup, "_warm_now", _slow)

    tts_warmup.warm("kokoro")
    tts_warmup.warm("kokoro")
    tts_warmup.warm("kokoro")
    gate.set()
    _wait()

    assert calls == ["kokoro"]


def test_ISINMIS_motor_yeniden_isitilmiyor(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(tts_warmup, "_warm_now", lambda p: calls.append(p))
    monkeypatch.setattr(tts_warmup, "_still_resident", lambda p: True)

    tts_warmup.warm("kokoro")
    _wait()
    tts_warmup.warm("kokoro")
    _wait()

    assert calls == ["kokoro"]


def test_SAGLAYICI_DEGISINCE_yeniden_isitiliyor(monkeypatch) -> None:
    """Kullanıcı motoru değiştirdiğinde eskisinin sıcak olması işe yaramıyor."""
    calls: list[str] = []
    monkeypatch.setattr(tts_warmup, "_warm_now", lambda p: calls.append(p))

    tts_warmup.warm("kokoro")
    _wait()
    tts_warmup.warm("styletts2")
    _wait()

    assert calls == ["kokoro", "styletts2"]


# ---------------------------------------------------------------------------
# Sağlayıcı yoksa
# ---------------------------------------------------------------------------

def test_saglayici_YOKSA_is_baslatilmiyor(monkeypatch) -> None:
    """Boş sağlayıcıyla ısıtmak, hangi modeli yükleyeceğini bilmeden bir
    süreç başlatmak olurdu."""
    monkeypatch.setattr(tts_warmup, "_active_provider", lambda: "")
    calls: list[str] = []
    monkeypatch.setattr(tts_warmup, "_warm_now", lambda p: calls.append(p))

    state = tts_warmup.warm()

    assert state["status"] == "cold"
    assert calls == []


def test_saglayici_verilmezse_yapilandirmadan_okunuyor(monkeypatch) -> None:
    monkeypatch.setattr(tts_warmup, "_active_provider", lambda: "styletts2")
    calls: list[str] = []
    monkeypatch.setattr(tts_warmup, "_warm_now", lambda p: calls.append(p))

    tts_warmup.warm()
    _wait()

    assert calls == ["styletts2"]


def test_bilinmeyen_saglayici_COKMUYOR() -> None:
    """Gerçek ``_warm_now`` ile: tanınmayan ad temiz bir ``failed`` olmalı,
    izlenemeyen bir istisna değil."""
    tts_warmup.warm("boyle-bir-motor-yok")

    assert _wait()["status"] == "failed"


# ---------------------------------------------------------------------------
# Kimlik / ad dönüşümü
# ---------------------------------------------------------------------------

def test_saglayici_adindan_katalog_kimligi() -> None:
    """İkisi aynı DEĞİL: ``qwen3-tts`` indiriliyor, ``qwen3`` çalışıyor.
    Karıştırmak ısıtmayı sessizce hiç çalışmaz hale getirirdi."""
    from fool.voice_preview import entry_for_provider

    assert entry_for_provider("qwen3") == "qwen3-tts"
    assert entry_for_provider("kokoro") == "kokoro"
    assert entry_for_provider("yok") == ""
    assert entry_for_provider("") == ""


def test_isitma_metni_KISA_ama_tek_kelime_degil() -> None:
    """Amaç modeli kurmak. Ama tek heceli girdide bazı motorlar prosodi
    hesaplarını atlıyor ve ilk gerçek cümlede maliyet yine çıkıyor."""
    assert 0 < len(tts_warmup.WARMUP_TEXT) <= 40
