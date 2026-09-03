"""
Resmî rapor DOCX üretimi -- yönergeye uygunluk.

Bu testler "açılıyor mu" diye bakmıyor; yönergenin SAYIYLA yazdığı şeyleri
sınıyor. Sebebi basit: bu belge imzalanıp devlet işine giriyor. Kenar boşluğu
2,5 yerine 2,54 olan bir rapor da açılır, ama yönergeye aykırıdır.

Kaynak: DSİ Teftiş Kurulu Başkanlığı Görev Usul ve Esaslarına İlişkin Yönerge,
MADDE 5-10 ve MADDE 17.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile

import pytest

from fool.rapor import docx_yazici as dy
from fool.rapor.model import EKSIK, Alinti, AltBaslik, Bolum, Ek, Kapak, Rapor, Tablo
from fool.rapor.yonerge import (
    KAPANIS_IFADESI,
    RAPOR_TURLERI,
    Bicim,
    ozet_sayfa_siniri,
)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _kapak() -> Kapak:
    return Kapak(
        bakanlik="Tarım ve Orman Bakanlığı",
        baskanlik="DSİ Teftiş Kurulu Başkanlığı",
        baslik="İNCELEME RAPORU",
        konu="Rücuen tazmin davalarında zamanaşımı",
        gorev_emri_tarih="10.04.2026",
        gorev_emri_sayi="7032434",
        rapor_tarih="01.06.2026",
        rapor_sayi="8-2026/1",
        ek_adedi="9",
        mufettis_ad="Birhan OĞURLU",
    )


def _rapor(**kw: object) -> Rapor:
    giris = Bolum("I. GİRİŞ")
    giris.paragraf("Makam Olur'u doğrultusunda incelemeye başlanmıştır.", ek="Ek: 1/1")

    varsayilan: dict[str, object] = {
        "tur": "inceleme",
        "kapak": _kapak(),
        "bolumler": [giris],
        "ozet": ["Kamu zararı oluşmadığı değerlendirilmiştir."],
        "ekler": [Ek(1, "Makam Onayı ve Görevlendirme Yazısı", 2)],
        "imza_yer": "Ankara",
        "imza_tarih": "01.06.2026",
    }
    varsayilan.update(kw)

    return Rapor(**varsayilan)  # type: ignore[arg-type]


@pytest.fixture
def xml() -> str:
    return dy.belge_xml(_rapor(), Bicim())


# ---------------------------------------------------------------------------
# Paket bütünlüğü
# ---------------------------------------------------------------------------


def test_docx_ACILABILIR_bir_paket(tmp_path) -> None:
    """Zip bozuksa Word hiçbir şey göstermeden reddediyor."""
    hedef = dy.yaz(_rapor(), tmp_path / "rapor.docx")

    with zipfile.ZipFile(hedef) as paket:
        assert paket.testzip() is None
        parcalar = set(paket.namelist())

    # OOXML'in zorunlu parcalari: biri eksikse belge acilmiyor.
    assert {
        "[Content_Types].xml",
        "_rels/.rels",
        "word/document.xml",
        "word/_rels/document.xml.rels",
        "word/styles.xml",
    } <= parcalar


def test_her_parca_GECERLI_XML(tmp_path) -> None:
    hedef = dy.yaz(_rapor(), tmp_path / "rapor.docx")

    with zipfile.ZipFile(hedef) as paket:
        for ad in paket.namelist():
            ET.fromstring(paket.read(ad))  # bozuksa burada patlar


def test_bildirilen_her_iliski_GERCEKTEN_var(tmp_path) -> None:
    """``r:id`` hedefi olmayan bir ilişki Word'de onarım uyarısı çıkarıyor."""
    hedef = dy.yaz(_rapor(), tmp_path / "rapor.docx")

    with zipfile.ZipFile(hedef) as paket:
        rels = ET.fromstring(paket.read("word/_rels/document.xml.rels"))
        parcalar = set(paket.namelist())
        govde = paket.read("word/document.xml").decode("utf-8")

        hedefler = {r.get("Id"): r.get("Target") for r in rels}

    for kimlik in re.findall(r'r:id="([^"]+)"', govde):
        assert kimlik in hedefler, f"{kimlik} ilanlanmamis"
        assert f"word/{hedefler[kimlik]}" in parcalar


# ---------------------------------------------------------------------------
# MADDE 8(2)-(4): şekil standartları
# ---------------------------------------------------------------------------


