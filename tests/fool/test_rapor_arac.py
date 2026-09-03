"""
Ajan araçları: okuma, öğrenme, tamamlama, yazma.

En önemli iki davranış burada sınanıyor:

* Bozuk metin modele DÖNDÜRÜLMÜYOR -- yalnızca uyarı dönüyor.
* Verilmeyen alan UYDURULMUYOR -- ``[EKSİK]`` kalıyor ve geri bildiriliyor.
"""

from __future__ import annotations

import json
import zipfile

from fool.rapor import arac

SAGLAM = (
    "Memur disiplin rejiminin genel çerçevesi yasal düzenleme ile "
    "belirlenmiştir. Ayrıca ilgili yönetmeliklerle de memur disiplin "
    "hukukunun usul ve esasları düzenleme altına alınmıştır. Nitekim kamu "
    "hizmetinin etkin ve verimli yürütülmesi için yapılan disiplin "
    "soruşturmalarında temel ilkelere riayet edilmesi gerekir. Disiplin "
    "suçu; Devlet memurlarının statülerine ilişkin hükümlere uymaması "
    "sebebiyle kurum düzeninin bozulmasına sebep olan fiillerdir."
)


def _docx(yol, satirlar, *, font="Times New Roman", sz=24) -> None:
    govde = "".join(
        f'<w:p><w:pPr><w:jc w:val="both"/></w:pPr>'
        f'<w:r><w:rPr><w:rFonts w:ascii="{font}"/><w:sz w:val="{sz}"/></w:rPr>'
        f"<w:t>{s}</w:t></w:r></w:p>"
        for s in satirlar
    )
    sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="850" w:right="850" w:bottom="1701" w:left="1417"/></w:sectPr>')
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{govde}{sect}</w:body></w:document>")
    with zipfile.ZipFile(yol, "w") as paket:
        paket.writestr("word/document.xml", xml)


_RAPOR = [
    "İNCELEME RAPORU",
    "I. GİRİŞ",
    "Makam Olur'u doğrultusunda incelemeye başlanmıştır. (Ek:1/1)",
    "II. KONU",
    "Rücuen tazmin davalarında zamanaşımı incelenmiştir.",
    "III. İNCELEME VE ARAŞTIRMA",
    SAGLAM,
    "IV. TARTIŞMA VE DEĞERLENDİRME",
    "Mevzuat açısından değerlendirildiğinde;",
    "V. SONUÇ VE ÖNERİLER",
    "A. Disiplin Yönünden",
    "Görüş ve kanaatine varılmıştır.",
]


# ---------------------------------------------------------------------------
# kaynak_oku
# ---------------------------------------------------------------------------


def test_bozuk_metin_MODELE_DONMUYOR(tmp_path) -> None:
    """Bozuk çıkarılmış metni "yine de al" diye vermek raporu bozar."""
    yol = tmp_path / "bozuk.docx"
    _docx(yol, [SAGLAM.replace("i", "")] * 3)

    cevap = json.loads(arac.kaynak_oku(str(yol)))

    assert cevap["guvenilir"] is False
    assert "OCR" in cevap["oneri"]
    assert "metin" not in cevap


def test_saglam_belge_METNI_donuyor(tmp_path) -> None:
    yol = tmp_path / "saglam.docx"
    _docx(yol, [SAGLAM])

    cevap = json.loads(arac.kaynak_oku(str(yol)))

    assert cevap["guvenilir"] is True
    assert "disiplin" in cevap["metin"]


def test_BUYUK_belge_tamamini_dokmuyor_sorgu_istiyor(tmp_path) -> None:
    """Bağlamı taşıracak bir belgeyi olduğu gibi vermek pencereyi patlatır."""
    yol = tmp_path / "buyuk.docx"
    _docx(yol, [SAGLAM] * 200)

    cevap = json.loads(arac.kaynak_oku(str(yol), token_butcesi=500))

    assert "metin" not in cevap
    assert "sorgu" in cevap["uyari"]


def test_sorguyla_YALNIZCA_ilgili_kesit_donuyor(tmp_path) -> None:
    yol = tmp_path / "mevzuat.docx"
    _docx(yol, [
        "MADDE 8- (1) Rapor metni Times New Roman 12 punto yazılır.",
        "MADDE 30- (1) Disiplin cezalarında zamanaşımı süreleri kanunda gösterilmiştir.",
    ])

    cevap = json.loads(arac.kaynak_oku(str(yol), sorgu="disiplin zamanaşımı"))
    basliklar = " ".join(k["baslik"] for k in cevap["kesitler"])

    assert "MADDE 30" in basliklar
    assert cevap["secilen_token"] <= cevap["toplam_token"]


