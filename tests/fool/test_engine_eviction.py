"""Motorlar VRAM'i paylaşıyor ve kimse bırakmıyordu.

Ölçüldü (RTX 4070 Ti SUPER, uygulama açık, birkaç motor denenmiş):

    nvidia-smi -> 15338 / 16376 MiB dolu, 724 MiB boş, 10 süreç

Her TTS motoru kalıcı bir süreçte yaşıyor ve modelini VRAM'e yükleyip HİÇ
bırakmıyordu. Beş TTS motoru + whisper + LM Studio'daki 9B model aynı kartta
birikince her şey bozuluyor: sentez saniyelerce takılıyor, panelde
"Speaking…" donuyor, çoğu zaman hiç ses çıkmıyor.

Kullanıcıya "TTS çalışmıyor" diye görünen şey buydu -- tek tek her motor
çalışıyor, hepsi birlikte hiçbiri çalışmıyor.

Tahliyeden sonra ölçülen (aynı sıra, aynı motorlar):

    boş VRAM hiç 6688 MiB'in altına düşmedi
    piper 0,17 · kokoro 0,19 · styletts2 0,60 · chatterbox 2,10 sn (ısınmış)
"""

from __future__ import annotations

import threading
import time

import pytest

from fool import engine_host as eh


class _FakeProcess:
    def __init__(self) -> None:
        self.killed = False

    def poll(self):
        return None

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout=None) -> int:
        return 0

    def terminate(self) -> None:
        self.killed = True

    @property
    def stdin(self):
        return None

    @property
    def stdout(self):
        return None


def _engine(last_used: float = 0.0) -> eh._Engine:
    return eh._Engine(
        lock=threading.Lock(),
        process=_FakeProcess(),
        setup_hash="x",
        last_used=last_used,
    )


@pytest.fixture(autouse=True)
def _clean():
    eh._ENGINES.clear()
    yield
    eh._ENGINES.clear()


# ---------------------------------------------------------------------------
# Tek motor
# ---------------------------------------------------------------------------

def test_sinir_TEK_motor() -> None:
    """Bir -- ve iki oldugu donemin sebebi ARTIK YOK.

    Bir sure 2 idi. Sebebi olculmustu: o gun uygulamada AYNI ANDA iki yuzey
    konusuyordu (sohbet paneli genel ``tts.provider`` ile, Friend KENDI
    sectigiyle). Ikisi farkli motor secince her tur yukle-bosalt-yukle
    dongusune giriyordu -- qwen3 40 sn + styletts2 37 sn. Makine surekli
    model yukluyor, hicbir cumle zamaninda seslendirilmiyor.

    O sebep kalkti: kip basina ses uclari kaldirildi, seslendirme motoru her
    yuzeyde TEK yerden seciliyor (``tts.provider``). Iki yuzey artik ayni
    motoru istiyor, yani ikinci yuva yalnizca ONCEKI secimi bellekte
    tutuyordu -- kullanicinin kurali ise "kategoride yeni bir sey secilince
    oncekisi TAMAMEN birakilsin" (bkz. ``fool/residency.py``).
    """
    assert eh.MAX_RESIDENT_ENGINES == 1


def test_yeni_motor_ONCEKINI_bosaltiyor() -> None:
    """Tek yuva: yeni motor istenince ayakta duran gidiyor."""
    eh._ENGINES["onceki"] = _engine(last_used=1.0)

    eh._evict_for("yeni")

    assert "onceki" not in eh._ENGINES


def test_sinir_asilinca_HEPSI_bosaltiliyor() -> None:
    """Tek yuvaya iki motor sigmaz: ikisi de gidiyor, en eskisi once."""
    eh._ENGINES["eski"] = _engine(last_used=1.0)
    eh._ENGINES["orta"] = _engine(last_used=5.0)

    eh._evict_for("yeni")

    assert eh._ENGINES == {}


