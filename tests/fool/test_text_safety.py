"""İşletim sisteminden gelen metin UTF-8 olmayabilir.

Ölçülen çöküş (kullanıcının ağ geçidi kayıtlarından, birebir):

    UnicodeEncodeError: 'utf-8' codec can't encode character (U+DCFC)
    in position 1: surrogates not allowed

    agent/conversation_loop.py::_restore_or_build_system_prompt
      -> run_agent.py::_build_system_prompt
        -> agent/system_prompt.py::build_system_prompt_parts
          -> now.strftime("%Z")

Windows saat dilimi adını sistemin ANSI kod sayfasında veriyor; bu makinede
cp1254 ve ad ``Türkiye Standart Saati``. ``ü`` = 0xFC baytı, Python onu
çözemeyince ``surrogateescape`` uyguluyor ve U+DCFC kalıyor.

Patladığı yer sistem promptunun kurulduğu yer, yani ajan turu HİÇ
başlamıyordu. Ağ geçidinin çökme kaydında altı kez var.
"""

from __future__ import annotations

import pytest

from fool.text_safety import has_surrogates, safe_os_text

#: cp1254'te "Türkiye Standart Saati" -- ``ü`` baytı çözülemeden kalmış hâli.
TAINTED = "T\udcfcrkiye Standart Saati"


def test_kirli_dize_gercekten_KODLANAMIYOR() -> None:
    """Sınavın dayandığı olgu: bu dize UTF-8'e kodlanamıyor."""
    with pytest.raises(UnicodeEncodeError):
        TAINTED.encode("utf-8")


def test_has_surrogates_yakaliyor() -> None:
    assert has_surrogates(TAINTED)
    assert not has_surrogates("Türkiye Standart Saati")
    assert not has_surrogates("")


def test_temiz_metin_DEGISMEDEN_donuyor() -> None:
    """Sıcak yol: vekil yoksa dokunulmuyor."""
    for value in ("UTC", "Türkiye Standart Saati", "+03", "GMT+3"):
        assert safe_os_text(value) == value


def test_sonuc_HER_ZAMAN_kodlanabiliyor() -> None:
    """Asıl sözleşme. Ne dönerse dönsün, prompt artık düşmüyor."""
    for value in (TAINTED, "\udc80\udcff", "a\udcfcb", "\udcfc"):
        safe_os_text(value).encode("utf-8")


def test_ad_KURTARILIYOR_silinmiyor() -> None:
    """Vekiller kayıp bilgi değil: orijinal baytlar dizenin içinde.

    Sadece silmek, Türkçe bir kurulumda saat diliminin adını sessizce yok
    etmek olurdu.
    """
    recovered = safe_os_text(TAINTED)

    assert not has_surrogates(recovered)
    # cp1254/cp1252/latin-1 hepsi 0xFC -> "ü" veriyor.
    assert recovered == "Türkiye Standart Saati"


def test_kurtarilamayan_bayt_DUSURULUYOR() -> None:
    """Promptun hiç kurulamamasındansa eksik bir kısaltma kabul edilir."""
    result = safe_os_text("\udc80\udc81")

    assert not has_surrogates(result)
    result.encode("utf-8")


def test_bos_ve_dize_olmayan_girdi_COKMUYOR() -> None:
    assert safe_os_text("") == ""
    assert safe_os_text(None) == ""


# ---------------------------------------------------------------------------
# Gerçek çağrı yolu
# ---------------------------------------------------------------------------

def test_KIRLI_saat_dilimi_promptu_DUSURMUYOR() -> None:
    """Dikişin gerçekten çözdüğü şey.

    ``datetime.datetime`` değiştirilemez bir tip, yani ``strftime``
    yamanamıyor -- o yüzden dikişin yaptığı işin AYNISI burada koşuyor:
    işletim sisteminden gelen kirli değeri temizle ve kodlanabildiğini
    doğrula. Temizlemeden bu satır ``UnicodeEncodeError`` ile düşüyordu ve
    düştüğü yer sistem promptunun kurulduğu yerdi.
    """
    # Ham deger: prompt kurulumunun eski hali.
    with pytest.raises(UnicodeEncodeError):
        f"Conversation started: Thursday ({TAINTED})".encode("utf-8")

    # Dikisin hali: kuruluyor.
    cleaned = safe_os_text(TAINTED)

    assert f"Conversation started: Thursday ({cleaned})".encode("utf-8")


def test_dikis_YERINDE_ve_dogru_islevi_cagiriyor() -> None:
    """Bir merge dikişi yutarsa burada yakalanır."""
    from pathlib import Path

    source = Path(__file__).resolve().parents[2] / "agent" / "system_prompt.py"
    text = source.read_text(encoding="utf-8")

    assert "FOOL-SEAM: os-text-encoding" in text
    assert "safe_os_text(now.strftime" in text
    # Ham cagri GERI GELMEMELI.
    assert "_abbrev = now.strftime(\"%Z\")" not in text
