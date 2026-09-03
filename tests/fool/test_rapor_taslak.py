"""
Parça parça rapor kurma.

Ölçülmüş sebep: yerel model (google/gemma-4-e4b, LM Studio) ``rapor_yaz``ı
tek dev JSON ile çağırdığında kapak alanlarını düşürdü -- ``gorev_emri_tarih``,
``gorev_emri_sayi``, ``rapor_tarih``, ``rapor_sayi``, ``ek_adedi`` ve
``imza_tarih`` kayboldu. Aynı JSON doğrudan araca verildiğinde eksik çıkmadı,
yani hata araçta değil modelin uzun yapıyı yeniden kurmasında.

Ayrıca 70 sayfalık bir rapor tek çağrıya zaten sığmıyor.
"""

from __future__ import annotations

import json
import zipfile

import pytest

from fool.rapor import arac, taslak


@pytest.fixture(autouse=True)
def _ayri_klasor(tmp_path, monkeypatch):
    """Testler kullanıcının gerçek taslaklarına dokunmasın."""
    monkeypatch.setenv("FOOL_RAPOR_TASLAK_DIR", str(tmp_path / "taslak"))


def test_bolumler_AYRI_cagrilarla_birikiyor() -> None:
    taslak.baslat("t1", "inceleme")
    taslak.bolum_ekle("t1", "I. GİRİŞ", [{"tur": "paragraf", "metin": "Başlandı."}])
    taslak.bolum_ekle("t1", "II. KONU", [{"tur": "paragraf", "metin": "Konu."}])

    durum = taslak.durum("t1")

    assert durum["yazilan_bolumler"] == ["I. GİRİŞ", "II. KONU"]
    assert "III. İNCELEME VE ARAŞTIRMA" in durum["eksik_bolumler"]
    assert durum["tamam_mi"] is False


def test_AYNI_baslik_ikinci_kez_gelince_UZERINE_yaziliyor() -> None:
    """Model bir bölümü düzeltmek isteyince aynı başlıkla tekrar gönderiyor."""
    taslak.baslat("t2", "inceleme")
    taslak.bolum_ekle("t2", "I. GİRİŞ", [{"tur": "paragraf", "metin": "ilk"}])
    taslak.bolum_ekle("t2", "I. GİRİŞ", [{"tur": "paragraf", "metin": "duzeltilmis"}])

    durum = taslak.durum("t2")

    assert durum["yazilan_bolumler"] == ["I. GİRİŞ"]
    assert taslak.yukle("t2").bolumler[0]["ogeler"][0]["metin"] == "duzeltilmis"


def test_kapak_PARCA_PARCA_dolduruluyor() -> None:
    """Tüm kapağı yeniden göndermek, alan düşürmenin olduğu yerdi."""
    taslak.baslat("t3", "inceleme", kapak={"bakanlik": "Tarım ve Orman Bakanlığı"})
    taslak.kapak_guncelle("t3", {"rapor_sayi": "8-2026/3"})
    taslak.kapak_guncelle("t3", {"mufettis_ad": "Cemil KAYA"})

    kapak = taslak.yukle("t3").kapak

    assert kapak["bakanlik"] == "Tarım ve Orman Bakanlığı"
    assert kapak["rapor_sayi"] == "8-2026/3"
    assert kapak["mufettis_ad"] == "Cemil KAYA"


def test_BOS_deger_mevcut_alani_SILMIYOR() -> None:
    """Modelin boş gönderdiği bir alan, dolu olanı silmemeli."""
    taslak.baslat("t4", "inceleme", kapak={"mufettis_ad": "Cemil KAYA"})
    taslak.kapak_guncelle("t4", {"mufettis_ad": "", "konu": "Yeni konu"})

    kapak = taslak.yukle("t4").kapak

    assert kapak["mufettis_ad"] == "Cemil KAYA"
    assert kapak["konu"] == "Yeni konu"


