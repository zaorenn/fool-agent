"""Ayarların ses bölümü her açılışta 27 saniye bekletiyordu.

Ölçüldü (bu makine, dokuz katalog öğesi):

    önbelleksiz + sırayla : 27,63 sn
    önbellekli  + paralel :  3,72 sn (soğuk) / 0,19 sn (sıcak)

Maliyetin tamamı alt süreç: her sidecar motorunun CUDA sondası izole bir
yorumlayıcıda ``import torch`` yapıyor. Kullanıcının bildirdiği "ayarlardaki
ses kısmı geç yükleniyor" tam olarak buydu.

Önbelleğin tehlikeli tarafı ESKİ CEVAP: kullanıcı CUDA çalışma zamanını
kurduktan sonra panel hâlâ "CPU" diyorsa, kurulumun işe yaramadığını sanır.
Testlerin çoğu o yönü tutuyor.
"""

from __future__ import annotations

import pytest

from fool import cuda_probe_cache as cache


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Önbellek dosyası testin kendi dizininde -- gerçek kurulum bozulmasın."""
    monkeypatch.setenv("FOOL_HOME", str(tmp_path))
    monkeypatch.setattr("fool_constants.get_hermes_home", lambda: str(tmp_path))
    cache.invalidate()
    yield
    cache.invalidate()


class _Counter:
    """Sondanın KAÇ KEZ koştuğunu sayıyor -- ölçtüğümüz şey bu."""

    def __init__(self, answer: bool = True) -> None:
        self.answer = answer
        self.calls = 0

    def __call__(self) -> bool:
        self.calls += 1
        return self.answer


def _pin(monkeypatch, mark: str) -> None:
    monkeypatch.setattr(cache, "fingerprint", lambda name: mark)


# ---------------------------------------------------------------------------
# Asıl kazanç
# ---------------------------------------------------------------------------

def test_ikinci_cagri_sondayi_KOSTURMUYOR(monkeypatch) -> None:
    _pin(monkeypatch, "torch:1")
    probe = _Counter()

    assert cache.cached("kokoro", probe) is True
    assert cache.cached("kokoro", probe) is True
    assert probe.calls == 1


def test_YENI_surecte_de_hatirliyor(monkeypatch) -> None:
    """Bellek içi önbellek yetmezdi: panel ayrı bir pencere ve ağ geçidi
    yeniden başlıyor. Süreç ömrüne bağlı bir önbellek ilk açılışta aynı
    beklemeyi geri getirirdi."""
    _pin(monkeypatch, "torch:1")
    cache.cached("kokoro", _Counter())

    cache._MEMO.clear()  # sureci yeniden baslatmis gibi
    probe = _Counter()

    assert cache.cached("kokoro", probe) is True
    assert probe.calls == 0, "disk onbellegi okunmadi"


def test_motorlar_BIRBIRINDEN_bagimsiz(monkeypatch) -> None:
    monkeypatch.setattr(cache, "fingerprint", lambda name: f"{name}:1")

    assert cache.cached("kokoro", _Counter(True)) is True
    assert cache.cached("chatterbox", _Counter(False)) is False


def test_OLUMSUZ_cevap_da_saklaniyor(monkeypatch) -> None:
    """Yalnızca "evet"i saklamak, CPU derlemeli motorlarda beklemeyi
    bırakırdı -- oysa asıl yavaş olan onlar."""
    _pin(monkeypatch, "torch:1")
    probe = _Counter(False)

    assert cache.cached("kokoro", probe) is False
    assert cache.cached("kokoro", probe) is False
    assert probe.calls == 1


# ---------------------------------------------------------------------------
# Eski cevap vermemek
# ---------------------------------------------------------------------------

def test_torch_DEGISINCE_sonda_yeniden_kosuyor(monkeypatch) -> None:
    """CUDA derlemesi kurulunca panel bunu GÖRMELİ."""
    _pin(monkeypatch, "torch:cpu")
    assert cache.cached("kokoro", _Counter(False)) is False

    _pin(monkeypatch, "torch:cuda")
    probe = _Counter(True)

    assert cache.cached("kokoro", probe) is True
    assert probe.calls == 1


def test_invalidate_saklanani_UNUTUYOR(monkeypatch) -> None:
    """Parmak izi zaman damgasına dayanıyor ve çözünürlüğü düşük olabilir:
    kurulumdan hemen sonra sorulan soru eski cevabı görebilirdi."""
    _pin(monkeypatch, "torch:1")
    cache.cached("kokoro", _Counter(False))

    cache.invalidate("kokoro")
    probe = _Counter(True)

    assert cache.cached("kokoro", probe) is True
    assert probe.calls == 1


def test_invalidate_TEK_motoru_unutuyor(monkeypatch) -> None:
    monkeypatch.setattr(cache, "fingerprint", lambda name: f"{name}:1")
    cache.cached("kokoro", _Counter(True))
    cache.cached("chatterbox", _Counter(True))

    cache.invalidate("kokoro")
    other = _Counter(True)
    cache.cached("chatterbox", other)

    assert other.calls == 0, "ilgisiz motorun cevabi da silinmis"


def test_ortam_YOKSA_hic_saklanmiyor(monkeypatch) -> None:
    """Parmak izi boş = kurulum yok. O durumu saklamak, kurulumdan sonra
    "CUDA yok" demeye devam etmek olurdu."""
    _pin(monkeypatch, "")
    probe = _Counter(False)

    cache.cached("kokoro", probe)
    cache.cached("kokoro", probe)

    assert probe.calls == 2


# ---------------------------------------------------------------------------
# Bozulmaya dayanıklılık
# ---------------------------------------------------------------------------

def test_bozuk_onbellek_dosyasi_COKMUYOR(monkeypatch) -> None:
    _pin(monkeypatch, "torch:1")
    path = cache._cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{bu json degil", encoding="utf-8")
    cache._MEMO.clear()

    assert cache.cached("kokoro", _Counter(True)) is True


def test_yazilamayan_dizin_COKMUYOR(monkeypatch) -> None:
    """Önbellek yazılamadı: doğruluk etkilenmiyor, yalnızca yavaşlık geri
    geliyor. Kullanıcıya hata göstermek burada oransız olurdu."""
    _pin(monkeypatch, "torch:1")
    monkeypatch.setattr(cache, "_store", lambda data: (_ for _ in ()).throw(OSError("dolu")))

    with pytest.raises(OSError):
        cache._store({})

    monkeypatch.setattr(cache, "_store", lambda data: None)
    assert cache.cached("kokoro", _Counter(True)) is True


def test_sonda_COKERSE_yayiliyor(monkeypatch) -> None:
    """Önbellek hatayı yutmamalı: çağıran taraf kendi kararını versin."""
    _pin(monkeypatch, "torch:1")

    def _boom() -> bool:
        raise RuntimeError("sonda coktu")

    with pytest.raises(RuntimeError):
        cache.cached("kokoro", _boom)


def test_gercek_parmak_izi_KURULU_OLMAYAN_motorda_bos() -> None:
    assert cache.fingerprint("boyle-bir-motor-yok") == ""