def test_sayfa_olcusu_ve_kenar_bosluklari_YONERGEDEKI_gibi(xml: str) -> None:
    """MADDE 8(2): A4; sol 2,5 cm, sağ/üst 1,5 cm, alt 3,0 cm."""
    kok = ET.fromstring(xml)

    for sect in kok.iter(f"{W}sectPr"):
        pg_sz = sect.find(f"{W}pgSz")
        assert pg_sz is not None
        # A4, Word'un yazdigi degerlerle birebir.
        assert pg_sz.get(f"{W}w") == "11906"
        assert pg_sz.get(f"{W}h") == "16838"

        pg_mar = sect.find(f"{W}pgMar")
        assert pg_mar is not None
        # 1 cm = 1440/2,54 twip. 2,5 cm -> 1417, 1,5 cm -> 850, 3 cm -> 1701.
        assert pg_mar.get(f"{W}left") == "1417"
        assert pg_mar.get(f"{W}right") == "850"
        assert pg_mar.get(f"{W}top") == "850"
        assert pg_mar.get(f"{W}bottom") == "1701"


def test_yazi_tipi_ve_punto_YONERGEDEKI_gibi() -> None:
    """MADDE 8(3): Times New Roman, 12 punto."""
    stiller = ET.fromstring(dy._styles(Bicim()))

    fonts = stiller.iter(f"{W}rFonts")
    assert all(f.get(f"{W}ascii") == "Times New Roman" for f in fonts)

    # 12 punto = 24 yarim-punto.
    assert [s.get(f"{W}val") for s in stiller.iter(f"{W}sz")] == ["24"]


def test_metin_IKI_YANA_YASLI_ve_paragraflar_1_cm_girintili(xml: str) -> None:
    """MADDE 8(3) blok yazım, MADDE 8(4) soldan 1 cm girinti."""
    kok = ET.fromstring(xml)

    girintiler = {
        ind.get(f"{W}firstLine") for ind in kok.iter(f"{W}ind")
    }
    # 1 cm = 567 twip. Baska bir girinti degeri kullanilmamali.
    assert girintiler == {"567"}

    hizalamalar = {jc.get(f"{W}val") for jc in kok.iter(f"{W}jc")}
    assert "both" in hizalamalar


def test_pPr_cocuklari_SEMA_SIRASINDA(xml: str) -> None:
    """``spacing`` -> ``ind`` -> ``jc``.

    Yanlis siralama Word'de cogu zaman aciliyor, o yuzden gozle fark
    edilmiyor; sema dogrulayan araclarda ise belge bozuk sayiliyor.
    """
    sira = [f"{W}spacing", f"{W}ind", f"{W}jc"]
    kok = ET.fromstring(xml)

    for ppr in kok.iter(f"{W}pPr"):
        gorulen = [c.tag for c in ppr if c.tag in sira]
        assert gorulen == sorted(gorulen, key=sira.index), gorulen


# ---------------------------------------------------------------------------
# MADDE 6(5), 8(9), 8(11): sayfa numarası hangi bölümde var
# ---------------------------------------------------------------------------


def test_sayfa_numarasi_YALNIZCA_rapor_metninde(xml: str) -> None:
    """MADDE 8(11): kapak, özet, ek dizini numaralandırmaya dâhil değil."""
    kok = ET.fromstring(xml)
    sectler = list(kok.iter(f"{W}sectPr"))
    R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

    # HER bolum ustbilgisini bildiriyor (devralmayi kesmek icin), ama
    # numarali olani (rId2) yalnizca BIRI kullaniyor: rapor metni.
    numaralilar = [
        s
        for s in sectler
        if s.find(f"{W}headerReference") is not None
        and s.find(f"{W}headerReference").get(f"{R}id") == "rId2"
    ]

    assert len(numaralilar) == 1

    metin = numaralilar[0]
    numara = metin.find(f"{W}pgNumType")
    assert numara is not None
    # MADDE 8(9): metnin ilk sayfasi 1'dir -- kapak sayilmaz.
    assert numara.get(f"{W}start") == "1"


def test_sayfa_numarasi_TOPLAMI_bolumun_kendi_sayfasi() -> None:
    """MADDE 8(9): "1/30" -- 30, metnin sayfa sayısı.

    ``NUMPAGES`` belgenin TAMAMINI sayardı ve kapak, özet, ek dizini de
    toplama girerdi; yönerge bunu açıkça yasaklıyor (MADDE 8(11)).
    """
    baslik = dy._header(Bicim())

    assert "SECTIONPAGES" in baslik
    assert "NUMPAGES" not in baslik
    assert "PAGE" in baslik


