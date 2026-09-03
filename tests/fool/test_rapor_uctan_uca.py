"""
Uçtan uca: yönerge -> şartname -> deliller -> taslak -> denetim -> DOCX/PDF.

Neden tek bir büyük test
------------------------
Parçaların hepsinin ayrı testi var. Buradaki soru başka: parçalar BİRLİKTE
kullanıcının iş akışını tamamlıyor mu? Ölçülen kusurların çoğu tam olarak
parçaların arasında çıktı -- sayfa sayacı tek başına doğruydu, tabloyla
başlayan bir sayfa gelene kadar; şartname tek başına doğruydu, taslağın
gömülü tür tablosuna düşmesine kadar.

Sayfa sayısı TAHMİN EDİLMİYOR
-----------------------------
Belge gerçekten basılıyor ve numaralı sayfaları sayılıyor. Bu, testin
LibreOffice'e bağlı olması demek; kurulu değilse test atlanıyor, çünkü
"sayfa sayısını ölçemedim ama muhtemelen doğrudur" demek bu raporun bütün
amacına aykırı.
"""

from __future__ import annotations

import json
import re
import subprocess
import zipfile
from pathlib import Path

import pytest

from fool.rapor import arac
from fool.rapor.pdf_cikti import donusturucu_bul
from fool.rapor.yonerge import cm, punto

FIXTURE = Path(__file__).parent / "fixtures" / "rapor"

KAYNAKLAR = (
    "kaynak_dilekce.txt",
    "kaynak_tutanak.txt",
    "kaynak_resmi_yazi.txt",
    "kaynak_mali_analiz.txt",
)

KAPAK = {
    "bakanlik": "T.C. ÖRNEK BAKANLIĞI",
    "baskanlik": "TEFTİŞ KURULU BAŞKANLIĞI",
    "baslik": "İNCELEME RAPORU",
    "konu": "Fazla çalışma ödemeleri ile temizlik hizmeti alımının incelenmesi",
    "gorev_emri_tarih": "20.02.2026",
    "gorev_emri_sayi": "2026/88",
    "rapor_tarih": "20.03.2026",
    "rapor_sayi": "2026/14",
    "ek_adedi": "4",
    "mufettis_ad": "Serkan TOPÇUOĞLU",
}

#: Kullanıcının hedefi: 12-20 sayfa, "dolu dolu".
HEDEF_EN_AZ, HEDEF_EN_COK = 12, 20


@pytest.fixture
def calisma(tmp_path, monkeypatch):
    monkeypatch.setenv("FOOL_RAPOR_TASLAK_DIR", str(tmp_path / "taslak"))
    monkeypatch.setenv("FOOL_RAPOR_SARTNAME_DIR", str(tmp_path / "sartname"))
    return tmp_path


def _cagir(ad: str, *a, **kw) -> dict:
    veri = json.loads(getattr(arac, ad)(*a, **kw))
    assert "error" not in veri, veri
    return veri


def _taslagi_kur(kimlik: str = "uctanuca") -> dict:
    """Yönergeyi öğren, delilleri bağla, gövdeyi yaz."""
    ogrenme = _cagir(
        "yonerge_ogren_arac", str(FIXTURE / "yonerge.txt"), kimlik,
        bolum_secimi="MADDE 11",
    )

    _cagir(
        "taslak_baslat", kimlik,
        tur="inceleme-raporu", sartname_kimligi=kimlik, sifirla=True,
    )

    for ad in KAYNAKLAR:
        _cagir("delil_ekle", kimlik, str(FIXTURE / ad))

    _cagir("taslak_kapak", kimlik, dict(KAPAK))

    govde = json.loads((FIXTURE / "rapor_govdesi.json").read_text(encoding="utf-8"))

    for bolum in govde["bolumler"]:
        _cagir("taslak_bolum", kimlik, bolum["baslik"], bolum["ogeler"])

    _cagir("taslak_ozet", kimlik, govde["ozet"])

    from fool.rapor import taslak as taslak_modulu

    veri = taslak_modulu.yukle(kimlik)
    veri.imza_yer, veri.imza_tarih = "Ankara", "20.03.2026"
    taslak_modulu._yaz(veri)

    return ogrenme


# ---------------------------------------------------------------------------
# Şartnamenin taslağı gerçekten yönetmesi
# ---------------------------------------------------------------------------


def test_sartname_taslagin_bolum_listesini_YONETIYOR(calisma) -> None:
    """Tür adı gömülü tabloda yok; bölümler yine de yönergeden geliyor."""
    _taslagi_kur()

    durum = _cagir("taslak_durum", "uctanuca")

    assert durum["tur"] == "inceleme-raporu"
    assert durum["sartname"] == "uctanuca"
    assert durum["beklenen_bolumler"][0] == "I. GİRİŞ"
    assert durum["eksik_bolumler"] == []


def test_kayitli_olmayan_sartname_SESSIZCE_gecilmiyor(calisma) -> None:
    """Bölüm listesi boş bir taslak, hiçbir denetimi olmayan bir rapor demek."""
    cevap = json.loads(
        arac.taslak_baslat("x", tur="inceleme", sartname_kimligi="yok-boyle")
    )

    assert "şartname bulunamadı" in cevap["error"]


