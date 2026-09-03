"""Konuşma tanıma konuşulmadan önce hazırlanıyor.

CODEX görev tanımı "STT tur sonunda çalışıyor, uzun cümlede saniyeler
kaybediliyor" diyor ve akışlı STT öneriyor. Ölçtüm (bu makine, RTX 4070 Ti
SUPER, Whisper large-v3-turbo float16, 12,18 saniyelik GERÇEK konuşma):

    ilk çağrı  : 6,94 sn   <- model yükleme dahil
    2. çağrı   : 0,37 sn
    3. çağrı   : 0,36 sn

Sıcak durumda 12 saniyelik bir cümle 0,37 saniyede yazıya dökülüyor. Akışlı
STT bunun belki 0,3 saniyesini kazandırırdı; kaybedilen saniyeler orada
DEĞİL. Soğuk başlangıçta:

    ısıtılmış ilk transkripsiyon : 0,66 sn   (ısıtmasız: 6,94 sn)

Bu testler ısıtmanın sözleşmesini tutuyor: bir kez yükler, iki kez
yüklemez, ve ASLA çağıranı patlatmaz.
"""

from __future__ import annotations

import pytest

from fool import stt_warmup


@pytest.fixture(autouse=True)
def _clean():
    stt_warmup.reset_for_tests()
    yield
    stt_warmup.reset_for_tests()


def test_baslangicta_soguk() -> None:
    assert stt_warmup.status()["status"] == "cold"


def test_isitma_durumu_warm_yapiyor(monkeypatch) -> None:
    monkeypatch.setattr(stt_warmup, "_warm_now", lambda: None)

    stt_warmup.warm(blocking=True)

    assert stt_warmup.status()["status"] == "warm"


def test_ikinci_cagri_yeniden_yuklemiyor(monkeypatch) -> None:
    """Isıtma idempotent olmalı: iki kez yüklemek 7 saniyeyi iki kez ödemek.

    Sınav MODELİN YERLEŞİK olduğunu da taklit ediyor. Eskiden yalnızca
    ``_warm_now`` sahteleniyordu ve idempotanslık ``_state["status"]``
    üzerinden okunuyordu -- ama o durum bir kez "warm" olunca bir daha hiç
    düşmüyor, oysa model boşta kalınca bellekten bırakılıyor. Yani sınav
    "aynı çağrı iki kez yüklemesin"i değil, "bayrak bir kez yazılsın"ı
    tutuyordu ve gerçek kusuru (bkz. ``test_stt_warmup_rearm.py``)
    göremiyordu.

    Doğru sözleşme: model YERLEŞİKKEN ikinci çağrı işlemsiz.
    """
    calls = []
    resident = []

    monkeypatch.setattr(stt_warmup, "_warm_now", lambda: (calls.append(1), resident.append(1)))
    monkeypatch.setattr(stt_warmup, "_still_resident", lambda: bool(resident))

    stt_warmup.warm(blocking=True)
    stt_warmup.warm(blocking=True)

    assert len(calls) == 1


def test_hata_YAYILMIYOR(monkeypatch) -> None:
    """Isıtma bir iyileştirme, bir gereklilik değil.

    Patlarsa eski davranış aynen geçerli: ilk transkripsiyon modeli kendisi
    yükler. Isıtmanın sesli oturumu açılmaz yapması kabul edilemez.
    """
    def _boom():
        raise RuntimeError("no CUDA")

    monkeypatch.setattr(stt_warmup, "_warm_now", _boom)

    result = stt_warmup.warm(blocking=True)  # istisna FIRLATMAMALI

    assert result["status"] == "failed"
    assert "no CUDA" in result["error"]


def test_basarisizliktan_sonra_yeniden_denenebiliyor(monkeypatch) -> None:
    """Geçici bir hata (model indiriliyordu) kalıcı bir kilit olmamalı."""
    monkeypatch.setattr(stt_warmup, "_warm_now", lambda: (_ for _ in ()).throw(OSError("x")))
    stt_warmup.warm(blocking=True)
    assert stt_warmup.status()["status"] == "failed"

    monkeypatch.setattr(stt_warmup, "_warm_now", lambda: None)
    stt_warmup.warm(blocking=True)

    assert stt_warmup.status()["status"] == "warm"


def test_arka_planda_calisiyor(monkeypatch) -> None:
    """Istem yolunu ASLA bloke etmemeli."""
    import threading

    started = threading.Event()
    release = threading.Event()

    def _slow():
        started.set()
        release.wait(timeout=5)

    monkeypatch.setattr(stt_warmup, "_warm_now", _slow)

    stt_warmup.warm()  # blocking DEGIL

    assert started.wait(timeout=5)
    assert stt_warmup.status()["status"] == "warming"
    release.set()


def test_status_kopya_donuyor() -> None:
    """Çağıranın elindeki sözlüğü değiştirmesi iç durumu bozmamalı."""
    snapshot = stt_warmup.status()
    snapshot["status"] = "hacked"

    assert stt_warmup.status()["status"] == "cold"


def test_model_adi_transkripsiyonla_AYNI_kuralla_cozuluyor() -> None:
    """Farklı çözmek yanlış modeli ısıtıp doğrusunu soğukta bırakırdı."""
    import inspect

    source = inspect.getsource(stt_warmup._warm_now)

    assert "_normalize_local_model" in source
    assert "_load_local_whisper_model" in source


def test_isitma_bosta_sayacini_sifirliyor() -> None:
    """Isıttığımız model bir sonraki tur başlamadan boşaltılmamalı.

    Paylaşılan 16 GB kartta boşta-boşaltma 300 sn (fool/gpu_budget.py);
    sayacı sıfırlamadan ısıtmak, ısınan modelin hemen atılmasına yol
    açabilirdi.
    """
    import inspect

    assert "_touch_transcription_time" in inspect.getsource(stt_warmup._warm_now)