def test_ekler_EKLEME_SIRASINA_gore_numaralaniyor() -> None:
    """MADDE 10(4): ekler rapora ilk konu edilme sırasına göre numaralanır."""
    taslak.baslat("t5", "inceleme")
    taslak.ek_ekle("t5", "Makam Onayı", 2)
    taslak.ek_ekle("t5", "Cevaplı Teftiş Raporu", 3)

    ekler = taslak.yukle("t5").ekler

    assert [e["no"] for e in ekler] == [1, 2]
    assert ekler[1]["icerik"] == "Cevaplı Teftiş Raporu"


def test_SONUC_VE_ONERILER_yonergedeki_SONUC_yerine_geciyor() -> None:
    taslak.baslat("t6", "inceleme")
    for baslik in (
        "I. GİRİŞ", "II. KONU", "III. İNCELEME VE ARAŞTIRMA",
        "IV. TARTIŞMA VE DEĞERLENDİRME", "V. SONUÇ VE ÖNERİLER",
    ):
        taslak.bolum_ekle("t6", baslik, [{"tur": "paragraf", "metin": "x"}])

    assert taslak.durum("t6")["tamam_mi"] is True


def test_taslaktan_DOCX_uretiliyor(tmp_path) -> None:
    taslak.baslat(
        "t7", "inceleme",
        kapak={"bakanlik": "Tarım ve Orman Bakanlığı",
               "baskanlik": "DSİ Teftiş Kurulu Başkanlığı",
               "baslik": "İnceleme Raporu", "konu": "Deneme",
               "gorev_emri_tarih": "01.05.2026", "gorev_emri_sayi": "123",
               "rapor_tarih": "01.06.2026", "rapor_sayi": "8-2026/3",
               "ek_adedi": "1", "mufettis_ad": "Cemil KAYA"},
        imza_yer="Ankara", imza_tarih="01.06.2026",
    )
    taslak.bolum_ekle("t7", "I. GİRİŞ", [{"tur": "paragraf", "metin": "Başlandı."}])
    taslak.ek_ekle("t7", "Makam Onayı", 1)

    hedef = tmp_path / "t7.docx"
    cevap = json.loads(arac.taslak_uret("t7", str(hedef)))

    assert cevap["eksik_alanlar"] == []
    with zipfile.ZipFile(hedef) as paket:
        assert paket.testzip() is None


def test_gecersiz_kimlik_BASKA_KLASORE_yazamiyor() -> None:
    """Taslak kimliği dosya adı oluyor; ``../`` başka yere yazardı."""
    with pytest.raises(taslak.TaslakHatasi, match="geçersiz"):
        taslak.baslat("../kacis", "inceleme")


def test_bilinmeyen_tur_REDDEDILIYOR() -> None:
    with pytest.raises(taslak.TaslakHatasi, match="bilinmeyen"):
        taslak.baslat("t8", "olmayan")


def test_olmayan_taslak_ACIK_hata_veriyor() -> None:
    assert "bulunamadı" in json.loads(arac.taslak_durum("hicyok"))["error"]


def test_taslak_OTURUMDAN_bagimsiz_diskte_duruyor() -> None:
    """Uzun oturumda bağlam özetlenince taslak kaybolmamalı."""
    taslak.baslat("t9", "inceleme")
    taslak.bolum_ekle("t9", "I. GİRİŞ", [{"tur": "paragraf", "metin": "kalici"}])

    # Yeni bir yukleme: bellekteki hicbir sey tasinmiyor.
    assert taslak.yukle("t9").bolumler[0]["ogeler"][0]["metin"] == "kalici"


