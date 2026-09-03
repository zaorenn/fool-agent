"""
Üretimden ÖNCE uygunluk denetimi ve sayfa hedefi.

Bu iki denetimin ortak gerekçesi: yanlış bir resmî evrak üretilip sonra
bildirilirse geç kalınmış olur -- üretilen belge imzalanıyor. O yüzden
denetim taslağın üstünde çalışıyor ve engel varsa belge YAZILMIYOR.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fool.rapor import sayfa_hedefi, uygunluk
from fool.rapor.sartname import Sartname

FIXTURE = Path(__file__).parent / "fixtures" / "rapor"


def _sartname(**degisiklik) -> Sartname:
    varsayilan = dict(
        kimlik="t",
        ad="İNCELEME RAPORU",
        bolumler=["I. GİRİŞ", "II. KONU", "III. SONUÇ"],
        bolum_dayanagi="MADDE 11/(1)",
        zorunlu_ifadeler=["kamu zararı tespit edilmiştir"],
        kapanis_ifadesi="görüş ve kanaatine varılmıştır",
        kapak_alanlari=["Bakanlık adı", "Rapor konusu"],
    )
    varsayilan.update(degisiklik)

    return Sartname(**varsayilan)  # type: ignore[arg-type]


def _p(metin: str, ek: str = "") -> dict:
    return {"tur": "paragraf", "metin": metin, "ek": ek}


def _tam_taslak(**degisiklik) -> dict:
    veri = {
        "tur": "inceleme",
        "kapak": {"bakanlik": "T.C. ÖRNEK BAKANLIĞI", "konu": "Fazla çalışma"},
        "ekler": [{"no": 1, "icerik": "Dilekçe", "sayfa_sayisi": 1}],
        "bolumler": [
            {"baslik": "I. GİRİŞ", "ogeler": [_p("Görev emri uyarınca inceleme yapıldı.")]},
            {"baslik": "II. KONU", "ogeler": [_p("İnceleme konusu fazla çalışmadır.")]},
            {
                "baslik": "III. SONUÇ",
                "ogeler": [
                    _p("Yapılan incelemede kamu zararı tespit edilmiştir.", "Ek: 1/1"),
                    _p("Gereğinin yapılması görüş ve kanaatine varılmıştır."),
                ],
            },
        ],
    }
    veri.update(degisiklik)

    return veri


# ---------------------------------------------------------------------------
# Bölümler ve sıra
# ---------------------------------------------------------------------------


def test_tam_taslak_uygun_cikiyor() -> None:
    denetim = uygunluk.denetle(_tam_taslak(), _sartname())

    assert denetim.uygun
    assert denetim.engeller == []


def test_eksik_bolum_ENGEL() -> None:
    taslak = _tam_taslak()
    taslak["bolumler"] = taslak["bolumler"][:2]

    denetim = uygunluk.denetle(taslak, _sartname())

    assert not denetim.uygun
    assert any("III. SONUÇ" in b.aciklama for b in denetim.engeller)


def test_bos_bolum_ENGEL() -> None:
    taslak = _tam_taslak()
    taslak["bolumler"][1]["ogeler"] = [_p("   ")]

    denetim = uygunluk.denetle(taslak, _sartname())

    assert any("boş" in b.aciklama for b in denetim.engeller)


def test_bolum_SIRASI_yonergeye_aykiriysa_ENGEL() -> None:
    """Yönerge sırayı sayıyor ve o sıra bağlayıcı."""
    taslak = _tam_taslak()
    taslak["bolumler"][0], taslak["bolumler"][1] = (
        taslak["bolumler"][1],
        taslak["bolumler"][0],
    )

    denetim = uygunluk.denetle(taslak, _sartname())

    assert any(b.alan == "sıra" for b in denetim.engeller)


def test_eksik_bolum_sira_hatasi_olarak_IKI_KEZ_sayilmiyor() -> None:
    taslak = _tam_taslak()
    del taslak["bolumler"][1]

    denetim = uygunluk.denetle(taslak, _sartname())

    assert not any(b.alan == "sıra" for b in denetim.bulgular)


def test_yonergede_olmayan_ek_bolum_engel_degil() -> None:
    """Müfettiş kendi alt bölümünü açabiliyor."""
    taslak = _tam_taslak()
    taslak["bolumler"].append({"baslik": "EKLER", "ogeler": [_p("Ek listesi.")]})

    assert uygunluk.denetle(taslak, _sartname()).uygun


# ---------------------------------------------------------------------------
# Zorunlu ifadeler -- bu depoda VERİ olarak duruyordu, uygulanmıyordu
# ---------------------------------------------------------------------------


def test_kapanis_ifadesi_yoksa_ENGEL() -> None:
    taslak = _tam_taslak()
    taslak["bolumler"][2]["ogeler"] = [
        _p("Yapılan incelemede kamu zararı tespit edilmiştir.", "Ek: 1/1")
    ]

    denetim = uygunluk.denetle(taslak, _sartname())

    assert any(b.alan == "kapanış" for b in denetim.engeller)


def test_kapanis_ifadesi_SON_BOLUMDE_aranıyor() -> None:
    """Tartışma bölümünde geçen bir kalıp raporu bitirmiş sayılmaz."""
    taslak = _tam_taslak()
    taslak["bolumler"][0]["ogeler"] = [_p("... görüş ve kanaatine varılmıştır.")]
    taslak["bolumler"][2]["ogeler"] = [
        _p("Yapılan incelemede kamu zararı tespit edilmiştir.", "Ek: 1/1")
    ]

    denetim = uygunluk.denetle(taslak, _sartname())

    assert any(b.alan == "kapanış" for b in denetim.engeller)


def test_sonuc_kesin_ifadesi_yoksa_ENGEL() -> None:
    taslak = _tam_taslak()
    taslak["bolumler"][2]["ogeler"] = [
        _p("İnceleme tamamlanmıştır.", "Ek: 1/1"),
        _p("Gereğinin yapılması görüş ve kanaatine varılmıştır."),
    ]

    denetim = uygunluk.denetle(taslak, _sartname())

    engel = next(b for b in denetim.engeller if b.alan == "sonuç ifadesi")

    assert "kamu zararı tespit edilmiştir" in engel.aciklama


def test_kesin_ifade_SONUC_bolumunde_aranıyor() -> None:
    """Tartışmada geçen bir ifade, sonucu yazmış saymıyor."""
    taslak = _tam_taslak()
    taslak["bolumler"][1]["ogeler"] = [_p("Burada kamu zararı tespit edilmiştir.")]
    taslak["bolumler"][2]["ogeler"] = [
        _p("İnceleme bitmiştir.", "Ek: 1/1"),
        _p("Gereğinin yapılması görüş ve kanaatine varılmıştır."),
    ]

    denetim = uygunluk.denetle(taslak, _sartname())

    assert any(b.alan == "sonuç ifadesi" for b in denetim.engeller)


# ---------------------------------------------------------------------------
# Kapak
# ---------------------------------------------------------------------------


def test_bos_kapak_alani_ENGEL() -> None:
    taslak = _tam_taslak()
    taslak["kapak"] = {"bakanlik": "T.C. ÖRNEK BAKANLIĞI"}

    denetim = uygunluk.denetle(taslak, _sartname())

    assert any("Rapor konusu" in b.aciklama for b in denetim.engeller)


def test_eslenemeyen_kapak_alani_SESSIZCE_gecilmiyor() -> None:
    """Yönerge istiyor, kod tutmuyorsa bu görünmeli."""
    denetim = uygunluk.denetle(
        _tam_taslak(), _sartname(kapak_alanlari=["Kurumsal logo"])
    )

    assert any("Kurumsal logo" in b.aciklama for b in denetim.uyarilar)


# ---------------------------------------------------------------------------
# İzlenebilirlik
# ---------------------------------------------------------------------------


def test_dayanaksiz_maddi_tespit_UYARI() -> None:
    taslak = _tam_taslak()
    taslak["bolumler"][1]["ogeler"] = [_p("14.02.2026 tarihinde dilekçe verilmiştir.")]

    denetim = uygunluk.denetle(taslak, _sartname())

    assert any(b.alan == "dayanak" for b in denetim.uyarilar)


def test_metne_yazilmis_ek_atfi_dayanak_sayiliyor() -> None:
    taslak = _tam_taslak()
    taslak["bolumler"][1]["ogeler"] = [
        _p("14.02.2026 tarihinde dilekçe verilmiştir (Ek: 1/1).")
    ]

    assert uygunluk.denetle(taslak, _sartname()).uygun


def test_yorum_cumlesi_maddi_tespit_sayilmiyor() -> None:
    """Her paragrafı işaretlemek uyarıyı gürültüye çevirirdi."""
    taslak = _tam_taslak()
    taslak["bolumler"][1]["ogeler"] = [_p("Durum ayrıntılı olarak değerlendirilmiştir.")]

    assert not any(
        b.alan == "dayanak" for b in uygunluk.denetle(taslak, _sartname()).bulgular
    )


def test_hic_ek_yokken_maddi_tespit_ENGEL() -> None:
    """Dayanağı olmayan bir rapor imzalanamaz."""
    taslak = _tam_taslak(ekler=[])
    taslak["bolumler"][1]["ogeler"] = [_p("14.02.2026 tarihinde dilekçe verilmiştir.")]

    denetim = uygunluk.denetle(taslak, _sartname())

    assert any(b.alan == "dayanak" for b in denetim.engeller)


# ---------------------------------------------------------------------------
# Şişirme
# ---------------------------------------------------------------------------


def test_birebir_tekrar_eden_cumle_ENGEL() -> None:
    """Sayfa hedefi olan bir üretimde tekrar, modelin en ucuz çıkış yolu."""
    tekrar = (
        "Fazla çalışma çizelgelerinin dayanak belgeye bağlanmadığı tespit edilmiştir."
    )
    taslak = _tam_taslak()
    taslak["bolumler"][0]["ogeler"] = [_p(tekrar)]
    taslak["bolumler"][1]["ogeler"] = [_p(tekrar)]

    denetim = uygunluk.denetle(taslak, _sartname())

    assert any(b.alan == "şişirme" for b in denetim.engeller)


def test_kisa_resmi_kalip_tekrari_sisirme_sayilmiyor() -> None:
    """"Arz olunur." meşru olarak tekrarlanıyor."""
    taslak = _tam_taslak()
    taslak["bolumler"][0]["ogeler"] = [_p("Arz olunur.")]
    taslak["bolumler"][1]["ogeler"] = [_p("Arz olunur.")]

    assert not any(
        b.alan == "şişirme" for b in uygunluk.denetle(taslak, _sartname()).bulgular
    )


# ---------------------------------------------------------------------------
# Şartname yokken
# ---------------------------------------------------------------------------


def test_sartname_yoksa_GOMULU_ture_dusuluyor() -> None:
    """Yönerge yüklenmemiş bir oturumda denetim büsbütün kaybolmamalı."""
    denetim = uygunluk.denetle({"tur": "inceleme", "bolumler": []})

    assert not denetim.uygun
    assert any("I. GİRİŞ" in b.aciklama for b in denetim.engeller)


def test_taninmayan_tur_ve_sartname_yoksa_ACIKCA_soyleniyor() -> None:
    denetim = uygunluk.denetle({"tur": "bilinmeyen", "bolumler": []})

    assert any(b.alan == "şartname" for b in denetim.engeller)


def test_denetlenmeyen_kural_UYGUN_sayilmiyor() -> None:
    """Şartname bir kuralı taşımıyorsa o kural denetlenmedi demektir."""
    denetim = uygunluk.denetle(
        _tam_taslak(), _sartname(kapanis_ifadesi="", zorunlu_ifadeler=[])
    )

    assert any("kapanış" in d for d in denetim.denetlenmeyenler)


def test_sayfa_araligi_denetlenmeyenlerde_bildiriliyor() -> None:
    """Gerçek sayfa sayısı ancak belge basıldıktan sonra bilinebiliyor."""
    denetim = uygunluk.denetle(
        _tam_taslak(), _sartname(sayfa_en_az=12, sayfa_en_cok=20)
    )

    assert any("sayfa aralığı" in d for d in denetim.denetlenmeyenler)


# ---------------------------------------------------------------------------
# Sayfa hedefi
# ---------------------------------------------------------------------------


def _uzun_taslak(karakter: int) -> dict:
    return {
        "bolumler": [
            {"baslik": "I. GİRİŞ", "ogeler": [_p("a" * (karakter // 2))]},
            {"baslik": "II. KONU", "ogeler": [_p("b" * (karakter // 2))]},
        ]
    }


def test_kisa_rapor_EKSIK_KARAKTERI_olcumden_hesapliyor() -> None:
    """Sayfa başına karakter, bu belgenin KENDİ ölçüsünden çıkıyor."""
    denetim = sayfa_hedefi.degerlendir(6, 12, 20, _uzun_taslak(18_000))

    assert not denetim.uygun
    assert denetim.sayfa_basina_karakter == 3000
    assert denetim.eksik_karakter == 6 * 3000


def test_kisa_rapor_yonergesi_SISIRMEYI_degil_KAYNAGI_isaret_ediyor() -> None:
    """Kullanıcının şartı "dolu dolu"; boşluk açarak sayfa tutturmak başarısızlık."""
    denetim = sayfa_hedefi.degerlendir(6, 12, 20, _uzun_taslak(18_000))

    assert "SATIR ARALIĞI" in denetim.yonerge
    assert "rapor_delil_oku" in denetim.yonerge


def test_kisa_rapor_EN_INCE_bolumleri_isaret_ediyor() -> None:
    """Eksiği eşit dağıtmak yanlış: uzaması gereken bölüm bellidir."""
    taslak = {
        "bolumler": [
            {"baslik": "I. GİRİŞ", "ogeler": [_p("a" * 5000)]},
            {"baslik": "II. KONU", "ogeler": [_p("b" * 100)]},
        ]
    }

    denetim = sayfa_hedefi.degerlendir(2, 12, 20, taslak)

    assert denetim.ince_bolumler[0] == "II. KONU"


def test_uzun_rapor_TESPIT_SILMEYI_onermiyor() -> None:
    denetim = sayfa_hedefi.degerlendir(25, 12, 20, _uzun_taslak(60_000))

    assert denetim.fazla_karakter > 0
    assert "Tespitleri SİLME" in denetim.yonerge


def test_aralik_icindeki_rapor_uygun() -> None:
    denetim = sayfa_hedefi.degerlendir(14, 12, 20, _uzun_taslak(40_000))

    assert denetim.uygun
    assert denetim.eksik_karakter == 0


def test_olculemeyen_sayfa_sayisi_UYGUN_sayilmiyor() -> None:
    """Dönüştürücüsü olmayan makinede her rapor "uygun" çıkmamalı."""
    denetim = sayfa_hedefi.degerlendir(
        0, 12, 20, {}, olculdu=False, gerekce="dönüştürücü yok"
    )

    assert not denetim.uygun
    assert "dönüştürücü yok" in denetim.yonerge


def test_donusturucu_yoksa_olcum_ACIKCA_basarisiz(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sayfa_hedefi, "donusturucu_bul", lambda: None)
    belge = tmp_path / "r.docx"
    belge.write_bytes(b"x")

    olcum = sayfa_hedefi.olc(belge)

    assert not olcum.olculdu
    assert "DENETLENMEDİ" in olcum.gerekce


# ---------------------------------------------------------------------------
# Gerçek gövde fixture'ı
# ---------------------------------------------------------------------------


def test_fixture_govdesi_sartnameye_uygun() -> None:
    """Uçtan uca testin kullandığı gövde, denetimden geçiyor olmalı."""
    from fool.rapor import yonerge_ogren

    sartname = yonerge_ogren.ogren(
        FIXTURE / "yonerge.txt", "t", bolum_secimi="MADDE 11"
    ).sartname

    govde = json.loads((FIXTURE / "rapor_govdesi.json").read_text(encoding="utf-8"))
    taslak = {
        "tur": "inceleme",
        "kapak": {
            "bakanlik": "T.C. ÖRNEK BAKANLIĞI",
            "baskanlik": "TEFTİŞ KURULU BAŞKANLIĞI",
            "baslik": "İNCELEME RAPORU",
            "konu": "Fazla çalışma",
            "gorev_emri_tarih": "20.02.2026",
            "gorev_emri_sayi": "2026/88",
            "rapor_tarih": "20.03.2026",
            "rapor_sayi": "2026/14",
            "ek_adedi": "5",
            "mufettis_ad": "Serkan TOPÇUOĞLU",
        },
        "ekler": [{"no": n, "icerik": "belge", "sayfa_sayisi": 1} for n in range(1, 6)],
        "bolumler": govde["bolumler"],
    }

    denetim = uygunluk.denetle(taslak, sartname)

    assert denetim.uygun, [str(b) for b in denetim.engeller]
