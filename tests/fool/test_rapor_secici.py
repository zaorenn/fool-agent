"""
Seçici okuma ve biçim devralma.

İki ayrı kullanıcı şartı, iki ayrı yön:

* Büyük KAYNAK belgeler (rehber, mevzuat) sorguya göre kısmen okunuyor --
  73 sayfalık rehber ~44 bin, Yönerge ~135 bin token; ikisi de tek başına
  64 binlik pencereyi zorluyor.
* Örnek rapor ve TAMAMLANACAK yarım rapor her zaman EKSİKSİZ okunuyor ve
  yarım rapor kendi fontuyla tamamlanıyor.
"""

from __future__ import annotations

import pathlib
import zipfile

from fool.rapor.bicim_devral import devral, yonergeye_uygunluk
from fool.rapor.kaynak import Belge, Kalite, token_tahmini
from fool.rapor.secici import ilgili_kesitler, kesitlere_ayir, terimler
from fool.rapor.yonerge import Bicim

_MEVZUAT = """MADDE 5- (1) Rapor; kapak, özet, rapor metni, ek dizini ve eklerden oluşur.
MADDE 6- (1) Raporların kapağında Bakanlığın ve Başkanlığın adı, raporun adını belirten başlık, raporun konusu, görev emrinin tarih ve sayısı yer alır.
MADDE 8- (3) Rapor metni, 1 satır aralığında ve iki yana yaslanmış biçimde, Times New Roman yazı tipinde 12 punto kullanılarak yazılır.
MADDE 17- (1) İnceleme ve soruşturma görevleri kapsamında düzenlenecek raporlar; I. GİRİŞ, II. KONU, III. İNCELEME VE ARAŞTIRMA, IV. TARTIŞMA VE DEĞERLENDİRME, V. SONUÇ bölümlerinden oluşur.
MADDE 30- (1) Disiplin cezalarında zamanaşımı süreleri kanunda gösterilmiştir. Uyarma ve kınama cezalarında bir ay içinde soruşturmaya başlanır.
MADDE 31- (1) Görevden uzaklaştırma tedbiri, kamu hizmetinin gerektirdiği hâllerde uygulanan geçici bir tedbirdir.
"""


def _belge(metin: str, ad: str = "mevzuat.docx") -> Belge:
    return Belge(yol=pathlib.Path(ad), sayfalar=[metin], kalite=Kalite(True))


# ---------------------------------------------------------------------------
# Terim çıkarma
# ---------------------------------------------------------------------------


def test_turkce_ekler_govdeleniyor() -> None:
    """"raporların" ile "rapor" aynı terim sayılmazsa arama tutmaz."""
    bulunan = terimler("raporların raporu rapor")

    assert len(set(bulunan)) == 1


def test_durak_kelimeler_ve_sayilar_atiliyor() -> None:
    bulunan = terimler("ve veya ile bir 2023 rapor")

    assert "rapor" in bulunan
    assert "veya" not in bulunan
    assert "2023" not in bulunan


# ---------------------------------------------------------------------------
# Kesitlere ayırma
# ---------------------------------------------------------------------------


def test_UZUN_madde_satiri_da_baslik_sayiliyor() -> None:
    """Ölçülmüş hata: DOCX'te her fıkra tek satır ve MADDE 17 600 karakter.

    Başlıklara 90 karakter sınırı koyunca bu satır başlık sayılmıyor, bir
    önceki maddenin gövdesine yapışıyordu -- rapor bölümlerini tanımlayan
    madde, tam da onu soran sorguda bulunamıyordu.
    """
    kesitler = kesitlere_ayir(_belge(_MEVZUAT))
    basliklar = [k.baslik for k in kesitler]

    assert any(b.startswith("MADDE 17") for b in basliklar)


def test_madde_metni_kesitin_GOVDESINDE_duruyor() -> None:
    """Başlık kısaltılıyor ama hüküm kaybolmuyor."""
    kesitler = kesitlere_ayir(_belge(_MEVZUAT))
    madde17 = next(k for k in kesitler if k.baslik.startswith("MADDE 17"))

    assert "TARTIŞMA VE DEĞERLENDİRME" in madde17.metin


# ---------------------------------------------------------------------------
# Seçici okuma
# ---------------------------------------------------------------------------


def test_sorgu_ILGILI_maddeyi_getiriyor() -> None:
    kesitler = ilgili_kesitler(
        _belge(_MEVZUAT), "rapor bölümleri giriş konu sonuç", token_butcesi=2000
    )

    assert any(k.baslik.startswith("MADDE 17") for k in kesitler)


def test_sorgu_ILGISIZ_maddeyi_getirmiyor() -> None:
    """Kullanıcının istediği: disiplin yerine rapor yazımı, ya da tersi."""
    kesitler = ilgili_kesitler(
        _belge(_MEVZUAT), "rapor bölümleri giriş konu sonuç", token_butcesi=400
    )
    basliklar = " ".join(k.baslik for k in kesitler)

    assert "MADDE 31" not in basliklar


def test_ters_sorgu_DISIPLIN_maddesini_getiriyor() -> None:
    """Aynı belgeden bu kez disiplin tarafı isteniyor."""
    kesitler = ilgili_kesitler(
        _belge(_MEVZUAT), "disiplin cezası zamanaşımı uyarma kınama", token_butcesi=600
    )

    assert any(k.baslik.startswith("MADDE 30") for k in kesitler)


def test_secilen_kesitler_TOKEN_BUTCESINI_asmiyor() -> None:
    kesitler = ilgili_kesitler(_belge(_MEVZUAT * 30), "rapor kapak", token_butcesi=900)

    assert sum(token_tahmini(k.metin) for k in kesitler) <= 900