def test_arac_katmani_da_ayni_sekilde_calisiyor() -> None:
    json.loads(arac.taslak_baslat("t10", "inceleme"))
    json.loads(arac.taslak_kapak("t10", {"mufettis_ad": "Cemil KAYA"}))
    cevap = json.loads(
        arac.taslak_bolum("t10", "I. GİRİŞ", [{"tur": "paragraf", "metin": "x"}])
    )

    assert cevap["yazilan_bolumler"] == ["I. GİRİŞ"]
    assert "mufettis_ad" in cevap["kapak_alanlari"]


# ---------------------------------------------------------------------------
# Modelin GERÇEKTE yaptıkları -- uygulamayı sürerken ölçüldü
# ---------------------------------------------------------------------------


def test_SAYI_gonderilen_alan_cokme_yerine_kabul_ediliyor(tmp_path) -> None:
    """Model ``ek_adedi``yi ``"5"`` yerine ``5`` gönderdi ve üretim çöktü.

    ``AttributeError: 'int' object has no attribute 'strip'`` -- raporun
    tamamı hazırken son adımda. Sayı göndermek makul bir davranış.
    """
    taslak.baslat(
        "s1", "inceleme",
        kapak={"bakanlik": "B", "baskanlik": "K", "baslik": "İnceleme Raporu",
               "konu": "K", "gorev_emri_tarih": "05.03.2026",
               "gorev_emri_sayi": 7118342, "rapor_tarih": "01.06.2026",
               "rapor_sayi": "8-2026/3", "ek_adedi": 5, "mufettis_ad": "Cemil KAYA"},
        imza_yer="Ankara", imza_tarih="01.06.2026",
    )
    taslak.bolum_ekle("s1", "I. GİRİŞ", [{"tur": "paragraf", "metin": "x"}])

    cevap = json.loads(arac.taslak_uret("s1", str(tmp_path / "s1.docx")))

    assert "error" not in cevap
    assert cevap["eksik_alanlar"] == []


def test_bolumler_YONERGEDEKI_siraya_diziliyor() -> None:
    """Model IV'ü III'ten önce gönderdi -- ölçüldü."""
    taslak.baslat("s2", "inceleme")
    for baslik in (
        "IV. TARTIŞMA VE DEĞERLENDİRME",
        "I. GİRİŞ",
        "V. SONUÇ VE ÖNERİLER",
        "III. İNCELEME VE ARAŞTIRMA",
        "II. KONU",
    ):
        taslak.bolum_ekle("s2", baslik, [{"tur": "paragraf", "metin": "x"}])

    sirali = [b["baslik"] for b in taslak.rapor_sozlugu("s2")["bolumler"]]

    assert sirali == [
        "I. GİRİŞ",
        "II. KONU",
        "III. İNCELEME VE ARAŞTIRMA",
        "IV. TARTIŞMA VE DEĞERLENDİRME",
        "V. SONUÇ VE ÖNERİLER",
    ]


def test_YONERGEDE_OLMAYAN_bolum_atilmiyor_sona_gidiyor() -> None:
    """MADDE 8(7): müfettiş kendi alt bölümünü açabiliyor."""
    taslak.baslat("s3", "inceleme")
    taslak.bolum_ekle("s3", "EK DEĞERLENDİRME", [{"tur": "paragraf", "metin": "x"}])
    taslak.bolum_ekle("s3", "I. GİRİŞ", [{"tur": "paragraf", "metin": "x"}])

    sirali = [b["baslik"] for b in taslak.rapor_sozlugu("s3")["bolumler"]]

    assert sirali == ["I. GİRİŞ", "EK DEĞERLENDİRME"]


