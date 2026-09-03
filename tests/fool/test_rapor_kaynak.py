"""
Kaynak belge okuma, kalite denetimi, bağlam sınırına göre parçalama.

Bu testlerin varlık sebebi ölçülmüş bir hata: kullanıcının 72 sayfalık
"DSİ Disiplin Soruşturma Rehberi" PDF'inin metin katmanında küçük "i" harfi
yok. İki bağımsız çıkarıcı (pdftotext ve pdfminer.six) aynı sonucu veriyor,
PDF'in 404 font eşlemesinde 'i' hedefi yalnızca 69 kez geçiyor. Yani metin
kurtarılamıyor -- ama sessizce modele giderse rapor "disiplin" yerine
"dspln" öğrenmiş bir modelden çıkar.
"""

from __future__ import annotations

import zipfile

import pytest

from fool.rapor.cozumle import (
    bolumlere_ayir,
    eksik_bolumler,
    iskelet_cikar,
    tur_tahmin,
)
from fool.rapor.kaynak import (
    ASGARI_HARF,
    Belge,
    Kalite,
    kalite_olc,
    kart_cikar,
    oku,
    parcala,
    token_tahmini,
)

# Gercek bir Turkce paragraf: 'i' orani ~%8 civari.
SAGLAM = (
    "Memur disiplin rejiminin genel çerçevesi yasal düzenleme ile "
    "belirlenmiştir. Ayrıca ilgili yönetmeliklerle de memur disiplin "
    "hukukunun usul ve esasları düzenleme altına alınmıştır. Diğer taraftan "
    "mevzuat ve genellikle yargı kararları ile ortaya çıkan temel ilkelere "
    "uyulması da son derece önemlidir. Nitekim kamu hizmetinin etkin ve "
    "verimli yürütülmesi için yapılan disiplin soruşturmalarında ve tayin "
    "edilecek cezalarda temel ilkelere riayet edilmesi hukuk devletinin bir "
    "gereğidir. Disiplin suçu; Devlet memurlarının statülerine ilişkin "
    "hükümlere uymaması sebebiyle kurum düzeninin bozulmasına sebep olan "
    "kanuna aykırı fiil ve davranışlara denir."
)

# pdfminer'in urettigi hâl: 'i' harfi tamamen ATILMIS.
HARFI_ATILMIS = SAGLAM.replace("i", "")

# pdftotext'in urettigi hâl: 'i' yerine BOSLUK konmus.
HARFI_BOSLUK = SAGLAM.replace("i", " ")


def _docx_yaz(yol, satirlar: list[str]) -> None:
    """Testlik asgari ``.docx``."""
    govde = "".join(
        f"<w:p><w:r><w:t>{s}</w:t></w:r></w:p>" for s in satirlar
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main">'
        f"<w:body>{govde}</w:body></w:document>"
    )
    with zipfile.ZipFile(yol, "w") as paket:
        paket.writestr("word/document.xml", xml)


# ---------------------------------------------------------------------------
# Kalite denetimi
# ---------------------------------------------------------------------------


def test_saglam_turkce_metin_GUVENILIR() -> None:
    kalite = kalite_olc(SAGLAM * 2)

    assert kalite.guvenilir
    # Olculdu: gercek Yonerge belgesinde %9,05, ornek raporda %7,39.
    assert 0.05 < kalite.i_orani < 0.12


def test_i_harfi_ATILMIS_metin_REDDEDILIYOR() -> None:
    """pdfminer'in verdiği hâl: "disiplin" -> "dspln"."""
    kalite = kalite_olc(HARFI_ATILMIS * 2)

    assert not kalite.guvenilir
    assert "'i'" in kalite.gerekce
    assert "OCR" in kalite.gerekce


def test_i_harfi_BOSLUGA_cevrilmis_metin_REDDEDILIYOR() -> None:
    """pdftotext'in verdiği hâl: "disiplin" -> "d s pl n"."""
    kalite = kalite_olc(HARFI_BOSLUK * 2)

    assert not kalite.guvenilir
    # Iki isaretten HERHANGI biri yakalamali.
    assert kalite.i_orani < 0.02 or kalite.tek_harf_orani > 0.20


def test_KISA_metinde_oran_olculmuyor() -> None:
    """400 harfin altında oran anlamsız; yanlış alarm vermek işi durdururdu."""
    kalite = kalite_olc("Kısa bir not.")

    assert kalite.guvenilir
    assert kalite.harf_sayisi < ASGARI_HARF


def test_TURKCE_OLMAYAN_metin_i_oranindan_reddedilmiyor() -> None:
    """İngilizce bir ek 'i' oranı düşük diye bozuk sayılmamalı."""
    ingilizce = (
        "The contractor shall be jointly and severally liable for all damages "
        "awarded by the competent court. Payment was made in full and the "
        "recourse action was brought before the statutory deadline expired. "
    ) * 4

    assert kalite_olc(ingilizce).guvenilir