def test_sayfa_numarasi_SAG_ust_kosede() -> None:
    """MADDE 8(9): her sayfanın sağ üst kenarı."""
    baslik = ET.fromstring(dy._header(Bicim()))

    assert [jc.get(f"{W}val") for jc in baslik.iter(f"{W}jc")] == ["right"]


# ---------------------------------------------------------------------------
# MADDE 8(6), 8(8): alıntılar ve başlıklar
# ---------------------------------------------------------------------------


def test_aynen_alinti_TIRNAK_ICINDE_ve_ITALIK() -> None:
    """MADDE 8(6): başka belgeden alıntılar tırnak içinde ve italik."""
    bolum = Bolum("IV. TARTIŞMA VE DEĞERLENDİRME")
    bolum.ogeler.append(
        Alinti("her alacak on yıllık zamanaşımına tabidir", kaynak="TBK m.146")
    )

    kok = ET.fromstring(dy.belge_xml(_rapor(bolumler=[bolum]), Bicim()))

    for para in kok.iter(f"{W}p"):
        metinler = [t.text or "" for t in para.iter(f"{W}t")]
        if any("zamanaşımına tabidir" in m for m in metinler):
            assert para.find(f".//{W}i") is not None, "alinti italik degil"
            assert any(m.startswith("“") and m.endswith("”") for m in metinler)
            break
    else:
        pytest.fail("alinti paragrafi bulunamadi")


def test_bolum_baslıklari_TAMAMEN_BUYUK_ve_koyu() -> None:
    """MADDE 8(8): bölüm başlıkları büyük harf, alt başlıklar koyu."""
    bolum = Bolum("iii. inceleme ve araştırma")
    bolum.ogeler.append(AltBaslik("Cevaplı Teftiş Raporu Madde 2 Açısından"))

    kok = ET.fromstring(dy.belge_xml(_rapor(bolumler=[bolum]), Bicim()))
    metinler = [t.text or "" for t in kok.iter(f"{W}t")]

    # Kucuk harfle verilse bile BUYUK yaziliyor: bicim uretilmiyor, uygulaniyor.
    assert "III. İNCELEME VE ARAŞTIRMA" in metinler
    assert "Cevaplı Teftiş Raporu Madde 2 Açısından" in metinler


def test_turkce_karakterler_BOZULMADAN_geciyor(tmp_path) -> None:
    """Şğüıöç ve İ -- cp1254/utf-8 karışması bu belgede en görünür hata."""
    bolum = Bolum("II. KONU")
    bolum.paragraf("Şüphelinin ifadesi alınmış, çağrı yapılmıştır. İĞÜŞÖÇ")

    hedef = dy.yaz(_rapor(bolumler=[bolum]), tmp_path / "tr.docx")

    with zipfile.ZipFile(hedef) as paket:
        govde = paket.read("word/document.xml").decode("utf-8")

    assert "Şüphelinin ifadesi alınmış, çağrı yapılmıştır. İĞÜŞÖÇ" in govde


# ---------------------------------------------------------------------------
# MADDE 9, MADDE 10: ekler
# ---------------------------------------------------------------------------


def test_ek_dizini_her_ekin_NUMARASINI_SAYFASINI_ICERIGINI_gosteriyor() -> None:
    """MADDE 9(1)."""
    rapor = _rapor(
        ekler=[
            Ek(1, "Makam Onayı ve Görevlendirme Yazısı", 2),
            Ek(2, "Cevaplı Teftiş Raporu", 3),
        ]
    )
    metinler = [
        t.text or "" for t in ET.fromstring(dy.belge_xml(rapor, Bicim())).iter(f"{W}t")
    ]

    assert "EK DİZİNİ" in metinler
    for beklenen in ("1", "2", "3", "Makam Onayı ve Görevlendirme Yazısı"):
        assert beklenen in metinler


def test_metindeki_ek_atfi_PARANTEZ_ICINDE() -> None:
    """MADDE 10(8): rapor içinde ek bilgisi "(Ek: ...)" biçiminde."""
    bolum = Bolum("I. GİRİŞ")
    bolum.paragraf("Olur doğrultusunda başlanmıştır.", ek="Ek: 1/1")

    metinler = [
        t.text or ""
        for t in ET.fromstring(
            dy.belge_xml(_rapor(bolumler=[bolum]), Bicim())
        ).iter(f"{W}t")
    ]

    assert any("(Ek: 1/1)" in m for m in metinler)