def test_olmayan_belge_ACIK_hata_veriyor() -> None:
    assert "bulunamadı" in json.loads(arac.kaynak_oku("yok.docx"))["error"]


# ---------------------------------------------------------------------------
# ornek_ogren
# ---------------------------------------------------------------------------


def test_ornek_ISKELET_donuyor_METIN_donmuyor(tmp_path) -> None:
    """Örneğin cümleleri yeni rapora sızmamalı."""
    yol = tmp_path / "ornek.docx"
    _docx(yol, [*_RAPOR, "Davacı Sefer TOPKAFA işten çıkarılmıştır."])

    cevap = json.loads(arac.ornek_ogren(str(yol)))

    assert "I. GİRİŞ" in cevap["bolumler"]
    assert "(Ek:1/1)" in cevap["ek_atif_bicimi"]
    assert "TOPKAFA" not in json.dumps(cevap, ensure_ascii=False)


def test_ornekten_BICIM_de_okunuyor(tmp_path) -> None:
    yol = tmp_path / "ornek.docx"
    _docx(yol, _RAPOR, font="Cambria", sz=22)

    cevap = json.loads(arac.ornek_ogren(str(yol)))

    assert cevap["bicim"]["yazi_tipi"] == "Cambria"
    assert cevap["bicim"]["punto"] == 11


# ---------------------------------------------------------------------------
# yarim_cozumle
# ---------------------------------------------------------------------------


def test_yarim_rapor_EKSIKLERI_ve_BICIMI_bildiriyor(tmp_path) -> None:
    yol = tmp_path / "yarim.docx"
    _docx(yol, _RAPOR[:7], font="Cambria", sz=22)

    cevap = json.loads(arac.yarim_cozumle(str(yol)))
    eksik = {e["baslik"] for e in cevap["eksik_bolumler"]}

    assert cevap["tur"] == "inceleme"
    assert "IV. TARTIŞMA VE DEĞERLENDİRME" in eksik
    assert cevap["bicim"]["yazi_tipi"] == "Cambria"
    # Tamamlama icin tam metin de veriliyor: yarim rapor EKSIKSIZ okunuyor.
    assert SAGLAM[:40] in cevap["tam_metin"]


def test_yarim_rapor_yonergeden_FARKLARI_bildiriyor_ama_degistirmiyor(tmp_path) -> None:
    yol = tmp_path / "yarim.docx"
    _docx(yol, _RAPOR[:7], font="Cambria", sz=22)

    cevap = json.loads(arac.yarim_cozumle(str(yol)))
    farklar = " ".join(cevap["bicim"]["yonergeden_farklar"])

    assert "yazı tipi" in farklar
    assert cevap["bicim"]["yazi_tipi"] == "Cambria"


# ---------------------------------------------------------------------------
# rapor_yaz
# ---------------------------------------------------------------------------

_ISTEK = {
    "tur": "inceleme",
    "kapak": {
        "bakanlik": "Tarım ve Orman Bakanlığı",
        "baskanlik": "DSİ Teftiş Kurulu Başkanlığı",
        "baslik": "İnceleme Raporu",
        "konu": "Deneme konusu",
        "gorev_emri_tarih": "10.04.2026",
        "gorev_emri_sayi": "7032434",
        "rapor_tarih": "01.06.2026",
        "rapor_sayi": "8-2026/1",
        "ek_adedi": "2",
        "mufettis_ad": "Birhan OĞURLU",
    },
    "ozet": ["Kamu zararı oluşmadığı değerlendirilmiştir."],
    "bolumler": [
        {
            "baslik": "I. GİRİŞ",
            "ogeler": [
                {"tur": "paragraf", "metin": "İncelemeye başlanmıştır.", "ek": "Ek: 1/1"},
                {"tur": "alt_baslik", "metin": "Cevaplı Teftiş Raporu Madde 2 Açısından"},
                {"tur": "alinti", "metin": "her alacak on yıllık zamanaşımına tabidir",
                 "kaynak": "TBK m.146"},
                {"tur": "tablo", "baslik": "Tablo 1: Süreler",
                 "basliklar": ["Madde", "Süre"], "satirlar": [["2", "2 Yıl 4 Ay"]]},
            ],
        }
    ],
    "ekler": [{"no": 1, "icerik": "Makam Onayı", "sayfa_sayisi": 2}],
    "imza_yer": "Ankara",
    "imza_tarih": "01.06.2026",
}