def test_ISTENEN_motor_kendisi_tahliye_edilmiyor() -> None:
    """Ayakta olan motor YENIDEN istenince durdurulmamali.

    Tek yuvada bu kolayca ters gidebilirdi: sayi siniri ``(1 + 1) - 1 = 1``
    okuyup tam da konusmakta olan motoru bosaltirdi. ``_evict_for`` istenen
    adi aday listesinden cikariyor -- bu test o inceligi tutuyor.
    """
    eh._ENGINES["kokoro"] = _engine(last_used=1.0)

    eh._evict_for("kokoro")

    assert "kokoro" in eh._ENGINES


def test_EN_ESKI_kullanilan_once_gidiyor(monkeypatch) -> None:
    eh._ENGINES["eski"] = _engine(last_used=1.0)
    eh._ENGINES["yeni"] = _engine(last_used=99.0)

    eh._evict_for("ucuncu")

    assert "eski" not in eh._ENGINES


# ---------------------------------------------------------------------------
# KULLANIMDA olan motor korunuyor
# ---------------------------------------------------------------------------

def test_kullanimda_olan_motor_TAHLIYE_EDILMIYOR() -> None:
    """Kilidi tutulan bir motoru durdurmak süren bir sentezi ortasından kesmek.

    Kullanıcı cümlenin yarısını duyar ve sebebini göremez.
    """
    busy = _engine(last_used=1.0)
    busy.lock.acquire()
    eh._ENGINES["mesgul"] = busy

    try:
        eh._evict_for("yeni")

        assert "mesgul" in eh._ENGINES
    finally:
        busy.lock.release()


def test_kullanimda_olan_bosta_taramada_da_korunuyor() -> None:
    busy = _engine(last_used=time.monotonic() - eh.IDLE_UNLOAD_SECONDS - 100)
    busy.lock.acquire()
    eh._ENGINES["mesgul"] = busy

    try:
        assert eh._idle_sweep() == []
        assert "mesgul" in eh._ENGINES
    finally:
        busy.lock.release()


# ---------------------------------------------------------------------------
# Boşta zaman aşımı
# ---------------------------------------------------------------------------

def test_bosta_kalan_motor_bosaltiliyor() -> None:
    eh._ENGINES["bosta"] = _engine(last_used=time.monotonic() - eh.IDLE_UNLOAD_SECONDS - 1)

    assert eh._idle_sweep() == ["bosta"]
    assert "bosta" not in eh._ENGINES


def test_YENI_kullanilan_motor_bosaltilmiyor() -> None:
    eh._ENGINES["taze"] = _engine(last_used=time.monotonic())

    assert eh._idle_sweep() == []
    assert "taze" in eh._ENGINES


def test_bosta_suresi_bir_sohbet_turundan_uzun() -> None:
    """Tur arasında boşaltmak, her cümlede yeniden yükleme demek.

    Ölçüldü: StyleTTS 2 ilk yükleme 17,56 sn. Kısa bir zaman aşımı
    çözdüğünden çok sorun üretirdi.
    """
    assert eh.IDLE_UNLOAD_SECONDS >= 120


def test_izleyici_TEK_ve_daemon() -> None:
    """İki izleyici iki kat tarama ve yarış demek."""
    eh._ensure_idle_watcher()
    first = eh._IDLE_THREAD
    eh._ensure_idle_watcher()

    assert eh._IDLE_THREAD is first
    assert first is not None and first.daemon


# ---------------------------------------------------------------------------
# Ölçüm çökerse
# ---------------------------------------------------------------------------

def test_VRAM_olculemezse_tahliye_yapilmiyor(monkeypatch) -> None:
    """Ölçemediğimiz bir durumda çalışan motorları durdurmak zarar verir.

    Sayı sınırı yine geçerli; kesilen yalnızca BELLEK kaynaklı tahliye.
    """
    import fool.gpu_budget as gb

    def _boom():
        raise OSError("nvidia-smi yok")

    monkeypatch.setattr(gb, "free_vram_mb", _boom)
    eh._ENGINES["tek"] = _engine(last_used=1.0)

    eh._evict_for("tek")  # kendisi -- sayi siniri tetiklenmiyor

    assert "tek" in eh._ENGINES


