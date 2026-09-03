"""
Yönergeden şartname çıkarma.

Buradaki testlerin çoğu, ÖLÇÜLMÜŞ bir yanlış okumayı sabitliyor. Kural
tabanlı çıkarımın kusuru sessiz olması: yanlış okunan bir kenar boşluğu ya da
yanlış seçilen bir madde hata vermiyor, yalnızca 12-20 sayfalık belgeyi
yönergeye aykırı hâle getiriyor. O yüzden her tuzak kendi testini taşıyor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fool.rapor import sartname as sartname_modulu
from fool.rapor import yonerge_ogren
from fool.rapor.kaynak import Belge, Kalite
from fool.rapor.yonerge import cm, punto

FIXTURE = Path(__file__).parent / "fixtures" / "rapor"
YONERGE = FIXTURE / "yonerge.txt"


@pytest.fixture
def ogrenme():
    return yonerge_ogren.ogren(YONERGE, "test", bolum_secimi="MADDE 11")


def _belge(metin: str) -> Belge:
    return Belge(Path("yonerge.txt"), [metin], Kalite(True))


# ---------------------------------------------------------------------------
# Madde/fıkra bölme
# ---------------------------------------------------------------------------


def test_yonerge_madde_ve_fikralara_bolunuyor() -> None:
    """Her kuralın dayanağı olmalı; dayanak madde/fıkra bölmesinden geliyor."""
    birimler = yonerge_ogren.birimlere_ayir(YONERGE.read_text(encoding="utf-8"))
    dayanaklar = {b.dayanak for b in birimler}

    assert "MADDE 7/(2)" in dayanaklar
    assert "MADDE 11/(1)" in dayanaklar


def test_maddesi_olmayan_metin_TEK_birim_olarak_okunuyor() -> None:
    """Kullanıcı yönerge yerine düz bir kural listesi de verebilir."""
    birimler = yonerge_ogren.birimlere_ayir("Raporlar 12 punto yazılır.")

    assert len(birimler) == 1
    assert birimler[0].dayanak == ""


def test_olcu_parantezi_FIKRA_sanilmiyor() -> None:
    """"A4 (210x297 mm)" bir fıkra başlangıcı değil."""
    birimler = yonerge_ogren.birimlere_ayir(
        "MADDE 8- (1) Raporlar A4 (210x297 mm) boyutunda yazılır."
    )

    # Madde başlığı ayrı bir birim olarak çıkabiliyor (bölüm listesi bazen
    # orada duruyor); önemli olan TEK fıkra bulunması -- "(210x297 mm)"
    # ikinci bir fıkra sayılsaydı ölçü kendi başına bir kural gövdesi olurdu.
    assert [b.dayanak for b in birimler if "/" in b.dayanak] == ["MADDE 8/(1)"]


# ---------------------------------------------------------------------------
# Biçim çıkarımı
# ---------------------------------------------------------------------------


def test_kenar_bosluklari_YONE_gore_dagitiliyor(ogrenme) -> None:
    """"sol 2,5; sağ ve üst 1,5; alt 3" tek cümlede geçiyor."""
    degerler = ogrenme.sartname.bicim_degerleri

    assert degerler["kenar_sol"] == cm(2.5)
    assert degerler["kenar_sag"] == cm(1.5)
    assert degerler["kenar_ust"] == cm(1.5)
    assert degerler["kenar_alt"] == cm(3.0)


def test_paragraf_girintisi_SOL_KENAR_bosluguna_karismiyor(ogrenme) -> None:
    """Ölçülen tuzak: "Paragraflara soldan 1 cm içeriden başlanır".

    Bu cümle de "sol" içeriyor. Ayrım "kenar" sözcüğünde: girintiyi kenar
    boşluğu sanmak yönergenin 2,5 cm'lik kuralını 1 cm'e düşürüyordu.
    """
    degerler = ogrenme.sartname.bicim_degerleri

    assert degerler["paragraf_girinti"] == cm(1.0)
    assert degerler["kenar_sol"] == cm(2.5)


def test_font_adi_cumle_sozcugunu_YUTMUYOR() -> None:
    """Ölçülen tuzak: "Rapor metni Times New Roman yazı tipi ile".

    Düzenli ifade tamamen büyük/küçük harf duyarsız olduğunda font adı
    "metni Times New Roman" çıkıyordu -- belgeye var olmayan bir yazı tipi
    yazılır, Word sessizce başka bir fontla açardı.
    """
    birim = yonerge_ogren.Birim(
        "MADDE 7/(3)", "(3) Rapor metni Times New Roman yazı tipi ile 12 punto yazılır."
    )
    kurallar = {k.alan: k.deger for k in yonerge_ogren._yazi_kurallari(birim)}

    assert kurallar["yazi_tipi"] == "Times New Roman"
    assert kurallar["yazi_boyut"] == punto(12)


def test_bicim_kurallari_DAYANAGIYLA_saklaniyor(ogrenme) -> None:
    """Gözden geçirme, kuralın hangi maddeden geldiğini görmeyi gerektiriyor."""
    kural = ogrenme.sartname.kural("kenar_sol")

    assert kural is not None
    assert kural.dayanak == "MADDE 7/(2)"
    assert "2,5 cm" in kural.alinti


def test_satir_araligi_hizalama_ve_sayfa_olcusu(ogrenme) -> None:
    degerler = ogrenme.sartname.bicim_degerleri

    assert degerler["satir_araligi"] == 240  # tek satır aralığı
    assert degerler["hizalama"] == "both"  # iki yana yaslı
    assert degerler["sayfa_genislik"] == 11906  # A4
    assert degerler["sayfa_no_hizalama"] == "right"


def test_paragraf_bosluguda_araligin_UST_SINIRI_aliniyor(ogrenme) -> None:
    """"3-6 nk" -- üst sınır, ``yonerge.Bicim``in kendi tercihiyle aynı."""
    assert ogrenme.sartname.bicim_degerleri["paragraf_bosluk"] == 6 * 20


def test_bicim_dogrudan_yaziciya_verilebiliyor(ogrenme) -> None:
    """Şartname bir ``Bicim`` üretmeli; yazıcı başka bir şey kabul etmiyor."""
    bicim = ogrenme.sartname.bicim()

    assert bicim.yazi_tipi == "Times New Roman"
    assert bicim.kenar_sol == cm(2.5)


# ---------------------------------------------------------------------------
# Bölüm listeleri
# ---------------------------------------------------------------------------


def test_yonergedeki_BUTUN_iskeletler_bulunuyor(ogrenme) -> None:
    """Bir yönerge birkaç rapor türü tanımlıyor; seçim kullanıcının."""
    dayanaklar = {a.dayanak for a in ogrenme.bolum_adaylari}

    assert dayanaklar == {"MADDE 11/(1)", "MADDE 12/(1)"}


def test_secilen_iskelet_SIRASIYLA_aliniyor(ogrenme) -> None:
    assert ogrenme.sartname.bolumler == [
        "I. GİRİŞ",
        "II. KONU",
        "III. İNCELEME VE ARAŞTIRMA",
        "IV. TARTIŞMA VE DEĞERLENDİRME",
        "V. SONUÇ",
    ]


def test_secim_verilmezse_EN_UZUN_liste_seciliyor() -> None:
    ogrenme = yonerge_ogren.ogren(YONERGE, "test")

    assert ogrenme.sartname.bolum_dayanagi == "MADDE 12/(1)"
    assert len(ogrenme.sartname.bolumler) == 6


def test_liste_basligi_SATIR_SONUNDAN_bolunmuyor(ogrenme) -> None:
    """Ölçülen tuzak: "...ve bu sırayla\\noluşur:" -> başlık "oluşur" çıkıyordu.

    Başlık, kullanıcının iki iskeleti ayırt etmesini sağlayan tek ipucu.
    """
    assert "İnceleme raporları" in ogrenme.sartname.ad


def test_ikili_dizi_bolum_listesi_SAYILMIYOR() -> None:
    """İki maddelik bir dizi tesadüfen oluşabiliyor; rapor iskeleti olamaz."""
    birimler = [yonerge_ogren.Birim("MADDE 1", "I. BİRİNCİ II. İKİNCİ")]

    assert yonerge_ogren.bolum_listeleri(birimler) == []


# ---------------------------------------------------------------------------
# İfadeler, sayfa aralığı, kapak
# ---------------------------------------------------------------------------


def test_kapanis_ifadesi_cikariliyor(ogrenme) -> None:
    assert ogrenme.sartname.kapanis_ifadesi == "görüş ve kanaatine varılmıştır"


def test_zorunlu_ifadeler_RAPOR_TURUNE_gore_kapsanıyor() -> None:
    """Ön inceleme ifadeleri, inceleme raporunu "uygun" göstermemeli."""
    inceleme = yonerge_ogren.ogren(YONERGE, "t1", bolum_secimi="MADDE 11").sartname
    on = yonerge_ogren.ogren(YONERGE, "t2", bolum_secimi="MADDE 12").sartname

    assert "kamu zararı tespit edilmiştir" in inceleme.zorunlu_ifadeler
    assert "soruşturma izni verilmesi gerektiği" not in inceleme.zorunlu_ifadeler

    assert "soruşturma izni verilmesi gerektiği" in on.zorunlu_ifadeler
    assert "kamu zararı tespit edilmiştir" not in on.zorunlu_ifadeler


def test_satir_kaydirilmis_tirnak_BAGLACI_ifade_sanmiyor() -> None:
    """Ölçülen tuzak: ``"A\\nB" veya "C"`` -> şartnameye "veya" giriyordu.

    Kapanış tırnağı açılış sanılıyor ve iki ifadenin arasındaki bağlaç
    zorunlu ifade olarak kaydediliyordu.
    """
    _, zorunlu, _ = yonerge_ogren._ifade_kurallari(
        [
            yonerge_ogren.Birim(
                "MADDE 12/(2)",
                'Sonuç bölümünde "soruşturma izni verilmesi\n'
                'gerektiği" veya "soruşturma izni verilmemesi gerektiği" '
                "ifadelerinden biri kullanılır.",
            )
        ]
    )

    assert "veya" not in zorunlu
    assert "soruşturma izni verilmesi gerektiği" in zorunlu


def test_sayfa_araligi_yonergeden_okunuyor(ogrenme) -> None:
    assert (ogrenme.sartname.sayfa_en_az, ogrenme.sartname.sayfa_en_cok) == (12, 20)


def test_yonergedeki_sayfa_araligi_kullanici_tercihini_EZIYOR() -> None:
    """Yönergeyi kullanıcı tercihiyle ezmek "yönergeye uygun" sözünü bozardı."""
    ogrenme = yonerge_ogren.ogren(
        YONERGE, "test", bolum_secimi="MADDE 11", sayfa_en_az=5, sayfa_en_cok=8
    )

    assert (ogrenme.sartname.sayfa_en_az, ogrenme.sartname.sayfa_en_cok) == (12, 20)


def test_yonergede_aralik_yoksa_kullanici_hedefi_geciyor() -> None:
    ogrenme = yonerge_ogren.belgeden_ogren(
        _belge("MADDE 1- (1) Raporlar özenle yazılır."),
        "test",
        sayfa_en_az=6,
        sayfa_en_cok=9,
    )

    assert (ogrenme.sartname.sayfa_en_az, ogrenme.sartname.sayfa_en_cok) == (6, 9)


def test_kapak_alanlari_DOGRU_maddeden_aliniyor(ogrenme) -> None:
    """Ölçülen tuzak: bölüm başlığı bir önceki maddenin son fıkrasına yapışıyor.

    "İKİNCİ BÖLÜM / Kapak sayfası" başlığı MADDE 4'ün metnine dahil oluyor ve
    kapak alanları olarak MADDE 4'ün yazım kuralları çıkıyordu.
    """
    assert ogrenme.sartname.kapak_alanlari[0] == "Bakanlık adı"
    assert "Ek adedi" in ogrenme.sartname.kapak_alanlari
    assert not any(
        "Kısaltmalar" in a for a in ogrenme.sartname.kapak_alanlari
    )


def test_ek_atif_bicimi_cikariliyor(ogrenme) -> None:
    assert ogrenme.sartname.ek_atif_bicimi == "(Ek: 5/3)"


# ---------------------------------------------------------------------------
# Bulunamayan kural
# ---------------------------------------------------------------------------


def test_bulunamayan_kural_SESSIZCE_varsayilana_dusmuyor() -> None:
    """Kullanıcı "yönergeme göre üretildi" sanmamalı; ne okunmadıysa yazılı."""
    ogrenme = yonerge_ogren.belgeden_ogren(
        _belge("MADDE 1- (1) Raporlar özenle ve zamanında yazılır."), "test"
    )

    eksik = ogrenme.sartname.eksik_kurallar

    assert "yazi_tipi" in eksik
    assert "kenar_sol" in eksik
    assert "bölüm listesi" in eksik


def test_tam_yonergede_eksik_kural_kalmiyor(ogrenme) -> None:
    assert ogrenme.sartname.eksik_kurallar == []


def test_bozuk_metinli_yonerge_REDDEDILIYOR(tmp_path: Path) -> None:
    """Bozuk çıkarılmış bir yönergeden kural çıkarmak, uydurma kural üretir."""
    bozuk = tmp_path / "bozuk.txt"
    bozuk.write_text("d s pl n rej m n n genel çerçeves " * 80, encoding="utf-8")

    with pytest.raises(ValueError, match="güvenilir değil"):
        yonerge_ogren.ogren(bozuk, "test")


# ---------------------------------------------------------------------------
# Saklama
# ---------------------------------------------------------------------------


def test_sartname_diske_yazilip_geri_okunuyor(tmp_path, monkeypatch) -> None:
    """Yönerge bir kez veriliyor, aylarca kullanılıyor."""
    monkeypatch.setenv("FOOL_RAPOR_SARTNAME_DIR", str(tmp_path))

    ogrenme = yonerge_ogren.ogren(YONERGE, "kayit", bolum_secimi="MADDE 11")
    sartname_modulu.kaydet(ogrenme.sartname)

    geri = sartname_modulu.yukle("kayit")

    assert geri.bolumler == ogrenme.sartname.bolumler
    assert geri.bicim().kenar_sol == cm(2.5)
    assert sartname_modulu.listele() == ["kayit"]


def test_gecersiz_kimlik_baska_klasore_yazamiyor(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FOOL_RAPOR_SARTNAME_DIR", str(tmp_path))

    with pytest.raises(sartname_modulu.SartnameHatasi, match="geçersiz"):
        sartname_modulu.yukle("../../gizli")


def test_ozet_metni_her_kurali_DAYANAGIYLA_gosteriyor(ogrenme) -> None:
    """Kullanıcı 70 sayfayı değil bunu okuyup onaylıyor."""
    ozet = ogrenme.sartname.ozet_metni()

    assert "III. İNCELEME VE ARAŞTIRMA" in ozet
    assert "MADDE 7/(2)" in ozet
    assert "12-20 sayfa" in ozet
    assert "görüş ve kanaatine varılmıştır" in ozet