def test_dogrudan_rapor_yaz_da_SIRALIYOR(tmp_path) -> None:
    """Taslak kullanmayan çağrı da yönerge sırasına uymalı."""
    import xml.etree.ElementTree as ET
    import zipfile as _zip

    istek = {
        "tur": "inceleme",
        "kapak": {"mufettis_ad": "Cemil KAYA"},
        "bolumler": [
            {"baslik": "II. KONU", "ogeler": [{"tur": "paragraf", "metin": "konu"}]},
            {"baslik": "I. GİRİŞ", "ogeler": [{"tur": "paragraf", "metin": "giris"}]},
        ],
    }
    hedef = tmp_path / "sirali.docx"
    arac.rapor_yaz(json.dumps(istek), str(hedef))

    with _zip.ZipFile(hedef) as paket:
        kok = ET.fromstring(paket.read("word/document.xml"))

    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    metinler = [t.text or "" for t in kok.iter(f"{W}t")]

    assert metinler.index("I. GİRİŞ") < metinler.index("II. KONU")


def test_baslat_VAR_OLAN_taslagin_uzerine_YAZMIYOR() -> None:
    """Ölçüldü: model bölümleri yazdıktan sonra ``baslat``ı tekrar çağırdı.

    Beş bölüm silindi; taslakta yalnızca ekler ve kapak kaldı. Modelin turu
    yeniden başlatması olağan, 70 sayfalık işi sıfırlaması değil.
    """
    taslak.baslat("k1", "inceleme")
    taslak.bolum_ekle("k1", "I. GİRİŞ", [{"tur": "paragraf", "metin": "yazildi"}])

    with pytest.raises(taslak.TaslakHatasi, match="zaten var"):
        taslak.baslat("k1", "inceleme")

    assert taslak.durum("k1")["yazilan_bolumler"] == ["I. GİRİŞ"]


def test_sifirla_ACIKCA_istenirse_bastan_basliyor() -> None:
    taslak.baslat("k2", "inceleme")
    taslak.bolum_ekle("k2", "I. GİRİŞ", [{"tur": "paragraf", "metin": "eski"}])

    taslak.baslat("k2", "inceleme", sifirla=True)

    assert taslak.durum("k2")["yazilan_bolumler"] == []


def test_BOS_taslagi_yeniden_baslatmak_serbest() -> None:
    """Hiçbir şey yazılmamışsa kaybedilecek bir şey de yok."""
    taslak.baslat("k3", "inceleme")
    taslak.baslat("k3", "inceleme", kapak={"mufettis_ad": "Cemil KAYA"})

    assert taslak.yukle("k3").kapak["mufettis_ad"] == "Cemil KAYA"


def test_arac_katmani_da_KORUYOR() -> None:
    json.loads(arac.taslak_baslat("k4", "inceleme"))
    json.loads(arac.taslak_bolum("k4", "I. GİRİŞ", [{"tur": "paragraf", "metin": "x"}]))

    cevap = json.loads(arac.taslak_baslat("k4", "inceleme"))

    assert "zaten var" in cevap["error"]


# ---------------------------------------------------------------------------
# Sıradaki adım -- zayıf modeli akışta tutmak
# ---------------------------------------------------------------------------


def test_her_cevap_SIRADAKI_ADIMI_soyluyor() -> None:
    """Ölçüldü: model 11 adımlık planın 2. bölümünden sonra durdu.

    "Rapor tamamlandı" dedi; üç bölüm ve kapağın yarısı eksikti. Planı modelin
    hafızasına bırakmak yerine her cevapta yeniden söylemek dayanıklı.
    """
    taslak.baslat("n1", "inceleme")

    adim = taslak.durum("n1")["siradaki_adim"]

    assert "HENÜZ BİTMEDİ" in adim
    assert "I. GİRİŞ" in adim
    assert "rapor_taslak_bolum" in adim


def test_siradaki_adim_BOLUM_yazildikca_ilerliyor() -> None:
    taslak.baslat("n2", "inceleme")
    taslak.bolum_ekle("n2", "I. GİRİŞ", [{"tur": "paragraf", "metin": "x"}])

    assert "II. KONU" in taslak.durum("n2")["siradaki_adim"]


