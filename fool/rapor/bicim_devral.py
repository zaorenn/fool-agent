"""
Yarım raporun KENDİ biçimini devral.

Neden varsayılan biçim yetmiyor
-------------------------------
Kullanıcının şartı: "rapor yarımsa aynı font, aynı tip yazılar ve aynı tip
yazım tipiyle tamamlamalı."

``yonerge.Bicim`` yönergenin yazdığı biçimi taşıyor ve sıfırdan yazılan rapor
için doğru olan bu. Ama yarım bir raporu tamamlarken doğru olan başka: o
belgenin KENDİ biçimi. Müfettiş 40 sayfayı 12 punto Times New Roman ile
yazmışsa, kalan 30 sayfa yönergeye uygun diye 12 punto Cambria ile
tamamlanamaz -- ortaya iki yarısı farklı görünen tek bir resmî evrak çıkar ve
belgenin sonradan eklendiği ilk bakışta belli olur.

Bu yüzden tamamlama yolunda biçim ÜRETİLMİYOR, mevcut belgeden OKUNUYOR.

Yönergeyle çelişirse ne olur
----------------------------
Belge yönergeye aykırı bir biçim kullanıyorsa devralınan biçim de aykırı olur.
Bu bilerek böyle: karar müfettişin. ``yonergeye_uygunluk`` farkları listeliyor,
böylece kullanıcı görüp seçebiliyor -- sessizce "düzeltmek", elindeki belgeyi
yarısından itibaren değiştirmek olurdu.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .yonerge import Bicim

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _oz(xml: str, etiket: str, nitelik: str) -> str | None:
    """``<w:etiket w:nitelik="deger"/>`` içinde EN SIK geçen değeri çek.

    İlk değeri almak yanlış cevap veriyordu: belgenin ilk ``w:jc``si
    ortalanmış BAŞLIK oluyor, gövdenin hizalaması değil. Gerçek örnek raporda
    ölçüldü -- ilk değer ``center``, gövdenin tamamı ise ``both``. Devralınan
    biçim buna göre kurulunca tamamlanan bölümler ortalanmış çıkardı.

    Baskın değer, belgenin gerçekten kullandığı biçim.
    """
    kalip = rf'<w:{etiket}\b[^>]*\sw:{nitelik}="([^"]+)"'
    degerler = re.findall(kalip, xml)

    if not degerler:
        return None

    return Counter(degerler).most_common(1)[0][0]


@dataclass
class DevralinanBicim:
    """Var olan bir ``.docx``ten okunan biçim."""

    bicim: Bicim
    kaynak: str
    bulunan: dict[str, str]
    #: Okunamayan alanlar -- bunlarda yönerge varsayılanı kullanıldı.
    okunamayan: list[str]


def devral(yol: str | Path) -> DevralinanBicim:
    """Bir ``.docx``in biçimini oku.

    Okunamayan her alan için yönerge varsayılanı kalıyor ve ``okunamayan``
    listesine giriyor: sessizce varsayılana düşmek, "aynı biçim" sözünün
    sessizce tutulmaması demek olurdu.
    """
    yol = Path(yol)
    varsayilan = Bicim()
    bulunan: dict[str, str] = {}
    okunamayan: list[str] = []

    with zipfile.ZipFile(yol) as paket:
        adlar = set(paket.namelist())
        belge = paket.read("word/document.xml").decode("utf-8", "replace")
        stiller = (
            paket.read("word/styles.xml").decode("utf-8", "replace")
            if "word/styles.xml" in adlar
            else ""
        )

    # --- Yazi tipi ve punto: once belge govdesi, sonra stil varsayilani ---
    #
    # Sira onemli: styles.xml belgenin VARSAYILANINI soyluyor, govdedeki
    # rFonts ise gercekten KULLANILANI. Yarim raporlarda ikisi sik sik
    # ayrisiyor (sablondan gelen varsayilan Calibri, metnin kendisi TNR).
    yazi_tipi = _oz(belge, "rFonts", "ascii") or _oz(stiller, "rFonts", "ascii")

    if yazi_tipi:
        bulunan["yazi_tipi"] = yazi_tipi
    else:
        okunamayan.append("yazı tipi")
        yazi_tipi = varsayilan.yazi_tipi

    boyut_ham = _oz(belge, "sz", "val") or _oz(stiller, "sz", "val")

    if boyut_ham and boyut_ham.isdigit():
        yazi_boyut = int(boyut_ham)
        bulunan["yazi_boyut"] = f"{yazi_boyut / 2:g} punto"
    else:
        okunamayan.append("punto")
        yazi_boyut = varsayilan.yazi_boyut

    # --- Sayfa olcusu ve kenar bosluklari ---
    degerler: dict[str, int] = {}

    for alan, etiket, nitelik in (
        ("sayfa_genislik", "pgSz", "w"),
        ("sayfa_yukseklik", "pgSz", "h"),
        ("kenar_ust", "pgMar", "top"),
        ("kenar_alt", "pgMar", "bottom"),
        ("kenar_sol", "pgMar", "left"),
        ("kenar_sag", "pgMar", "right"),
    ):
        ham = _oz(belge, etiket, nitelik)

        if ham and ham.lstrip("-").isdigit():
            degerler[alan] = int(ham)
            bulunan[alan] = ham
        else:
            okunamayan.append(f"{etiket}/{nitelik}")

    # --- Satir araligi, hizalama, girinti ---
    satir = _oz(belge, "spacing", "line")
    if satir and satir.isdigit():
        degerler["satir_araligi"] = int(satir)
        bulunan["satir_araligi"] = satir
    else:
        okunamayan.append("satır aralığı")

    bosluk = _oz(belge, "spacing", "after")
    if bosluk and bosluk.isdigit():
        degerler["paragraf_bosluk"] = int(bosluk)
        bulunan["paragraf_bosluk"] = bosluk

    hizalama = _oz(belge, "jc", "val")
    if hizalama:
        degerler["hizalama"] = hizalama  # type: ignore[assignment]
        bulunan["hizalama"] = hizalama
    else:
        okunamayan.append("hizalama")

    girinti = _oz(belge, "ind", "firstLine")
    if girinti and girinti.isdigit():
        degerler["paragraf_girinti"] = int(girinti)
        bulunan["paragraf_girinti"] = girinti

    bicim = varsayilan.ile(
        yazi_tipi=yazi_tipi,
        yazi_boyut=yazi_boyut,
        **degerler,  # type: ignore[arg-type]
    )

    return DevralinanBicim(bicim, yol.name, bulunan, okunamayan)


@dataclass
class Fark:
    """Devralınan biçimin yönergeden ayrıldığı bir nokta."""

    alan: str
    belgede: object
    yonergede: object

    def __str__(self) -> str:
        return f"{self.alan}: belgede {self.belgede}, yönergede {self.yonergede}"


#: Yönergenin sayıyla yazdığı, karşılaştırmaya değer alanlar.
_KARSILASTIRILAN = (
    ("yazı tipi", "yazi_tipi"),
    ("punto", "yazi_boyut"),
    ("sayfa genişliği", "sayfa_genislik"),
    ("sayfa yüksekliği", "sayfa_yukseklik"),
    ("üst kenar", "kenar_ust"),
    ("alt kenar", "kenar_alt"),
    ("sol kenar", "kenar_sol"),
    ("sağ kenar", "kenar_sag"),
    ("hizalama", "hizalama"),
    ("paragraf girintisi", "paragraf_girinti"),
)


def yonergeye_uygunluk(bicim: Bicim, olcut: Bicim | None = None) -> list[Fark]:
    """Devralınan biçim yönergeden nerede ayrılıyor?

    Düzeltme YAPILMIYOR, yalnızca bildiriliyor: elindeki belgeyi yarısından
    itibaren değiştirmek müfettişin kararı, aracın değil.
    """
    olcut = olcut or Bicim()

    return [
        Fark(ad, getattr(bicim, alan), getattr(olcut, alan))
        for ad, alan in _KARSILASTIRILAN
        if getattr(bicim, alan) != getattr(olcut, alan)
    ]