def test_rapor_yaziliyor_ve_ACILABILIR_docx_cikiyor(tmp_path) -> None:
    hedef = tmp_path / "rapor.docx"

    cevap = json.loads(arac.rapor_yaz(json.dumps(_ISTEK), str(hedef)))

    assert cevap["bayt"] > 0
    assert cevap["eksik_alanlar"] == []
    with zipfile.ZipFile(hedef) as paket:
        assert paket.testzip() is None
        assert "word/document.xml" in paket.namelist()


def test_verilmeyen_alan_UYDURULMUYOR_ve_bildiriliyor(tmp_path) -> None:
    """Resmî evrakta uydurulmuş bir sayı, görünür bir boşluktan kötüdür."""
    istek = json.loads(json.dumps(_ISTEK))
    del istek["kapak"]["gorev_emri_sayi"]
    del istek["imza_tarih"]

    cevap = json.loads(arac.rapor_yaz(json.dumps(istek), str(tmp_path / "r.docx")))

    assert "Görev emri sayısı" in cevap["eksik_alanlar"]
    assert "İmza tarihi" in cevap["eksik_alanlar"]
    assert cevap["uyari"]


def test_BICIM_kaynagindan_devralarak_yaziliyor(tmp_path) -> None:
    """Yarım raporu tamamlarken iki yarı aynı görünmeli."""
    yarim = tmp_path / "yarim.docx"
    _docx(yarim, _RAPOR[:5], font="Cambria", sz=22)
    hedef = tmp_path / "tamam.docx"

    cevap = json.loads(
        arac.rapor_yaz(json.dumps(_ISTEK), str(hedef), bicim_kaynagi=str(yarim))
    )

    assert cevap["bicim_devralindi"]["yazi_tipi"] == "Cambria"
    with zipfile.ZipFile(hedef) as paket:
        assert "Cambria" in paket.read("word/styles.xml").decode("utf-8")


def test_bilinmeyen_tur_REDDEDILIYOR(tmp_path) -> None:
    istek = {**_ISTEK, "tur": "olmayan_tur"}

    cevap = json.loads(arac.rapor_yaz(json.dumps(istek), str(tmp_path / "r.docx")))

    assert "bilinmeyen rapor türü" in cevap["error"]
    assert "inceleme" in cevap["gecerli"]


def test_bozuk_json_ACIK_hata_veriyor(tmp_path) -> None:
    cevap = json.loads(arac.rapor_yaz("{bozuk", str(tmp_path / "r.docx")))

    assert "JSON" in cevap["error"]


def test_kayik_tablo_YAZIYA_girmeden_reddediliyor(tmp_path) -> None:
    """Hücre sayısı tutmayan tablo Word'de sessizce bozuk görünür."""
    istek = json.loads(json.dumps(_ISTEK))
    istek["bolumler"][0]["ogeler"] = [
        {"tur": "tablo", "baslik": "Tablo 1", "basliklar": ["A", "B"],
         "satirlar": [["tek"]]}
    ]

    cevap = json.loads(arac.rapor_yaz(json.dumps(istek), str(tmp_path / "r.docx")))

    assert "hucre" in cevap["error"]


# ---------------------------------------------------------------------------
# Kayıt: araçlar GERÇEKTEN keşfediliyor mu
# ---------------------------------------------------------------------------


def test_araclar_KESIFLE_kaydoluyor() -> None:
    """Ölçülmüş tuzak: kayıt ``try`` içindeyken keşif modülü hiç ithal etmiyor.

    ``registry._module_registers_tools`` yalnızca modül gövdesindeki en üst
    seviye ifadelere bakıyor. ``fool/output_file.py`` bu yüzden üründe hiç
    kaydolmuyor -- ``write_output`` takım listesinde var, aracı yok.
    """
    from tools.registry import discover_builtin_tools, registry

    discover_builtin_tools()
    adlar = registry.get_all_tool_names()

    for arac_adi in (
        "rapor_kaynak_oku",
        "rapor_ornek_ogren",
        "rapor_yarim_cozumle",
        "rapor_yaz",
    ):
        assert arac_adi in adlar, f"{arac_adi} kesifle kaydolmadi"
        assert registry.get_toolset_for_tool(arac_adi) == "rapor"
