"""
DOCX üretimi -- doğrudan OOXML, kütüphane YOK.

Neden bağımlılık yok
--------------------
Kullanıcının şartı "tamamen yerel modellerde kusursuz çalışmalı". Bir resmî
rapor üretiminin, üretim anında pip'ten paket çekmeye çalışıp ağ yokken
patlaması kabul edilebilir değil. ``.docx`` zaten bir zip içinde XML; ihtiyaç
duyulan parça (bölümler, kenar boşlukları, alan kodlu sayfa numarası) elle
yazılabilecek kadar dar. Böylece üretim yolu ne ağa ne kuruluma bağlı.

Bölüm yapısı neden bu kadar önemli
----------------------------------
MADDE 8(9) sayfa numarasını "1/30" biçiminde istiyor; MADDE 8(11) ise kapak,
özet, ek dizini ve eklerin BU NUMARALANDIRMAYA DAHİL OLMADIĞINI söylüyor.
Tek bölümlü bir belgede ``NUMPAGES`` toplam sayfayı verir ve kapak da sayılır
-- yani 30 sayfalık bir metin "2/32" diye numaralanır ve yönergeye aykırı olur.
O yüzden belge ayrı bölümlere ayrılıyor ve metin bölümü ``SECTIONPAGES``
kullanıyor: kendi bölümünün sayfa sayısı.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from .model import Alinti, AltBaslik, Ek, Paragraf, Rapor, Tablo
from .turkce import bolum_basligi, buyuk
from .yonerge import Bicim

_NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
<Override PartName="/word/header2.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header2.xml"/>
</Relationships>"""


def _styles(bicim: Bicim) -> str:
    """Belge geneli varsayılanlar. MADDE 8(3): Times New Roman 12 punto."""
    tip = escape(bicim.yazi_tipi)

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{_NS_W}">'
        "<w:docDefaults><w:rPrDefault><w:rPr>"
        f'<w:rFonts w:ascii="{tip}" w:hAnsi="{tip}" w:cs="{tip}"/>'
        f'<w:sz w:val="{bicim.yazi_boyut}"/><w:szCs w:val="{bicim.yazi_boyut}"/>'
        '<w:lang w:val="tr-TR"/>'
        "</w:rPr></w:rPrDefault>"
        "<w:pPrDefault><w:pPr>"
        f'<w:spacing w:after="{bicim.paragraf_bosluk}"'
        f' w:line="{bicim.satir_araligi}" w:lineRule="auto"/>'
        f'<w:jc w:val="{bicim.hizalama}"/>'
        "</w:pPr></w:pPrDefault></w:docDefaults>"
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/></w:style>'
        "</w:styles>"
    )


def _run(metin: str, *, kalin: bool = False, italik: bool = False) -> str:
    ozellik = ""
    if kalin:
        ozellik += "<w:b/><w:bCs/>"
    if italik:
        ozellik += "<w:i/><w:iCs/>"

    rpr = f"<w:rPr>{ozellik}</w:rPr>" if ozellik else ""

    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(metin)}</w:t></w:r>'


def _para(
    icerik: str,
    *,
    girinti: int = 0,
    hizalama: str = "both",
    bosluk: int = 120,
    satir: int = 240,
) -> str:
    ind = f'<w:ind w:firstLine="{girinti}"/>' if girinti else ""

    # Siralama SEMA GEREGI: CT_PPrBase icinde spacing -> ind -> jc. Word
    # yanlis siraya cogu zaman katlaniyor ama sema disi bir belge, dogrulayan
    # her araca (LibreOffice, arsiv sistemleri) bozuk gorunuyor. Resmi evrakta
    # "cogu zaman aciliyor" yeterli degil.
    return (
        "<w:p><w:pPr>"
        f'<w:spacing w:after="{bosluk}" w:line="{satir}" w:lineRule="auto"/>'
        f'{ind}<w:jc w:val="{hizalama}"/>'
        f"</w:pPr>{icerik}</w:p>"
    )


def _alan(kod: str) -> str:
    """OOXML alan kodu (PAGE, SECTIONPAGES). Word açarken hesaplıyor."""
    return (
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        f'<w:r><w:instrText xml:space="preserve"> {kod} </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        "<w:r><w:t>1</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    )


def _header(bicim: Bicim) -> str:
    """MADDE 8(9): sağ üstte "1/30" -- bölümün KENDİ sayfa sayısıyla."""
    icerik = _alan("PAGE") + "<w:r><w:t>/</w:t></w:r>" + _alan("SECTIONPAGES")

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:hdr xmlns:w="{_NS_W}">'
        + _para(icerik, hizalama=bicim.sayfa_no_hizalama, bosluk=0)
        + "</w:hdr>"
    )


