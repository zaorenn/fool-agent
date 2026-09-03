"""
Eşlemesi bozuk PDF'ten metni GERİ KAZAN.

Ölçülen sorun
-------------
Kullanıcının 72 sayfalık "DSİ Disiplin Soruşturma Rehberi" PDF'inde küçük "i"
harfi hiçbir metin çıkarıcıyla gelmiyor: ``pdftotext`` yerine boşluk koyuyor
("d s pl n"), ``pdfminer`` düşürüyor ("dspln"). PDF'in 404 ToUnicode
eşlemesinde 'i' hedefi yalnızca 69 kez geçiyor, yani eşleme fontta gerçekten
yok.

Ama harf KAYIP DEĞİL
--------------------
Glif sayfada duruyor; yalnızca Unicode karşılığı bildirilmemiş. ``pdfminer``
karakter karakter okunduğunda bu glifler METNİ BOŞ birer karakter olarak
görünüyor. Ölçüldü (72 sayfa): 218.215 karakterin 17.190'ı boş -- %7,9, ki
Türkçede 'i' harfinin beklenen sıklığı tam olarak bu.

Bağlamları tek tek bakıldı ve istisnasız 'i' çıktı::

    Ülkem[?]zde        -> Ülkemizde
    Mehmet Ak[?]f      -> Mehmet Akif
    Koord[?]natör      -> Koordinatör
    d[?]kkat ed[?]lmes[?] -> dikkat edilmesi

Glif genişlikleri farklı (1,45 ile 3,42 arası) ama bu harf farkı değil PUNTO
farkı: başlıklar büyük, dipnotlar küçük.

Neden yine de tahmin edilmiyor
------------------------------
"Boş glif = i" diye sabitlemek bu belgede doğru, başka belgede yanlış olurdu.
Onun yerine aday harfler denenip sonuç TÜRKÇE OLARAK puanlanıyor, kazanan
seçiliyor ve ne yapıldığı rapor ediliyor. Kalite denetimi de ayrıca koşuyor:
kurtarma işe yaramadıysa metin yine reddediliyor.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

#: Denenecek harfler. Türkçe PDF'lerde eşlemesi düşen glif hemen her zaman
#: bunlardan biri: dar gövdeli, noktalı/noktasız i ve l.
ADAYLAR = ("i", "ı", "l", "İ")

#: Puanlama için sık Türkçe sözcükler. Aday harf doğruysa bunlar ortaya çıkıyor,
#: yanlışsa çıkmıyor -- "dsiplin" hiçbir listede yok.
_OLCUT_SOZCUKLER = (
    "için", "ile", "bir", "gibi", "olarak", "ilgili", "ilişkin",
    "disiplin", "inceleme", "soruşturma", "müfettiş", "idari", "işlem",
    "kişi", "bildirim", "tarih", "madde", "hükmü", "kanun", "yönetmelik",
)


def kullanilabilir() -> bool:
    """``pdfminer.six`` kurulu mu?"""
    try:
        import pdfminer  # noqa: F401
    except ImportError:
        return False

    return True


@dataclass
class Kurtarma:
    """Bir PDF'ten kurtarılan metin ve nasıl kurtarıldığı."""

    sayfalar: list[str] = field(default_factory=list)
    #: Eşlemesi olmayan kaç glif vardı?
    bos_glif: int = 0
    toplam_glif: int = 0
    #: Onların yerine hangi harf kondu? Boşsa hiçbir şey değiştirilmedi.
    secilen_harf: str = ""
    #: Aday harflerin Türkçe puanları -- kararın gerekçesi.
    puanlar: dict[str, int] = field(default_factory=dict)

    @property
    def bos_orani(self) -> float:
        return self.bos_glif / self.toplam_glif if self.toplam_glif else 0.0

    @property
    def metin(self) -> str:
        return "\n".join(self.sayfalar)

    def aciklama(self) -> str:
        if not self.secilen_harf:
            return "Eşlemesi eksik glif bulunmadı; metin olduğu gibi okundu."

        return (
            f"PDF'in fontunda {self.bos_glif} glifin "
            f"(%{self.bos_orani * 100:.1f}) Unicode eşlemesi yok. "
            f"Türkçe puanlamasına göre yerlerine '{self.secilen_harf}' kondu "
            f"(puanlar: {self.puanlar})."
        )


def _turkce_puan(metin: str) -> int:
    """Metin ne kadar Türkçe görünüyor? Sözcük eşleşme sayısı."""
    dusuk = metin.lower()

    return sum(dusuk.count(f" {sozcuk} ") for sozcuk in _OLCUT_SOZCUKLER)


def _ham_sayfalar(yol: Path) -> tuple[list[list[list[str | None]]], int, int]:
    """Sayfa -> satır -> karakter. Eşlemesi olmayan karakter ``None``.

    Metin burada BİRLEŞTİRİLMİYOR: aday harf denemeleri aynı okumayı tekrar
    tekrar kullanabilsin diye yapı korunuyor. 72 sayfalık belgede pdfminer
    okuması saniyeler sürüyor; dört aday için dört kez okumak gereksiz.
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar, LTTextContainer, LTTextLine

    sayfalar: list[list[list[str | None]]] = []
    bos = 0
    toplam = 0

    for sayfa in extract_pages(str(yol)):
        satirlar: list[list[str | None]] = []

        for oge in sayfa:
            if not isinstance(oge, LTTextContainer):
                continue

            for satir in oge:
                if not isinstance(satir, LTTextLine):
                    continue

                karakterler: list[str | None] = []

                for karakter in satir:
                    if not isinstance(karakter, LTChar):
                        continue

                    metin = karakter.get_text()
                    toplam += 1

                    if metin == "":
                        bos += 1
                        karakterler.append(None)
                    else:
                        karakterler.append(metin)

                if karakterler:
                    satirlar.append(karakterler)

        sayfalar.append(satirlar)

    return sayfalar, bos, toplam


def _birlestir(sayfalar: list[list[list[str | None]]], harf: str) -> list[str]:
    return [
        "\n".join(
            "".join(harf if k is None else k for k in satir).rstrip()
            for satir in sayfa
        )
        for sayfa in sayfalar
    ]


def kurtar(yol: str | Path) -> Kurtarma:
    """PDF'i karakter karakter oku, eşlemesi düşen glifleri geri koy.

    ``pdfminer.six`` yoksa ``ImportError`` yükseliyor; çağıran
    ``kullanilabilir()`` ile önceden bakabiliyor.
    """
    yol = Path(yol)
    sayfalar, bos, toplam = _ham_sayfalar(yol)

    if not bos:
        return Kurtarma(_birlestir(sayfalar, ""), 0, toplam)

    puanlar = {aday: _turkce_puan("\n".join(_birlestir(sayfalar, aday))) for aday in ADAYLAR}
    kazanan = max(puanlar, key=lambda aday: puanlar[aday])

    # Hicbir aday Turkce'ye benzemiyorsa DEGISTIRME. Bilinmeyen bir glifi
    # rastgele bir harfe cevirmek, bozuk metni "duzeltilmis" gibi gostermek
    # olurdu -- bu belgeler imzalaniyor.
    if puanlar[kazanan] == 0:
        return Kurtarma(_birlestir(sayfalar, ""), bos, toplam, "", puanlar)

    return Kurtarma(_birlestir(sayfalar, kazanan), bos, toplam, kazanan, puanlar)