def test_secilen_kesitler_BELGEDEKI_SIRAYLA_veriliyor() -> None:
    """Mevzuatta sıra anlam taşıyor: madde 17'yi 5'ten önce okumak atıfları ters çevirir."""
    kesitler = ilgili_kesitler(
        _belge(_MEVZUAT), "rapor kapak bölüm punto", token_butcesi=4000
    )
    numaralar = [
        int(k.baslik.split()[1].rstrip("-")) for k in kesitler if k.baslik.startswith("MADDE")
    ]

    assert numaralar == sorted(numaralar)


def test_sorgu_hicbir_seye_uymuyorsa_BOS_donuyor() -> None:
    """Uymayan bir sorguya rastgele kesit vermek, modele gürültü vermek olur."""
    assert ilgili_kesitler(_belge(_MEVZUAT), "zzz qqq", token_butcesi=2000) == []


# ---------------------------------------------------------------------------
# Biçim devralma -- yarım raporu AYNI fontla tamamlamak
# ---------------------------------------------------------------------------


def _docx_bicimli(yol, *, font: str, sz: int, jc_govde: str) -> None:
    """Başlığı ORTALI, gövdesi ``jc_govde`` olan bir belge."""
    paragraflar = [f'<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
                   f'<w:r><w:rPr><w:rFonts w:ascii="{font}"/><w:sz w:val="{sz}"/></w:rPr>'
                   f"<w:t>İNCELEME RAPORU</w:t></w:r></w:p>"]

    for _ in range(12):
        paragraflar.append(
            f'<w:p><w:pPr><w:spacing w:after="195" w:line="360"/>'
            f'<w:ind w:firstLine="567"/><w:jc w:val="{jc_govde}"/></w:pPr>'
            f'<w:r><w:rPr><w:rFonts w:ascii="{font}"/><w:sz w:val="{sz}"/></w:rPr>'
            f"<w:t>Gövde paragrafı.</w:t></w:r></w:p>"
        )

    sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="2865" w:right="1274" w:bottom="1417" w:left="1417"/></w:sectPr>')
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{''.join(paragraflar)}{sect}</w:body></w:document>")

    with zipfile.ZipFile(yol, "w") as paket:
        paket.writestr("word/document.xml", xml)


def test_yarim_raporun_FONTU_ve_PUNTOSU_devraliniyor(tmp_path) -> None:
    yol = tmp_path / "yarim.docx"
    _docx_bicimli(yol, font="Cambria", sz=22, jc_govde="both")

    devralinan = devral(yol)

    assert devralinan.bicim.yazi_tipi == "Cambria"
    assert devralinan.bicim.yazi_boyut == 22  # 11 punto
    assert devralinan.okunamayan == []


def test_hizalama_BASKIN_degerden_okunuyor(tmp_path) -> None:
    """İlk ``w:jc`` ortalanmış BAŞLIK; gövdenin hizalaması o değil.

    Gerçek örnek raporda ölçüldü: ilk değer ``center``, gövde ``both``.
    İlk değeri almak, tamamlanan bölümleri ortalanmış yazardı.
    """
    yol = tmp_path / "yarim.docx"
    _docx_bicimli(yol, font="Times New Roman", sz=24, jc_govde="both")

    assert devral(yol).bicim.hizalama == "both"


def test_sayfa_olcusu_ve_kenarlar_devraliniyor(tmp_path) -> None:
    yol = tmp_path / "yarim.docx"
    _docx_bicimli(yol, font="Times New Roman", sz=24, jc_govde="both")

    bicim = devral(yol).bicim

    assert bicim.kenar_ust == 2865
    assert bicim.kenar_sol == 1417
    assert bicim.satir_araligi == 360


def test_yonergeden_FARKLAR_bildiriliyor_ama_duzeltilmiyor(tmp_path) -> None:
    """Elindeki belgeyi yarısından değiştirmek müfettişin kararı."""
    yol = tmp_path / "yarim.docx"
    _docx_bicimli(yol, font="Cambria", sz=22, jc_govde="both")

    devralinan = devral(yol)
    farklar = {f.alan for f in yonergeye_uygunluk(devralinan.bicim)}

    assert "yazı tipi" in farklar
    assert "punto" in farklar
    # Devralinan bicim DEGISTIRILMEDI: hala belgenin kendi fontu.
    assert devralinan.bicim.yazi_tipi == "Cambria"


def test_yonergeye_UYAN_belgede_fark_cikmiyor(tmp_path) -> None:
    yol = tmp_path / "uygun.docx"
    olcut = Bicim()
    paragraf = (
        f'<w:p><w:pPr><w:spacing w:after="{olcut.paragraf_bosluk}" '
        f'w:line="{olcut.satir_araligi}"/>'
        f'<w:ind w:firstLine="{olcut.paragraf_girinti}"/>'
        f'<w:jc w:val="{olcut.hizalama}"/></w:pPr>'
        f'<w:r><w:rPr><w:rFonts w:ascii="{olcut.yazi_tipi}"/>'
        f'<w:sz w:val="{olcut.yazi_boyut}"/></w:rPr><w:t>Metin.</w:t></w:r></w:p>'
    )
    sect = (
        f'<w:sectPr><w:pgSz w:w="{olcut.sayfa_genislik}" w:h="{olcut.sayfa_yukseklik}"/>'
        f'<w:pgMar w:top="{olcut.kenar_ust}" w:right="{olcut.kenar_sag}" '
        f'w:bottom="{olcut.kenar_alt}" w:left="{olcut.kenar_sol}"/></w:sectPr>'
    )
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{paragraf}{sect}</w:body></w:document>")

    with zipfile.ZipFile(yol, "w") as paket:
        paket.writestr("word/document.xml", xml)

    assert yonergeye_uygunluk(devral(yol).bicim) == []
