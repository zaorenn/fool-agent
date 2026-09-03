"""
DOCX'ten PDF üretimi.

Bu depoda F5-TTS'in bıraktığı ders var: arayüzde çalışıyormuş gibi duran ama
hiç ses üretmeyen bir motor, hiç sunulmamasından kötüydü. Dönüştürücü yoksa
burada da PDF "üretiliyormuş" gibi yapılmıyor.
"""

from __future__ import annotations

import json

import pytest

from fool.rapor import arac
from fool.rapor.pdf_cikti import donusturucu_bul, pdf_uret


def test_olmayan_belge_ACIK_hata_veriyor(tmp_path) -> None:
    sonuc = pdf_uret(tmp_path / "yok.docx")

    assert not sonuc.basarili
    assert "bulunamadı" in sonuc.gerekce


def test_donusturucu_YOKSA_uretiyormus_gibi_yapilmiyor(tmp_path, monkeypatch) -> None:
    from fool.rapor import pdf_cikti

    belge = tmp_path / "r.docx"
    belge.write_bytes(b"PK")

    monkeypatch.setattr(pdf_cikti, "donusturucu_bul", lambda: None)
    monkeypatch.setattr(pdf_cikti, "_WINDOWS_ADAYLARI", ())

    sonuc = pdf_cikti.pdf_uret(belge)

    assert not sonuc.basarili
    assert "LibreOffice" in sonuc.gerekce
    # .docx'in hazir oldugu ACIKCA soyleniyor -- is durmuyor.
    assert ".docx" in sonuc.gerekce


@pytest.mark.skipif(donusturucu_bul() is None, reason="LibreOffice yok")
def test_GERCEK_donusturme_pdf_uretiyor(tmp_path) -> None:
    import zipfile

    from fool.rapor.docx_yazici import yaz
    from fool.rapor.model import Bolum, Ek, Kapak, Rapor

    kapak = Kapak(
        bakanlik="Tarım ve Orman Bakanlığı",
        baskanlik="DSİ Teftiş Kurulu Başkanlığı",
        baslik="İnceleme Raporu", konu="Deneme",
        gorev_emri_tarih="05.03.2026", gorev_emri_sayi="1",
        rapor_tarih="01.06.2026", rapor_sayi="8-2026/1",
        ek_adedi="1", mufettis_ad="Cemil KAYA",
    )
    bolum = Bolum("I. GİRİŞ")
    bolum.paragraf("İncelemeye başlanmıştır.", ek="Ek: 1/1")
    rapor = Rapor(tur="inceleme", kapak=kapak, bolumler=[bolum],
                  ekler=[Ek(1, "Makam Onayı", 1)],
                  imza_yer="Ankara", imza_tarih="01.06.2026")

    docx = yaz(rapor, tmp_path / "r.docx")
    assert zipfile.ZipFile(docx).testzip() is None

    cevap = json.loads(arac.rapor_pdf(str(docx)))

    assert "error" not in cevap, cevap
    assert cevap["bayt"] > 1000