def test_bolumler_bitince_EKSIK_KAPAK_alanlarina_yonlendiriyor() -> None:
    taslak.baslat("n3", "inceleme")
    for baslik in (
        "I. GİRİŞ", "II. KONU", "III. İNCELEME VE ARAŞTIRMA",
        "IV. TARTIŞMA VE DEĞERLENDİRME", "V. SONUÇ",
    ):
        taslak.bolum_ekle("n3", baslik, [{"tur": "paragraf", "metin": "x"}])

    adim = taslak.durum("n3")["siradaki_adim"]

    assert "rapor_taslak_kapak" in adim
    assert "gorev_emri_sayi" in adim


def test_her_sey_tamamsa_URET_diyor() -> None:
    taslak.baslat(
        "n4", "inceleme",
        kapak={a: "x" for a in taslak._ZORUNLU_KAPAK},
    )
    for baslik in (
        "I. GİRİŞ", "II. KONU", "III. İNCELEME VE ARAŞTIRMA",
        "IV. TARTIŞMA VE DEĞERLENDİRME", "V. SONUÇ",
    ):
        taslak.bolum_ekle("n4", baslik, [{"tur": "paragraf", "metin": "x"}])
    taslak.ek_ekle("n4", "Makam Onayı", 1)
    taslak.ozet_yaz("n4", ["Özet."])

    assert "rapor_taslak_uret" in taslak.durum("n4")["siradaki_adim"]


# ---------------------------------------------------------------------------
# Şekli anlaşılmayan girdi SESSİZCE kabul edilmiyor
# ---------------------------------------------------------------------------
#
# Ölçüldü: model bölüm öğesi olarak şunu gönderdi ve kod kabul etti --
# ``tur`` yok sayıldı, ``metin`` boş kaldı, beş bölümü de BOŞ olan bir rapor
# üretildi ve araç "başarılı" dedi. Resmî evrakta en kötü sonuç bu: hata
# görünmüyor, belge boş çıkıyor.

MODELIN_GONDERDIGI = [
    {'"icerik"': [{'"metin"': [{'"aciklama"': 1, '"tur"': 0}], '"paragraf"': 1}]}
]


def test_modelin_BOZUK_yapisi_reddediliyor() -> None:
    taslak.baslat("v1", "inceleme")

    with pytest.raises(taslak.TaslakHatasi, match="metin"):
        taslak.bolum_ekle("v1", "I. GİRİŞ", MODELIN_GONDERDIGI)

    # Taslak KIRLENMEDI.
    assert taslak.durum("v1")["yazilan_bolumler"] == []


def test_hata_DOGRU_SEKLI_soyluyor() -> None:
    """Model düzeltip tekrar gönderebilmeli; "geçersiz" demek yetmez."""
    taslak.baslat("v2", "inceleme")

    with pytest.raises(taslak.TaslakHatasi) as bilgi:
        taslak.bolum_ekle("v2", "I. GİRİŞ", MODELIN_GONDERDIGI)

    assert '"tur": "paragraf"' in str(bilgi.value)


def test_BOS_bolum_reddediliyor() -> None:
    taslak.baslat("v3", "inceleme")

    with pytest.raises(taslak.TaslakHatasi, match="boş gönderildi"):
        taslak.bolum_ekle("v3", "I. GİRİŞ", [])


def test_bilinmeyen_OGE_TURU_reddediliyor() -> None:
    taslak.baslat("v4", "inceleme")

    with pytest.raises(taslak.TaslakHatasi, match="bilinmeyen tür"):
        taslak.bolum_ekle("v4", "I. GİRİŞ", [{"tur": "sekil", "metin": "x"}])


def test_eksik_TABLO_alanlari_reddediliyor() -> None:
    taslak.baslat("v5", "inceleme")

    with pytest.raises(taslak.TaslakHatasi, match="basliklar"):
        taslak.bolum_ekle("v5", "IV. TARTIŞMA", [{"tur": "tablo", "baslik": "Tablo 1"}])


