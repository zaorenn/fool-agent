"""
Eşlemesi bozuk PDF'ten metni geri kazanma.

Ölçülen olay: kullanıcının 72 sayfalık rehberinde küçük "i" harfi hiçbir
çıkarıcıyla gelmiyordu. Glif sayfada duruyor, yalnızca Unicode karşılığı
bildirilmemiş -- 218.215 karakterin 17.190'ı (%7,9, Türkçede 'i'nin beklenen
sıklığı) metni boş bir karakter olarak okunuyor.

Bağlamların hepsi 'i' çıktı: "Ülkem[?]zde", "Mehmet Ak[?]f", "Koord[?]natör",
"d[?]kkat ed[?]lmes[?]".
"""

from __future__ import annotations

import os

import pytest

from fool.rapor import pdf_kurtar
from fool.rapor.kaynak import kalite_olc

# Rehberden alinmis gercek bir paragraf.
GERCEK = (
    "Memur disiplin rejiminin genel çerçevesi yasal düzenleme ile "
    "belirlenmiştir. Ayrıca ilgili yönetmeliklerle de memur disiplin "
    "hukukunun usul ve esasları düzenleme altına alınmıştır. Nitekim kamu "
    "hizmetinin etkin ve verimli yürütülmesi için yapılan disiplin "
    "soruşturmalarında ve tayin edilecek cezalarda temel ilkelere riayet "
    "edilmesi hukuk devletinin bir gereğidir."
)


def _sayfalar_yap(metin: str) -> list[list[list[str | None]]]:
    """``_ham_sayfalar``ın ürettiği yapı: 'i' harfleri eşlemesiz (``None``)."""
    return [
        [[None if k == "i" else k for k in satir] for satir in [list(metin)]]
    ]


def test_bos_glifler_TURKCE_puanlamayla_i_secip_kurtariliyor(monkeypatch) -> None:
    yapi = _sayfalar_yap(GERCEK * 3)
    bos = sum(1 for satir in yapi[0] for k in satir if k is None)

    monkeypatch.setattr(
        pdf_kurtar, "_ham_sayfalar", lambda yol: (yapi, bos, len(GERCEK) * 3)
    )

    sonuc = pdf_kurtar.kurtar("sahte.pdf")

    assert sonuc.secilen_harf == "i"
    assert "disiplin" in sonuc.metin
    # Dogru aday, yanlislari acik ara geciyor.
    assert sonuc.puanlar["i"] > sonuc.puanlar["ı"]
    assert sonuc.puanlar["i"] > sonuc.puanlar["l"]


def test_kurtarilan_metin_KALITE_denetiminden_geciyor(monkeypatch) -> None:
    """Kurtarma işe yaradıysa metin artık modele verilebilir olmalı."""
    yapi = _sayfalar_yap(GERCEK * 3)
    bos = sum(1 for satir in yapi[0] for k in satir if k is None)
    monkeypatch.setattr(
        pdf_kurtar, "_ham_sayfalar", lambda yol: (yapi, bos, len(GERCEK) * 3)
    )

    sonuc = pdf_kurtar.kurtar("sahte.pdf")

    kalite_once = kalite_olc(GERCEK.replace("i", "") * 3)
    kalite_sonra = kalite_olc(sonuc.metin)

    assert not kalite_once.guvenilir
    assert kalite_sonra.guvenilir


def test_HICBIR_aday_tutmuyorsa_DEGISTIRILMIYOR(monkeypatch) -> None:
    """Bilinmeyen bir glifi rastgele harfe çevirmek, bozuğu düzelmiş göstermek olur.

    Bu belgeler imzalanıyor; "düzeltilmiş gibi" en kötü sonuç.
    """
    yapi = [[[None if k == "x" else k for k in list("qqq xqq zzz xww kkk x")]]]
    monkeypatch.setattr(pdf_kurtar, "_ham_sayfalar", lambda yol: (yapi, 3, 21))

    sonuc = pdf_kurtar.kurtar("sahte.pdf")

    assert sonuc.secilen_harf == ""
    assert "Türkçe" not in sonuc.aciklama() or "bulunmadı" in sonuc.aciklama()


def test_esleme_eksigi_YOKSA_hicbir_sey_yapilmiyor(monkeypatch) -> None:
    yapi = [[list(GERCEK)]]
    monkeypatch.setattr(pdf_kurtar, "_ham_sayfalar", lambda yol: (yapi, 0, len(GERCEK)))

    sonuc = pdf_kurtar.kurtar("sahte.pdf")

    assert sonuc.secilen_harf == ""
    assert sonuc.bos_glif == 0
    assert "bulunmadı" in sonuc.aciklama()


def test_aciklama_NE_YAPILDIGINI_soyluyor(monkeypatch) -> None:
    """Sessiz düzeltme olmamalı: kullanıcı neyin değiştiğini görmeli."""
    yapi = _sayfalar_yap(GERCEK * 3)
    bos = sum(1 for satir in yapi[0] for k in satir if k is None)
    monkeypatch.setattr(
        pdf_kurtar, "_ham_sayfalar", lambda yol: (yapi, bos, len(GERCEK) * 3)
    )

    aciklama = pdf_kurtar.kurtar("sahte.pdf").aciklama()

    assert str(bos) in aciklama
    assert "'i'" in aciklama


# ---------------------------------------------------------------------------
# Gerçek belge -- pdfminer kuruluysa
# ---------------------------------------------------------------------------

#: Gerçek belgeyle koşan sınav için YOL DIŞARIDAN veriliyor.
#:
#: Burada kullanıcının kendi yolu SABİT yazılıydı -- kullanıcı adı ve özel
#: bir belgenin başlığı dahil. Depo herkese açık; kişisel bir yolu koda
#: gömmek onu yayınlamak demek.
#:
#: Ayarlanmamışsa sınav atlanıyor: makineye özel bir dosyayı gerektirmek,
#: başka herkeste kırmızı bir sınav bırakırdı.
REHBER = os.environ.get("FOOL_TEST_PDF", "")


@pytest.mark.skipif(
    not REHBER or not pdf_kurtar.kullanilabilir(),
    reason="FOOL_TEST_PDF ayarlanmamis ya da pdfminer.six yok",
)
def test_GERCEK_rehber_kurtariliyor() -> None:
    """Kullanıcının belgesi: kurtarma öncesi okunamıyor, sonrası okunuyor."""
    import pathlib

    if not pathlib.Path(REHBER).exists():
        pytest.skip("rehber bu makinede yok")

    from fool.rapor.kaynak import oku

    belge = oku(REHBER)

    assert belge.kalite.guvenilir, belge.kalite.gerekce
    # Olculdu: 17.190 glif, %7,9 -- Turkce'de 'i' harfinin sikligi.
    assert "'i' kondu" in belge.kurtarma_aciklamasi
    assert "DEVLET SU İŞLERİ GENEL MÜDÜRLÜĞÜ" in belge.metin
    assert belge.metin.count("disiplin") > 100