def test_tablo_SEMAYA_uygun_grid_tasiyor() -> None:
    """``w:tblGrid`` yoksa tablo bazı görüntüleyicilerde hiç çizilmiyor."""
    bolum = Bolum("IV. TARTIŞMA VE DEĞERLENDİRME")
    bolum.ogeler.append(
        Tablo("Tablo 1: Süreler", ("Madde", "Ödeme", "Süre"), [("2", "14.02.2023", "2 Yıl")])
    )

    kok = ET.fromstring(dy.belge_xml(_rapor(bolumler=[bolum]), Bicim()))
    tablolar = list(kok.iter(f"{W}tbl"))

    assert tablolar
    for tablo in tablolar:
        grid = tablo.find(f"{W}tblGrid")
        assert grid is not None, "tblGrid yok"
        # Sutun sayisi baslik sayisiyla ayni olmali.
        assert len(list(grid)) == len(list(tablo.iter(f"{W}tr"))[0])


def test_tablo_hucre_sayisi_TUTMUYORSA_yaziya_hic_girmiyor() -> None:
    """Kayık bir tablo Word'de sessizce bozuk görünür; kurulumda patlasın."""
    with pytest.raises(ValueError, match="hucre"):
        Tablo("Tablo 1", ("A", "B"), [("tek",)])


# ---------------------------------------------------------------------------
# MADDE 17: rapor bölümleri ve türleri
# ---------------------------------------------------------------------------


def test_dort_rapor_turu_de_YONERGEDEKI_bolumlere_sahip() -> None:
    """MADDE 17(1) ve 17(2)."""
    inceleme = RAPOR_TURLERI["inceleme"].bolumler
    assert list(inceleme) == [
        "I. GİRİŞ",
        "II. KONU",
        "III. İNCELEME VE ARAŞTIRMA",
        "IV. TARTIŞMA VE DEĞERLENDİRME",
        "V. SONUÇ",
    ]

    # Disiplin ve adli sorusturma AYNI iskeleti kullaniyor (MADDE 17(1)).
    assert RAPOR_TURLERI["disiplin"].bolumler == inceleme
    assert RAPOR_TURLERI["adli"].bolumler == inceleme

    # On inceleme TAMAMEN AYRI (MADDE 17(2)): 10 bolum.
    on = RAPOR_TURLERI["on_inceleme"].bolumler
    assert len(on) == 10
    assert on[1] == "II. MUHBİR VE MÜŞTEKİ"
    assert on[-1] == "X. SONUÇ"


def test_her_turun_SONUC_ifadeleri_yonergeden() -> None:
    """MADDE 17(8): sonuçta kullanılacak kesin ifadeler türe göre değişiyor."""
    assert "kamu zararı tespit edilmiştir" in RAPOR_TURLERI["inceleme"].sonuc_ifadeleri
    assert (
        "soruşturma izni verilmesi gerektiği"
        in RAPOR_TURLERI["on_inceleme"].sonuc_ifadeleri
    )
    # Disiplin raporunda ceza onerisi 657/125'e atif yapiyor; ifade kalibi bu.
    assert "disiplin cezasını gerektirdiği" in RAPOR_TURLERI["disiplin"].sonuc_ifadeleri


def test_ozet_sayfa_siniri_MADDE_7() -> None:
    """Her 30 sayfa için en fazla 1 sayfa özet."""
    assert ozet_sayfa_siniri(1) == 1
    assert ozet_sayfa_siniri(30) == 1
    assert ozet_sayfa_siniri(31) == 2
    assert ozet_sayfa_siniri(80) == 3
    assert ozet_sayfa_siniri(0) == 0


def test_kapanis_ifadesi_yonergeden() -> None:
    """MADDE 17(9): rapor bu ifadeyle sonuçlanır."""
    assert KAPANIS_IFADESI == "görüş ve kanaatine varılmıştır"


# ---------------------------------------------------------------------------
# Uydurma karşıtı: boş alan UYDURULMUYOR
# ---------------------------------------------------------------------------


def test_doldurulmamis_kapak_alanlari_RAPOR_EDILIYOR() -> None:
    """Resmî evrakta uydurulmuş bir sayı, boş bir alandan çok daha kötü."""
    eksikler = Rapor(tur="inceleme", kapak=Kapak()).eksikler()

    assert "Görev emri sayısı" in eksikler
    assert "Müfettiş adı" in eksikler
    assert "Rapor tarihi" in eksikler


def test_metinde_kalan_EKSIK_isareti_de_rapor_ediliyor() -> None:
    """Model bir alanı dolduramadıysa bu imzadan önce görülmeli."""
    bolum = Bolum("II. KONU")
    bolum.paragraf(f"{EKSIK} tarihli yazı ile bilgi istenmiştir.")

    eksikler = _rapor(bolumler=[bolum]).eksikler()

    assert any("doldurulmamış alan" in e for e in eksikler)


