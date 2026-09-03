"""Takılan bir motor SESİ KALICI OLARAK susturmamalı.

Ölçülen hata
------------
``engine_host.request`` cevabı çıplak ``readline()`` ile okuyordu::

    engine.process.stdin.write(...)
    line = engine.process.stdout.readline()   # <- sınırsız

``REQUEST_TIMEOUT_SECONDS = 300`` dosyanın başında tanımlıydı ve depoda
HİÇBİR YERDE kullanılmıyordu -- yani niyet yazılmış, uygulanmamıştı.

Sidecar takılırsa (CUDA kilidi, model kilitlenmesi, yarıda kalmış indirme)
o çağrı sonsuza kadar bloke oluyor. Asıl bedel yerel değil: bloke olurken
``engine.lock`` ELDE TUTULUYOR, dolayısıyla o motora giden bütün sonraki
istekler de aynı kilitte sıraya giriyor. Sonuç, uygulamanın ses özelliğinin
tamamen ve sessizce ölmesi -- ne ``end``, ne ``fallback``, ne hata.

Sözleşme: cevap sınırlı sürede gelmezse süreç öldürülüyor ve çağıran bir
istisna alıyor, böylece yedek yol devreye girebiliyor ve bir sonraki istek
temiz bir motorla karşılaşıyor.
"""

from __future__ import annotations

import threading
import time

import pytest

from fool import engine_host as eh


class _WedgedProcess:
    """Yazmayı kabul eden ama ASLA cevap vermeyen bir süreç."""

    def __init__(self) -> None:
        self.killed = False
        self.stdin_closed = False
        self.read_released = threading.Event()
        self._release = self.read_released

    def poll(self):
        return None if not self.killed else -9

    def kill(self) -> None:
        self.killed = True
        self._release.set()

    def terminate(self) -> None:
        self.kill()

    def wait(self, timeout=None) -> int:
        return 0

    @property
    def stdin(self):
        return self

    def write(self, _data) -> None:
        return None

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.stdin_closed = True
        self._release.set()

    @property
    def stdout(self):
        return self

    def readline(self) -> str:
        # Surec oldurulene kadar asili kal -- takilmis bir sidecar tam boyle.
        self._release.wait(10)
        return ""


@pytest.fixture(autouse=True)
def _clean():
    eh._ENGINES.clear()
    yield
    eh._ENGINES.clear()


def test_takilan_motor_SINIRLI_surede_birakiliyor(monkeypatch) -> None:
    process = _WedgedProcess()

    engine = eh._Engine(
        lock=threading.Lock(),
        process=process,
        setup_hash=eh._hash("setup"),
        last_used=time.monotonic(),
    )
    eh._ENGINES["takilan"] = engine

    # Gercek 300 sn'yi beklemek bir sinav degil, bir ceza olurdu.
    monkeypatch.setattr(eh, "REQUEST_TIMEOUT_SECONDS", 0.25)

    started = time.monotonic()

    with pytest.raises(RuntimeError, match="cevap vermedi"):
        eh.request("takilan", "setup", {"text": "merhaba"})

    elapsed = time.monotonic() - started

    # SONSUZ degil: sinirin biraz ustunde birakiyor.
    assert elapsed < 5, f"cagri {elapsed:.1f} sn surdu -- sinir islemedi"

    # Motor GERCEKTEN durduruldu: kayittan dusuruldu ve stdin kapatildi
    # (``stop`` once nazik yolu deniyor, ancak o dusunce olduruyor).
    assert "takilan" not in eh._ENGINES
    assert process.stdin_closed, "surec durdurulmadi -- sonraki istek de beklerdi"

    # Ve asili okuma serbest kaldi: is parcaciklari birikmiyor.
    assert process.read_released.wait(2)


def test_okuma_sinirli_ve_None_donuyor() -> None:
    """Yardimci dogrudan: sure dolunca ``None``, aksi halde satir."""
    process = _WedgedProcess()
    engine = eh._Engine(
        lock=threading.Lock(), process=process, setup_hash="x", last_used=0.0
    )

    assert eh._read_reply_bounded(engine, 0.2) is None

    process.kill()  # okuma serbest kaliyor