def test_deliller_kunyeleriyle_baglaniyor(calisma) -> None:
    _taslagi_kur()

    liste = _cagir("delil_listesi", "uctanuca")
    turler = {d["tur"] for d in liste["deliller"]}

    # ``kart_cikar`` Turkce kucultme kullanmazsa "İFADE" hic eslesmiyor.
    assert "şikâyet dilekçesi" in turler
    assert "ifade tutanağı" in turler
    assert len(liste["deliller"]) == len(KAYNAKLAR)


def test_uygunluk_denetimi_uretimden_ONCE_temiz(calisma) -> None:
    _taslagi_kur()

    denetim = _cagir("uygunluk_denetle", "uctanuca")

    assert denetim["uygun"], denetim["bulgular"]
    assert denetim["engel_sayisi"] == 0


def test_engelli_taslak_URETILMIYOR(calisma) -> None:
    """Yanlış bir resmî evrak üretmek, üretmemekten kötü: dosyaya düşen imzalanıyor."""
    _taslagi_kur()

    # Sonuc bolumunden kesin ifadeyi de kapanisi da kaldir.
    _cagir(
        "taslak_bolum", "uctanuca", "V. SONUÇ",
        [{"tur": "paragraf", "metin": "İnceleme tamamlanmıştır.", "ek": "Ek: 1/1"}],
    )

    cevap = json.loads(
        arac.taslak_uret("uctanuca", str(calisma / "olmamali.docx"))
    )

    assert "error" in cevap
    assert not (calisma / "olmamali.docx").exists()
    assert {b["alan"] for b in cevap["engeller"]} >= {"kapanış", "sonuç ifadesi"}


# ---------------------------------------------------------------------------
# Gerçek belge üretimi -- dönüştürücü gerektiriyor
# ---------------------------------------------------------------------------


@pytest.mark.skipif(donusturucu_bul() is None, reason="LibreOffice yok")
def test_uctan_uca_DOCX_ve_PDF_uretiliyor_ve_sayfa_araligi_TUTUYOR(calisma) -> None:
    """Kullanıcının iş akışının tamamı, ölçülmüş sayfa sayısıyla."""
    _taslagi_kur()

    docx = calisma / "inceleme-raporu.docx"
    uretim = _cagir("taslak_uret", "uctanuca", str(docx))

    assert docx.exists()

    # --- Sayfa sayisi TAHMIN degil OLCUM ---
    sayfa = uretim["metin_sayfasi"]
    assert HEDEF_EN_AZ <= sayfa <= HEDEF_EN_COK, f"rapor {sayfa} sayfa"

    denetim = uretim["sayfa_denetimi"]
    assert denetim["olculdu"] and denetim["uygun"]
    assert denetim["hedef"] == f"{HEDEF_EN_AZ}-{HEDEF_EN_COK}"

    # --- Bagimsiz sayfa denetimi ayni sonucu vermeli ---
    tekrar = _cagir("sayfa_denetle", str(docx), kimlik="uctanuca")
    assert tekrar["sayfa"] == sayfa

    # --- PDF ---
    pdf = _cagir("rapor_pdf", str(docx))
    assert Path(pdf["pdf"]).exists()

    # --- Uretilen PDF'te sayfa numaralari 1/N .. N/N ---
    ham = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", pdf["pdf"], "-"],
        capture_output=True, stdin=subprocess.DEVNULL, check=False,
    ).stdout.decode("utf-8", "replace")

    # Sayfa sayfa aranıyor: ``^`` satır başını tutuyor ama sayfa ayracı
    # form feed ve ondan sonrası satır başı SAYILMIYOR -- birleşik metinde
    # aranınca sayfaların çoğunun numarası kaçıyor.
    kalip = re.compile(r"^[ \t]*(\d+)\s*/\s*(\d+)", re.MULTILINE)
    numaralar = [kalip.search(s) for s in ham.split("\f")]
    bulunan = [(int(m.group(1)), int(m.group(2))) for m in numaralar if m]

    assert [n for n, _ in bulunan] == list(range(1, sayfa + 1))
    # Paydanin TAMAMI dogru olmali: "12/10" yazan bir belge yonergeye aykiri.
    assert {t for _, t in bulunan} == {sayfa}


@pytest.mark.skipif(donusturucu_bul() is None, reason="LibreOffice yok")
def test_uretilen_belgenin_bicimi_YONERGEDEN_geliyor(calisma) -> None:
    """Biçim modelin dikkatine değil, şartnameye bağlı."""
    _taslagi_kur()

    docx = calisma / "bicim.docx"
    _cagir("taslak_uret", "uctanuca", str(docx))

    with zipfile.ZipFile(docx) as paket:
        belge = paket.read("word/document.xml").decode()
        stiller = paket.read("word/styles.xml").decode()
        ustbilgi = paket.read("word/header1.xml").decode()

    pg_mar = re.search(r"<w:pgMar[^>]*>", belge).group()

    assert f'w:left="{cm(2.5)}"' in pg_mar
    assert f'w:right="{cm(1.5)}"' in pg_mar
    assert f'w:top="{cm(1.5)}"' in pg_mar
    assert f'w:bottom="{cm(3.0)}"' in pg_mar
    assert '<w:pgSz w:w="11906" w:h="16838"/>' in belge
    assert 'w:ascii="Times New Roman"' in stiller
    assert f'<w:sz w:val="{punto(12)}"/>' in stiller
    assert '<w:jc w:val="both"/>' in stiller
    # Sayfa toplami SABITLENMIS olmali; alan olarak kalirsa LibreOffice
    # "1" hesaplar ve yonergenin "1/30" bicimi yanlis cikar.
    assert "SECTIONPAGES" not in ustbilgi