def test_kalite_dogrudan_dogruluk_degeri_gibi_kullanilabiliyor() -> None:
    assert bool(Kalite(True))
    assert not bool(Kalite(False, "bozuk"))


# ---------------------------------------------------------------------------
# Okuma
# ---------------------------------------------------------------------------


def test_docx_okunuyor_ve_kalite_olculuyor(tmp_path) -> None:
    yol = tmp_path / "belge.docx"
    _docx_yaz(yol, [SAGLAM, SAGLAM])

    belge = oku(yol)

    assert belge.kalite.guvenilir
    assert "disiplin" in belge.metin


def test_bozuk_docx_okunuyor_ama_GUVENILMEZ_isaretleniyor(tmp_path) -> None:
    """Okuma hata fırlatmıyor: karar çağırana ait, ama işaret görünür."""
    yol = tmp_path / "bozuk.docx"
    _docx_yaz(yol, [HARFI_ATILMIS, HARFI_ATILMIS])

    belge = oku(yol)

    assert not belge.kalite.guvenilir


def test_desteklenmeyen_tur_ACIKCA_reddediliyor(tmp_path) -> None:
    yol = tmp_path / "x.rtf"
    yol.write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="desteklenmeyen"):
        oku(yol)


# ---------------------------------------------------------------------------
# Bağlam sınırı -- 64k/128k pencere
# ---------------------------------------------------------------------------


def test_parcalar_TOKEN_BUTCESINI_asmiyor() -> None:
    """Model penceresi 64-128 bin; hiçbir parça bütçeyi geçmemeli."""
    belge = Belge(
        yol=__import__("pathlib").Path("uzun.pdf"),
        sayfalar=[SAGLAM * 3 for _ in range(40)],
        kalite=Kalite(True),
    )

    parcalar = parcala(belge, token_butcesi=2000)

    assert parcalar
    for parca in parcalar:
        assert token_tahmini(parca.metin) <= 2000


def test_TEK_SAYFA_butceden_buyukse_o_sayfa_da_boluniyor() -> None:
    """DOCX'te sayfa sınırı yok: Yönerge tek "sayfa"da ~135 bin token.

    Yalnızca sayfa sınırında bölseydik bu belge tek parça kalır ve hiçbir
    pencereye sığmazdı -- ölçülen hâli tam olarak buydu.
    """
    belge = Belge(
        yol=__import__("pathlib").Path("yonerge.docx"),
        sayfalar=["\n".join([SAGLAM] * 200)],
        kalite=Kalite(True),
    )

    parcalar = parcala(belge, token_butcesi=1500)

    assert len(parcalar) > 1
    for parca in parcalar:
        assert token_tahmini(parca.metin) <= 1500


def test_parca_HANGI_SAYFADAN_geldigini_hatirliyor() -> None:
    """Rapora atıf verilecekse sayfa numarası kesin bilinmeli."""
    belge = Belge(
        yol=__import__("pathlib").Path("delil.pdf"),
        sayfalar=[f"sayfa {n} " + SAGLAM for n in range(1, 7)],
        kalite=Kalite(True),
    )

    parcalar = parcala(belge, token_butcesi=400)

    assert parcalar[0].ilk_sayfa == 1
    assert parcalar[-1].son_sayfa == 6
    assert "delil.pdf s." in parcalar[0].atif


# ---------------------------------------------------------------------------
# Delil kartı
# ---------------------------------------------------------------------------


def test_delil_karti_tarih_sayi_ve_kisi_cikariyor() -> None:
    belge = Belge(
        yol=__import__("pathlib").Path("dilekce.docx"),
        sayfalar=[
            "Şikâyet dilekçesi. 10.04.2026 tarih ve 7032434 sayılı yazı ile "
            "Sefer TOPKAFA hakkında bildirimde bulunulmuştur."
        ],
        kalite=Kalite(True),
    )

    kart = kart_cikar(belge, ek_no=3)

    assert kart.ek_no == 3
    assert kart.tarih == "10.04.2026"
    assert kart.sayi == "7032434"
    assert "Sefer TOPKAFA" in kart.kisiler
    assert kart.tur == "şikâyet dilekçesi"


def test_delil_karti_BULUNMAYAN_alani_UYDURMUYOR() -> None:
    """Bir dilekçenin tarihini tahmin etmek, o tarihi rapora sokmak olur."""
    belge = Belge(
        yol=__import__("pathlib").Path("notsuz.docx"),
        sayfalar=["Herhangi bir tarih ya da sayı içermeyen kısa bir not."],
        kalite=Kalite(True),
    )

    kart = kart_cikar(belge, ek_no=1)

    assert kart.tarih == ""
    assert kart.sayi == ""