def test_TANINMAYAN_kapak_alani_reddediliyor() -> None:
    """Model ``rapor_tarih`` yerine ``rapor_date`` yazdı; tarih [EKSİK] kaldı."""
    taslak.baslat("v6", "inceleme")

    with pytest.raises(taslak.TaslakHatasi, match="rapor_date"):
        taslak.kapak_guncelle("v6", {"rapor_date": "01.06.2026"})


def test_dogru_kapak_alani_KABUL_ediliyor() -> None:
    taslak.baslat("v7", "inceleme")
    taslak.kapak_guncelle("v7", {"rapor_tarih": "01.06.2026"})

    assert taslak.yukle("v7").kapak["rapor_tarih"] == "01.06.2026"


def test_dogrudan_rapor_yaz_da_BOZUGU_reddediyor(tmp_path) -> None:
    istek = {
        "tur": "inceleme",
        "kapak": {"mufettis_ad": "Cemil KAYA"},
        "bolumler": [{"baslik": "I. GİRİŞ", "ogeler": MODELIN_GONDERDIGI}],
    }

    cevap = json.loads(arac.rapor_yaz(json.dumps(istek), str(tmp_path / "r.docx")))

    assert "error" in cevap
    assert not (tmp_path / "r.docx").exists()


def test_ozet_SONRADAN_yazilabiliyor() -> None:
    """MADDE 7 özeti raporun uzunluğuna göre ölçüyor: önce metin, sonra özet."""
    taslak.baslat("o1", "inceleme")
    taslak.bolum_ekle("o1", "I. GİRİŞ", [{"tur": "paragraf", "metin": "x"}])

    taslak.ozet_yaz("o1", ["Kamu zararı oluşmadığı değerlendirilmiştir."])

    assert taslak.yukle("o1").ozet == ["Kamu zararı oluşmadığı değerlendirilmiştir."]


def test_BOS_ozet_reddediliyor() -> None:
    taslak.baslat("o2", "inceleme")

    with pytest.raises(taslak.TaslakHatasi, match="MADDE 7"):
        taslak.ozet_yaz("o2", ["", "   "])


def test_ekler_bitince_OZETE_yonlendiriyor() -> None:
    taslak.baslat("o3", "inceleme", kapak={a: "x" for a in taslak._ZORUNLU_KAPAK})
    for baslik in (
        "I. GİRİŞ", "II. KONU", "III. İNCELEME VE ARAŞTIRMA",
        "IV. TARTIŞMA VE DEĞERLENDİRME", "V. SONUÇ",
    ):
        taslak.bolum_ekle("o3", baslik, [{"tur": "paragraf", "metin": "x"}])
    taslak.ek_ekle("o3", "Makam Onayı", 1)

    assert "rapor_taslak_ozet" in taslak.durum("o3")["siradaki_adim"]

    taslak.ozet_yaz("o3", ["Özet."])

    assert "rapor_taslak_uret" in taslak.durum("o3")["siradaki_adim"]


# ---------------------------------------------------------------------------
# "Örnek rapordan kısa olamaz" -- dilek değil, ölçülen kural
# ---------------------------------------------------------------------------


def test_hedef_uzunluk_ORNEKTEN_olculuyor() -> None:
    """Kullanıcının şartı ölçülebilir hâle geliyor: örneği ölç, hedef yap."""
    taslak.baslat(
        "u1", "inceleme",
        hedef_uzunluk={"III. İNCELEME VE ARAŞTIRMA": 9230},
    )
    taslak.bolum_ekle(
        "u1", "III. İNCELEME VE ARAŞTIRMA", [{"tur": "paragraf", "metin": "Kısa."}]
    )

    durum = taslak.durum("u1")

    assert durum["kisa_bolumler"][0]["hedef"] == 9230
    assert durum["kisa_bolumler"][0]["mevcut"] < 100