def test_bos_kayitta_cokmuyor() -> None:
    assert eh._evict_for("herhangi") == []
    assert eh._idle_sweep() == []


# ---------------------------------------------------------------------------
# Seçili motor daha uzun yaşıyor
# ---------------------------------------------------------------------------

def test_BES_DAKIKA_sessizlikten_sonra_birakiliyor(monkeypatch) -> None:
    """Kullanıcının istediği politika: beş dakika kullanılmazsa kapansın.

    Sayaç HER kullanımda sıfırlanıyor (``last_used``), yani sürekli konuşulan
    bir oturumda motor hiç boşalmıyor -- beş dakika SESSİZLİKTEN sonra
    bırakılıyor.

    Ölçüldü (ürün yolu, Chatterbox Turbo): sıcak 0,78 sn/cümle, soğuk
    13,08 sn.
    """
    import time

    from fool import engine_host as eh

    monkeypatch.setattr(eh, "_selected_engine", lambda: "chatterbox")
    stopped: list[str] = []
    monkeypatch.setattr(eh, "_stop_locked", lambda name: stopped.append(name))

    now = time.monotonic()

    class _E:
        def __init__(self, age):
            self.lock = threading.Lock()
            self.last_used = now - age

    # Dort dakika: HENUZ degil. Alti dakika: birakiliyor.
    monkeypatch.setattr(eh, "_ENGINES", {"chatterbox": _E(240)})
    assert eh._idle_sweep() == []

    monkeypatch.setattr(eh, "_ENGINES", {"chatterbox": _E(360)})
    assert eh._idle_sweep() == ["chatterbox"]


def test_SECILI_ve_digerleri_AYNI_esikte(monkeypatch) -> None:
    """Seçili olmayan bir motorun kartı daha uzun tutmasının sebebi yok."""
    from fool import engine_host as eh

    assert eh.SELECTED_IDLE_UNLOAD_SECONDS == eh.IDLE_UNLOAD_SECONDS == 300.0


def test_SECILI_motor_da_SONSUZA_kadar_tutmuyor(monkeypatch) -> None:
    """Kullanıcı gerçekten başka işe geçtiyse kart bırakılıyor."""
    import time

    from fool import engine_host as eh

    monkeypatch.setattr(eh, "_selected_engine", lambda: "chatterbox")
    monkeypatch.setattr(eh, "_stop_locked", lambda name: None)

    now = time.monotonic()

    class _E:
        def __init__(self, age):
            self.lock = threading.Lock()
            self.last_used = now - age

    # Bes dakikayi fazlasiyla gecti.
    monkeypatch.setattr(eh, "_ENGINES", {"chatterbox": _E(2000)})

    assert eh._idle_sweep() == ["chatterbox"]


def test_KULLANIMDAKI_motor_hicbir_esikte_kesilmiyor(monkeypatch) -> None:
    """Kilidi tutulan bir süreç süren bir sentezin ortasında; onu durdurmak
    cümleyi yarıda kesmek demek."""
    import time

    from fool import engine_host as eh

    monkeypatch.setattr(eh, "_selected_engine", lambda: "")
    monkeypatch.setattr(eh, "_stop_locked", lambda name: None)

    busy = threading.Lock()
    busy.acquire()

    class _E:
        def __init__(self):
            self.lock = busy
            self.last_used = time.monotonic() - 99_999

    monkeypatch.setattr(eh, "_ENGINES", {"kokoro": _E()})

    assert eh._idle_sweep() == []


def test_yapilandirma_okunamazsa_ESKI_davranis(monkeypatch) -> None:
    """Güvenli taraf: herkes aynı eşiğe tabi."""
    from fool import engine_host as eh
    import fool_cli.config as cfg

    def _boom(*a, **k):
        raise RuntimeError("config unreadable")

    monkeypatch.setattr(cfg, "load_config", _boom)

    assert eh._selected_engine() == ""
