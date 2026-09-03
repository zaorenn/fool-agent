"""Piper, espeak verisini DERLEME MAKİNESİNİN yolunda aramamalı.

Ölçülen hata (kullanıcının ikinci makinesi, temiz kurulum)::

    Error processing file 'D:/a/piper1-gpl/piper1-gpl/_skbuild/win-amd64-3.9/
      cmake-build/espeak_ng-install/share/espeak-ng-data/phontab':
      No such file or directory.
    The Fool backend exited (1)

``D:/a/piper1-gpl/...`` bir GitHub Actions koşucusunun yolu; espeak-ng tekerleğe
derlenirken gömülmüş. Veri paketin içinde geliyor, eksik olan ADRES.

Sonucu ağırdı: TTS başarısız olmakla kalmıyor, ARKA UCU düşürüyordu -- yani ses
seçimi yüzünden sohbet de, oturumlar da gidiyordu.
"""

from __future__ import annotations

import os
import sys

import pytest

from tools.tts_tool import (
    _ascii_safe_path,
    _point_espeak_at_bundled_data,
    _refuse_piper_on_unreadable_espeak_path,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("ESPEAK_DATA_PATH", raising=False)


def test_paketteki_veri_yolu_AYARLANIYOR(monkeypatch, tmp_path) -> None:
    try:
        import piper
    except ImportError:
        piper = type(sys)("piper")
        piper.__file__ = str(tmp_path / "piper" / "__init__.py")
        monkeypatch.setitem(sys.modules, "piper", piper)
        (tmp_path / "piper" / "espeak-ng-data").mkdir(parents=True)
        (tmp_path / "piper" / "espeak-ng-data" / "phontab").write_text("x", encoding="utf-8")

    _point_espeak_at_bundled_data()

    path = os.environ.get("ESPEAK_DATA_PATH")

    assert path
    assert os.path.isfile(os.path.join(path, "phontab"))


def test_KULLANICININ_CALISAN_ayari_ezilmiyor(monkeypatch, tmp_path) -> None:
    """Kendi espeak kurulumunu gösteren birinin kararını geri almak,
    düzeltilen hatanın aynası olurdu -- ama gösterdiği yer ÇALIŞIYORSA.

    ``phontab`` konuyor: gerçek bir espeak veri dizininde o dosya vardır.
    """
    (tmp_path / "phontab").write_text("x", encoding="utf-8")
    monkeypatch.setenv("ESPEAK_DATA_PATH", str(tmp_path))

    _point_espeak_at_bundled_data()

    assert os.environ["ESPEAK_DATA_PATH"] == str(tmp_path)


def test_GECERSIZ_ayar_duzeltiliyor(monkeypatch, tmp_path) -> None:
    """Çalışmayan bir yola "kullanıcı öyle istedi" diye sadık kalmak,
    uygulamayı on saniyede bir kapatmak demek.

    Bir yol geçersizleşebiliyor: venv yeniden kuruldu, kurulum taşındı, ya da
    kullanıcı geçici bir çözüm olarak kalıcı bir ortam değişkeni yazdı ve o yol
    sonradan kayboldu. espeak-ng veri yüklemesi başarısız olunca C tarafında
    ``exit()`` çağırıyor -- yani bedeli bütün arka uç.
    """
    try:
        import piper
    except ImportError:
        piper = type(sys)("piper")
        piper.__file__ = str(tmp_path / "piper" / "__init__.py")
        monkeypatch.setitem(sys.modules, "piper", piper)
        (tmp_path / "piper" / "espeak-ng-data").mkdir(parents=True)
        (tmp_path / "piper" / "espeak-ng-data" / "phontab").write_text("x", encoding="utf-8")

    monkeypatch.setenv("ESPEAK_DATA_PATH", str(tmp_path / "yok-boyle-bir-yer"))

    _point_espeak_at_bundled_data()

    resolved = os.environ["ESPEAK_DATA_PATH"]

    assert resolved != str(tmp_path / "yok-boyle-bir-yer"), "gecersiz yol korunmus"
    assert os.path.isfile(os.path.join(resolved, "phontab")), "duzeltilen yol da calismiyor"


def test_YARIM_klasor_gosterilmiyor(monkeypatch, tmp_path) -> None:
    """Boş bir klasörü göstermek, hiçbir şey göstermemekle aynı hatayı verir --
    o yüzden klasörün kendisi değil ``phontab`` sınanıyor."""
    try:
        import piper
    except ImportError:
        piper = type(sys)("piper")
        monkeypatch.setitem(sys.modules, "piper", piper)

    monkeypatch.setattr(piper, "__file__", str(tmp_path / "piper" / "__init__.py"), raising=False)
    (tmp_path / "piper" / "espeak-ng-data").mkdir(parents=True)

    _point_espeak_at_bundled_data()

    assert os.environ.get("ESPEAK_DATA_PATH") is None


def test_piper_ice_aktarilirken_CAGIRILIYOR() -> None:
    """Ayarın sentezden önce yapılması gerekiyor; içe aktarma tek geçit."""
    from pathlib import Path

    source = Path("tools/tts_tool.py").read_text(encoding="utf-8")
    body = source[source.index("def _import_piper"):]

    assert body.index("_point_espeak_at_bundled_data()") < body.index("from piper import PiperVoice")


# ---------------------------------------------------------------------------
# ASCII olmayan yol: espeak-ng dosyayı açamıyor ve SÜRECİ öldürüyor
# ---------------------------------------------------------------------------


def test_TURKCE_kullanici_adi_kisa_yola_cevriliyor(tmp_path) -> None:
    r"""Ölçülen hata (kullanıcının laptopu, kullanıcı adı ``Birhan Oğurlu``)::

        Error processing file '...piper\espeak-ng-data\phontab':
          Illegal byte sequence.
        The Fool backend exited (1)

    Yol DOĞRU, dosya YERİNDE -- taşınamayan şey ``ğ``. espeak-ng bir C
    kütüphanesi; yolu bayt olarak alıyor ve kod sayfası dönüşümü karakteri
    bozuyor (günlükte ``Birhan Oï¿½urlu``).

    Windows'un 8.3 kısa adı saf ASCII ve aynı dizini gösteriyor.
    """
    if sys.platform != "win32":
        pytest.skip("8.3 kisa yol yalnizca Windows'ta var")

    turkish = tmp_path / "Birhan Oğurlu"
    turkish.mkdir()
    (turkish / "phontab").write_text("x", encoding="utf-8")

    safe = _ascii_safe_path(str(turkish))

    assert safe.isascii(), "yol hala ASCII degil -- espeak yine acamaz"
    assert os.path.isfile(os.path.join(safe, "phontab")), "kisa yol ayni dizini gostermiyor"


def test_ASCII_yola_dokunulmuyor() -> None:
    """Çevirinin bedeli var (kısa adlar okunaksız); sorunu olmayan makinede
    ödenmemeli."""
    plain = os.path.join(os.sep, "ascii", "path")

    assert _ascii_safe_path(plain) == plain


def test_cevrilemeyen_yolda_piper_YUKLENMIYOR(monkeypatch) -> None:
    """Bir motorun başarısızlığı ÜRÜNÜ düşürmemeli.

    espeak-ng veri yüklemesi başarısız olduğunda C tarafında ``exit()``
    çağırıyor -- hiçbir ``try/except`` yakalayamaz, arka uç komple ölür.
    Kullanıcının gördüğü: on saniyede bir kapanan uygulama, ECONNRESET,
    "gateway checking -> offline", %1'de donan indirmeler.

    Karar bu yüzden YÜKLEMEDEN ÖNCE veriliyor ve sıradan bir Python hatası
    olarak yükseliyor: ses çalışmaz, ama sohbet ve oturumlar ayakta kalır.
    """
    if sys.platform != "win32":
        pytest.skip("kapi Windows'a ozel")

    monkeypatch.setenv("ESPEAK_DATA_PATH", os.path.join("C:", "Birhan Oğurlu", "espeak"))

    with pytest.raises(RuntimeError, match="non-ASCII"):
        _refuse_piper_on_unreadable_espeak_path()


def test_ASCII_yolda_kapi_ACIK(monkeypatch) -> None:
    monkeypatch.setenv("ESPEAK_DATA_PATH", os.path.join(os.sep, "ascii", "espeak"))

    _refuse_piper_on_unreadable_espeak_path()