def test_delil_karti_satiri_BAGLAMA_sigacak_kadar_kisa() -> None:
    """On belgenin künyesi birlikte pencereye sığmalı."""
    belge = Belge(
        yol=__import__("pathlib").Path("dilekce.docx"),
        sayfalar=["İfade tutanağı. 01.06.2026 tarihinde Ersin ÇULHA ifade vermiştir."],
        kalite=Kalite(True),
    )

    satir = kart_cikar(belge, 2).satir()

    assert token_tahmini(satir) < 100


# ---------------------------------------------------------------------------
# Rapor çözümleme: örnekten öğrenme ve yarım raporu tamamlama
# ---------------------------------------------------------------------------

_TAM_RAPOR = [
    "İNCELEME RAPORU",
    "I. GİRİŞ",
    "Makam Olur'u doğrultusunda incelemeye başlanmıştır. (Ek:1/1)",
    "II. KONU",
    "Rücuen tazmin davalarında zamanaşımı süresi incelenmiştir.",
    "III. İNCELEME VE ARAŞTIRMA",
    "Bilgi ve belgeler talep edilmiş, ifadeler alınmıştır. (Ek:5/1-40)",
    "IV. TARTIŞMA VE DEĞERLENDİRME",
    "Mevzuat açısından konu değerlendirildiğinde;",
    "V. SONUÇ VE ÖNERİLER",
    "A. Disiplin Yönünden",
    "Disiplin yönünden yapılacak işlem bulunmamaktadır.",
    "B. Cezai Yönden",
    "Cezai yönden yapılacak işlem bulunmamaktadır.",
    "Görüş ve kanaatine varılmıştır.",
]


def _rapor_belgesi(tmp_path, satirlar: list[str], ad: str = "rapor.docx") -> Belge:
    yol = tmp_path / ad
    _docx_yaz(yol, satirlar)
    return oku(yol)


def test_rapor_BOLUMLERINE_ayriliyor(tmp_path) -> None:
    cozumlenmis = bolumlere_ayir(_rapor_belgesi(tmp_path, _TAM_RAPOR))

    assert cozumlenmis.basliklar() == [
        "I. GİRİŞ",
        "II. KONU",
        "III. İNCELEME VE ARAŞTIRMA",
        "IV. TARTIŞMA VE DEĞERLENDİRME",
        "V. SONUÇ VE ÖNERİLER",
    ]


def test_rapor_TURU_bolum_basliklarindan_bulunuyor(tmp_path) -> None:
    tur = tur_tahmin(bolumlere_ayir(_rapor_belgesi(tmp_path, _TAM_RAPOR)))

    assert tur is not None
    assert tur.kimlik == "inceleme"


def test_TAMAMLANMIS_rapor_eksiksiz_gorunuyor(tmp_path) -> None:
    """Yönerge "V. SONUÇ" diyor, uygulamada "V. SONUÇ VE ÖNERİLER" yazılıyor.

    Tam eşleşme arayınca bitmiş bir rapora "sonuç bölümü yok" deniyordu.
    """
    cozumlenmis = bolumlere_ayir(_rapor_belgesi(tmp_path, _TAM_RAPOR))

    assert eksik_bolumler(cozumlenmis) == []


def test_YARIM_rapor_eksikleri_bildiriyor(tmp_path) -> None:
    yarim = _TAM_RAPOR[:7]  # IV ve V hic yok
    cozumlenmis = bolumlere_ayir(_rapor_belgesi(tmp_path, yarim))

    eksikler = {e.baslik: e.durum for e in eksik_bolumler(cozumlenmis)}

    assert "IV. TARTIŞMA VE DEĞERLENDİRME" in eksikler
    assert "V. SONUÇ" in eksikler


def test_BASLIGI_olan_ama_BOS_bolum_de_eksik_sayiliyor(tmp_path) -> None:
    """Yarım raporda en sık hâl: başlık atılmış, altı yazılmamış."""
    yarim = [*_TAM_RAPOR[:8], "V. SONUÇ VE ÖNERİLER"]
    cozumlenmis = bolumlere_ayir(_rapor_belgesi(tmp_path, yarim))

    eksikler = {e.baslik: e.durum for e in eksik_bolumler(cozumlenmis)}

    assert eksikler.get("V. SONUÇ") == "boş"


def test_iskelet_ornegin_ONDA_BIRINDEN_kucuk(tmp_path) -> None:
    """Örneğin tamamı yerine iskeleti veriliyor -- bağlam bunun için.

    Ölçüldü (gerçek örnek rapor): 6.384 token -> 226 token.
    """
    # Gercekci uzun rapor: bolumler BIR kez geciyor, govde uzun.
    uzun = [*_TAM_RAPOR[:6], *([SAGLAM] * 60), *_TAM_RAPOR[6:]]

    belge = _rapor_belgesi(tmp_path, uzun)
    iskelet = iskelet_cikar(belge)

    assert token_tahmini(iskelet.metin()) < token_tahmini(belge.metin) / 10