def test_KISA_bolum_varken_rapor_TAMAM_sayilmiyor() -> None:
    """Aksi hâlde model ince bir raporla "bitti" diyebiliyordu."""
    hedefler = {
        b: 1000
        for b in (
            "I. GİRİŞ", "II. KONU", "III. İNCELEME VE ARAŞTIRMA",
            "IV. TARTIŞMA VE DEĞERLENDİRME", "V. SONUÇ",
        )
    }
    taslak.baslat("u2", "inceleme", hedef_uzunluk=hedefler)
    for baslik in hedefler:
        taslak.bolum_ekle("u2", baslik, [{"tur": "paragraf", "metin": "Kısa."}])

    assert taslak.durum("u2")["tamam_mi"] is False


def test_YETERINCE_dolu_bolum_kisa_sayilmiyor() -> None:
    """Birebir eşitlik istenmiyor; %60 eşiği yeterli."""
    taslak.baslat("u3", "inceleme", hedef_uzunluk={"I. GİRİŞ": 100})
    taslak.bolum_ekle("u3", "I. GİRİŞ", [{"tur": "paragraf", "metin": "x" * 70}])

    assert taslak.durum("u3")["kisa_bolumler"] == []


def test_siradaki_adim_KAC_KARAKTER_yazilacagini_soyluyor() -> None:
    taslak.baslat("u4", "inceleme", hedef_uzunluk={"I. GİRİŞ": 288})

    adim = taslak.durum("u4")["siradaki_adim"]

    assert "~288 karakter" in adim
    assert "en az 172 karakter" in adim


def test_kisa_bolum_icin_AYNI_basligi_tekrar_gondermesi_soyleniyor() -> None:
    taslak.baslat("u5", "inceleme", hedef_uzunluk={b: 1000 for b in (
        "I. GİRİŞ", "II. KONU", "III. İNCELEME VE ARAŞTIRMA",
        "IV. TARTIŞMA VE DEĞERLENDİRME", "V. SONUÇ")})
    for baslik in ("I. GİRİŞ", "II. KONU", "III. İNCELEME VE ARAŞTIRMA",
                   "IV. TARTIŞMA VE DEĞERLENDİRME", "V. SONUÇ"):
        taslak.bolum_ekle(baslik="x" and baslik, kimlik="u5",
                          ogeler=[{"tur": "paragraf", "metin": "Kısa."}])

    adim = taslak.durum("u5")["siradaki_adim"]

    assert "ÇOK KISA" in adim
    assert "rapor_taslak_bolum" in adim


def test_tablo_ve_alt_basliklar_da_uzunluga_sayiliyor() -> None:
    """Bölümün doluluğu yalnızca paragraflardan ibaret değil."""
    taslak.baslat("u6", "inceleme")
    taslak.bolum_ekle("u6", "IV. TARTIŞMA VE DEĞERLENDİRME", [
        {"tur": "alt_baslik", "metin": "İlgili Hukuk"},
        {"tur": "tablo", "baslik": "Tablo 1: Süreler",
         "basliklar": ["Madde", "Süre"], "satirlar": [["2", "2 Yıl 4 Ay"]]},
    ])

    uzunluk = taslak.durum("u6")["uzunluk"]["IV. TARTIŞMA VE DEĞERLENDİRME"]

    assert uzunluk > len("İlgili Hukuk")


def test_hedef_YOKSA_kisalik_denetimi_yapilmiyor() -> None:
    """Örnek verilmemişse kıyaslanacak bir şey yok."""
    taslak.baslat("u7", "inceleme")
    for baslik in ("I. GİRİŞ", "II. KONU", "III. İNCELEME VE ARAŞTIRMA",
                   "IV. TARTIŞMA VE DEĞERLENDİRME", "V. SONUÇ"):
        taslak.bolum_ekle("u7", baslik, [{"tur": "paragraf", "metin": "Kısa."}])

    assert taslak.durum("u7")["tamam_mi"] is True