def test_eksigi_olmayan_rapor_TEMIZ() -> None:
    assert _rapor().eksikler() == []


# ---------------------------------------------------------------------------
# Türkçe büyük harf -- ölçülmüş bir hata
# ---------------------------------------------------------------------------


def test_buyuk_harf_TURKCE_kurallariyla() -> None:
    """``str.upper()`` "Teftiş"i "TEFTIŞ" yapıyordu -- kurumun kendi adı yanlış.

    Bu, biçimi doğru ama içeriği yanlış bir resmî evrak üretiyordu: belge
    açılıyor, kenar boşluğu tutuyor, başlıkta "DSİ TEFTIŞ KURULU" yazıyor.
    """
    from fool.rapor.turkce import baslik, buyuk, kucuk

    assert buyuk("DSİ Teftiş Kurulu Başkanlığı") == "DSİ TEFTİŞ KURULU BAŞKANLIĞI"
    # Noktasiz i'nin buyugu noktasiz I.
    assert buyuk("Tarım ve Orman Bakanlığı") == "TARIM VE ORMAN BAKANLIĞI"
    assert buyuk("ılık ışık") == "ILIK IŞIK"
    assert kucuk("İSTANBUL IĞDIR") == "istanbul ığdır"
    assert baslik("cevaplı teftiş raporu") == "Cevaplı Teftiş Raporu"


def test_bolum_basligindaki_ROMA_RAKAMI_bozulmuyor() -> None:
    """Türkçe kuralı Roma rakamına uygulanırsa "iii." -> "İİİ." oluyor."""
    from fool.rapor.turkce import bolum_basligi

    assert bolum_basligi("iii. inceleme ve araştırma") == "III. İNCELEME VE ARAŞTIRMA"
    assert bolum_basligi("VIII. hakkında ön inceleme yapılanların ifadeleri") == (
        "VIII. HAKKINDA ÖN İNCELEME YAPILANLARIN İFADELERİ"
    )
    # Roma rakami olmayan baslik normal Turkce kuraliyla buyuyor.
    assert bolum_basligi("ilgili hukuk") == "İLGİLİ HUKUK"


def test_kurum_adi_kapakta_DOGRU_yaziliyor(tmp_path) -> None:
    """Uctan uca: kapaktaki kurum adı yanlış büyütülmemeli."""
    import zipfile as _zip

    hedef = dy.yaz(_rapor(), tmp_path / "kapak.docx")

    with _zip.ZipFile(hedef) as paket:
        govde = paket.read("word/document.xml").decode("utf-8")

    assert "DSİ TEFTİŞ KURULU BAŞKANLIĞI" in govde
    assert "TEFTIŞ" not in govde


# ---------------------------------------------------------------------------
# MADDE 9(3): ek dizinine sayfa numarası VERİLMEZ
# ---------------------------------------------------------------------------


def test_numarasiz_bolumler_BOS_ustbilgiye_bagli(xml: str) -> None:
    """OOXML'de üstbilgi tanımlamayan bölüm ÖNCEKİNDEN devralıyor.

    Gerçekten render edilip bakıldığında görüldü: ek dizini sayfasında "2/1"
    çıkıyordu, oysa MADDE 9(3) oraya sayfa numarası verilmemesini istiyor.
    Devralmayı kesmenin yolu referansı atlamak değil, BOŞ bir üstbilgiye
    bağlamak.
    """
    kok = ET.fromstring(xml)
    sectler = list(kok.iter(f"{W}sectPr"))

    # Her bolum ustbilgisini ACIKCA bildiriyor.
    for sect in sectler:
        assert sect.find(f"{W}headerReference") is not None

    kimlikler = [
        s.find(f"{W}headerReference").get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        for s in sectler
    ]

    # Yalnizca BIR bolum numarali ustbilgiyi (rId2) kullaniyor.
    assert kimlikler.count("rId2") == 1
    # Geri kalan hepsi BOS ustbilgiye (rId3) bagli.
    assert set(kimlikler) == {"rId2", "rId3"}


def test_bos_ustbilgi_parcasi_pakette_var(tmp_path) -> None:
    hedef = dy.yaz(_rapor(), tmp_path / "r.docx")

    with zipfile.ZipFile(hedef) as paket:
        assert "word/header2.xml" in paket.namelist()
        bos = paket.read("word/header2.xml").decode("utf-8")

    # Bos ustbilgide alan kodu OLMAMALI.
    assert "PAGE" not in bos
    assert "SECTIONPAGES" not in bos