def test_iskelet_TEKRARLAYAN_baslikla_sismiyor(tmp_path) -> None:
    """İskelet yapıyı anlatıyor; belgedeki tekrarları değil."""
    belge = _rapor_belgesi(tmp_path, _TAM_RAPOR * 20)
    iskelet = iskelet_cikar(belge)

    # 20 kez tekrarlanan 5 bolum -> yine 5 bolum.
    assert len(iskelet.bolumler) == 5
    assert token_tahmini(iskelet.metin()) < 400


def test_iskelet_EK_ATIF_bicimini_ogreniyor(tmp_path) -> None:
    iskelet = iskelet_cikar(_rapor_belgesi(tmp_path, _TAM_RAPOR))

    assert "(Ek:1/1)" in iskelet.ek_atif_bicimi
    assert "(Ek:5/1-40)" in iskelet.ek_atif_bicimi


def test_iskelet_SONUC_alt_basliklarini_ogreniyor(tmp_path) -> None:
    """"Disiplin Yönünden" ve "Cezai Yönden" -- iki farklı yazım."""
    iskelet = iskelet_cikar(_rapor_belgesi(tmp_path, _TAM_RAPOR))

    assert "A. Disiplin Yönünden" in iskelet.alt_basliklar
    assert "B. Cezai Yönden" in iskelet.alt_basliklar


def test_iskelet_ornek_METNI_TASIMIYOR(tmp_path) -> None:
    """Örneğin cümleleri yeni rapora sızmamalı.

    Sızarsa başka bir soruşturmanın isimleri ve tarihleri yeni raporda
    çıkar -- resmî evrakta en tehlikeli hata biçimi.
    """
    satirlar = [
        *_TAM_RAPOR,
        "Davacı Sefer TOPKAFA şoför olarak çalışmakta iken işten çıkarılmıştır.",
    ]
    iskelet = iskelet_cikar(_rapor_belgesi(tmp_path, satirlar))

    assert "TOPKAFA" not in iskelet.metin()


# ---------------------------------------------------------------------------
# Üslup ÖRNEKTEN öğreniliyor, sabit listeden değil
# ---------------------------------------------------------------------------


def test_kaliplar_ORNEGIN_kendi_cumle_sonlarindan_ogreniliyor(tmp_path) -> None:
    """Örnek değişebilir; sabit bir kalıp listesi yeni örneği ıskalardı."""
    satirlar = [
        *_TAM_RAPOR,
        "Ödeme işlemi usulüne uygun olarak gerçekleştirilmiştir.",
        "İkinci ödeme de aynı şekilde gerçekleştirilmiştir.",
        "Üçüncü ödeme yine gerçekleştirilmiştir.",
    ]
    iskelet = iskelet_cikar(_rapor_belgesi(tmp_path, satirlar))

    assert any("gerçekleştirilmiştir" in k for k in iskelet.kalip_ifadeler)


def test_TEK_KEZ_gecen_bitis_kalip_sayilmiyor(tmp_path) -> None:
    """Bir kez geçen cümle sonu üslup değil, o cümlenin kendisi."""
    satirlar = [*_TAM_RAPOR, "Bu cümle bir kez yazılmıştır."]
    iskelet = iskelet_cikar(_rapor_belgesi(tmp_path, satirlar))

    assert not any("bir kez yazılmıştır" in k for k in iskelet.kalip_ifadeler)


def test_ISIM_ve_UNVANLAR_kalip_sayilmiyor(tmp_path) -> None:
    """Şirket adları kalıp sayılınca örneğin İÇERİĞİ yeni rapora sızıyordu."""
    satirlar = [
        *_TAM_RAPOR,
        "Yüklenici GÖK-ER Taşımacılık Sınır Tic.",
        "Karşı taraf GÖK-ER Taşımacılık Sınır Tic.",
        "Ayrıca GÖK-ER Taşımacılık Sınır Tic.",
    ]
    metin = iskelet_cikar(_rapor_belgesi(tmp_path, satirlar)).metin()

    assert "Taşımacılık" not in metin
    assert "GÖK-ER" not in metin


def test_RAKAMLI_bitisler_kalip_sayilmiyor(tmp_path) -> None:
    """"2 Yıl 4 Ay" bir üslup değil, bir ölçüm."""
    satirlar = [*_TAM_RAPOR, "Süre 2 Yıl 4 Ay.", "Diğer süre 2 Yıl 4 Ay."]
    iskelet = iskelet_cikar(_rapor_belgesi(tmp_path, satirlar))

    assert not any(any(k.isdigit() for k in kalip) for kalip in iskelet.kalip_ifadeler)