def _bos_header() -> str:
    """Sayfa numarası TAŞIMAYAN üstbilgi -- devralmayı kesmek için."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:hdr xmlns:w="{_NS_W}"><w:p/></w:hdr>'
    )


def _sect_pr(bicim: Bicim, *, baslik_ref: bool, numara_baslat: int | None) -> str:
    """Bölüm özellikleri: sayfa ölçüsü, kenar boşlukları, sayfa numarası."""
    parcalar = []

    # Ustbilgi HER bolumde ACIKCA bildiriliyor.
    #
    # OOXML'de bir bolum kendi ustbilgisini tanimlamazsa BIR ONCEKINDEN
    # devraliyor ("link to previous"). Once numarasiz bolumlerde referansi
    # hic yazmiyordum ve olculdu: ek dizini sayfasinda "2/1" numarasi cikti
    # -- MADDE 9(3) "Ek dizinine sayfa numarasi verilmez" diyor. Devralmayi
    # kesmenin yolu referansi atlamak degil, BOS bir ustbilgiye baglamak.
    parcalar.append(
        f'<w:headerReference w:type="default" r:id="{"rId2" if baslik_ref else "rId3"}"/>'
    )

    parcalar.append(
        f'<w:pgSz w:w="{bicim.sayfa_genislik}" w:h="{bicim.sayfa_yukseklik}"/>'
    )
    parcalar.append(
        f'<w:pgMar w:top="{bicim.kenar_ust}" w:right="{bicim.kenar_sag}"'
        f' w:bottom="{bicim.kenar_alt}" w:left="{bicim.kenar_sol}"'
        f' w:header="{bicim.kenar_ust}" w:footer="708" w:gutter="0"/>'
    )

    if numara_baslat is not None:
        parcalar.append(f'<w:pgNumType w:start="{numara_baslat}"/>')

    return f"<w:sectPr>{''.join(parcalar)}</w:sectPr>"


def _bolum_sonu(sect_pr: str) -> str:
    """Bölümü kapatan boş paragraf -- ``sectPr`` son paragrafın içinde durur."""
    return f"<w:p><w:pPr>{sect_pr}</w:pPr></w:p>"


def _tablo_govde(tablo: Tablo) -> str:
    """Kenarlıklı tablo gövdesi -- başlık satırı hariç."""
    kenar = (
        "<w:tblBorders>"
        + "".join(
            f'<w:{yan} w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
            for yan in ("top", "left", "bottom", "right", "insideH", "insideV")
        )
        + "</w:tblBorders>"
    )

    def hucre(metin: str, kalin: bool) -> str:
        return (
            "<w:tc><w:tcPr/>"
            + _para(_run(metin, kalin=kalin), hizalama="left", bosluk=0)
            + "</w:tc>"
        )

    satirlar = ["<w:tr>" + "".join(hucre(b, True) for b in tablo.basliklar) + "</w:tr>"]
    for satir in tablo.satirlar:
        satirlar.append("<w:tr>" + "".join(hucre(h, False) for h in satir) + "</w:tr>")

    # ``w:tblGrid`` SEMADA ZORUNLU: tblPr -> tblGrid -> satirlar. Grid yoksa
    # sutun genislikleri tanimsiz kaliyor ve tablo bazi goruntuleyicilerde hic
    # cizilmiyor.
    grid = (
        "<w:tblGrid>"
        + "".join("<w:gridCol/>" for _ in tablo.basliklar)
        + "</w:tblGrid>"
    )

    return (
        f'<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/>{kenar}</w:tblPr>{grid}'
        + "".join(satirlar)
        + "</w:tbl>"
        # Tablodan sonra bos paragraf: iki tablo bitisik olursa Word onlari
        # TEK tablo sayiyor ve satirlar birbirine karisiyor.
        + _para("")
    )


def _tablo(tablo: Tablo) -> str:
    """Başlıklı tablo. Örnek rapordaki gibi başlık tablonun ÜSTÜNDE."""
    ust = _para(_run(tablo.baslik, kalin=True), hizalama="left") if tablo.baslik else ""

    return ust + _tablo_govde(tablo)


def _kapak(rapor: Rapor) -> str:
    """MADDE 6: kapak alanları. MADDE 6(5): kapağa sayfa numarası verilmez."""
    kapak = rapor.kapak
    orta = "center"
    parcalar = [
        _para(_run(buyuk(kapak.bakanlik), kalin=True), hizalama=orta),
        _para(_run(buyuk(kapak.baskanlik), kalin=True), hizalama=orta),
    ]

    if kapak.gizli:
        # MADDE 6(4): kapagin ust ve alt ortasina "GIZLI".
        parcalar.append(_para(_run("GİZLİ", kalin=True), hizalama=orta))

    parcalar += [
        _para(""),
        _para(_run(buyuk(kapak.baslik), kalin=True), hizalama=orta),
        _para(""),
        _para(_run(f"Konu: {kapak.konu}"), hizalama="left"),
        _para(
            _run(
                f"Görev Emri: {kapak.gorev_emri_tarih} tarih ve "
                f"{kapak.gorev_emri_sayi} sayılı"
            ),
            hizalama="left",
        ),
        _para(
            _run(f"Rapor Tarihi ve Sayısı: {kapak.rapor_tarih} - {kapak.rapor_sayi}"),
            hizalama="left",
        ),
        _para(_run(f"Ek Adedi: {kapak.ek_adedi}"), hizalama="left"),
        _para(""),
        _para(_run(kapak.mufettis_ad, kalin=True), hizalama=orta),
        _para(_run(kapak.mufettis_unvan), hizalama=orta),
    ]

    if kapak.gizli:
        parcalar.append(_para(_run("GİZLİ", kalin=True), hizalama=orta))

    return "".join(parcalar)


def _ek_dizini(ekler: list[Ek]) -> str:
    """MADDE 9: her ekin numarası, sayfa sayısı ve içeriği."""
    parcalar = [_para(_run("EK DİZİNİ", kalin=True), hizalama="center")]

    if ekler:
        parcalar.append(
            _tablo_govde(
                Tablo(
                    baslik="",
                    basliklar=("Ek No", "Sayfa Sayısı", "İçeriği"),
                    satirlar=[
                        (str(ek.no), str(ek.sayfa_sayisi), ek.icerik) for ek in ekler
                    ],
                )
            )
        )

    return "".join(parcalar)


def belge_xml(rapor: Rapor, bicim: Bicim) -> str:
    """Raporun ``word/document.xml`` içeriği."""
    govde: list[str] = []

    # 1. bolum: kapak. Sayfa numarasi YOK (MADDE 6(5)).
    govde.append(_kapak(rapor))
    govde.append(_bolum_sonu(_sect_pr(bicim, baslik_ref=False, numara_baslat=None)))

    # 2. bolum: ozet. MADDE 7: kapak ile rapor metni ARASINDA.
    if rapor.ozet:
        govde.append(_para(_run("ÖZET", kalin=True), hizalama="center"))
        for satir in rapor.ozet:
            govde.append(_para(_run(satir), girinti=bicim.paragraf_girinti))
        govde.append(_bolum_sonu(_sect_pr(bicim, baslik_ref=False, numara_baslat=None)))

    # 3. bolum: rapor metni. Numaralandirma burada 1'den BASLIYOR.
    for bolum in rapor.bolumler:
        # MADDE 8(8): bolum basliklari tamamen buyuk harf ve koyu.
        govde.append(_para(_run(bolum_basligi(bolum.baslik), kalin=True), hizalama="left"))

        for oge in bolum.ogeler:
            if isinstance(oge, AltBaslik):
                # MADDE 8(8): alt basliklarda her kelimenin ilk harfi buyuk, koyu.
                govde.append(_para(_run(oge.metin, kalin=True), hizalama="left"))
            elif isinstance(oge, Paragraf):
                metin = f"{oge.metin} ({oge.ek})" if oge.ek else oge.metin
                govde.append(
                    _para(
                        _run(metin, kalin=oge.kalin),
                        girinti=bicim.paragraf_girinti,
                    )
                )
            elif isinstance(oge, Alinti):
                # MADDE 8(6): aynen alintilar tirnak icinde VE italik.
                govde.append(
                    _para(
                        _run(f"“{oge.metin}”", italik=True),
                        girinti=bicim.paragraf_girinti,
                    )
                )
                kaynak = " ".join(x for x in (oge.kaynak, oge.ek) if x)
                if kaynak:
                    govde.append(_para(_run(kaynak), hizalama="right"))
            elif isinstance(oge, Tablo):
                govde.append(_tablo(oge))

    # Imza blogu: ornek rapordaki "Arz olunur. Ankara, 01.06.2026" bicimi.
    govde.append(_para(""))
    govde.append(
        _para(
            _run(f"Arz olunur. {rapor.imza_yer}, {rapor.imza_tarih}"),
            hizalama="right",
        )
    )
    govde.append(_para(_run(rapor.kapak.mufettis_ad, kalin=True), hizalama="right"))
    govde.append(_para(_run(rapor.kapak.mufettis_unvan), hizalama="right"))

    govde.append(_bolum_sonu(_sect_pr(bicim, baslik_ref=True, numara_baslat=1)))

    # 4. bolum: ek dizini. MADDE 9(3): sayfa numarasi verilmez.
    govde.append(_ek_dizini(rapor.ekler))

    son = _sect_pr(bicim, baslik_ref=False, numara_baslat=None)

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_NS_W}" xmlns:r="{_NS_R}">'
        f"<w:body>{''.join(govde)}{son}</w:body></w:document>"
    )


def yaz(rapor: Rapor, hedef: str | Path, bicim: Bicim | None = None) -> Path:
    """Raporu ``.docx`` olarak yaz ve yolunu döndür."""
    bicim = bicim or Bicim()
    hedef = Path(hedef)
    hedef.parent.mkdir(parents=True, exist_ok=True)

    # ZIP_DEFLATED: 80 sayfalik bir rapor sikistirilmadan gereksiz buyuk olur.
    with zipfile.ZipFile(hedef, "w", zipfile.ZIP_DEFLATED) as paket:
        paket.writestr("[Content_Types].xml", _CONTENT_TYPES)
        paket.writestr("_rels/.rels", _RELS)
        paket.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        paket.writestr("word/styles.xml", _styles(bicim))
        paket.writestr("word/header1.xml", _header(bicim))
        paket.writestr("word/header2.xml", _bos_header())
        paket.writestr("word/document.xml", belge_xml(rapor, bicim))

    return hedef
