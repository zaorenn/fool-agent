"""
Raporu hedeflenen sayfa aralığına -- DOLDURARAK değil, DERİNLEŞTİREREK -- getir.

Ölçmek, tahmin etmek değil
--------------------------
"Kaç sayfa tuttu" sorusunun kestirilebilir bir cevabı yok: aynı karakter
sayısı, yazı tipine, punto'ya, satır aralığına, tabloların kırılmasına ve
paragraf boşluğuna göre farklı sayıda sayfa ediyor. Bu depoda bunun bir
karşılığı zaten var -- ``sayfa_toplami`` sayfa numarasındaki toplamı
HESAPLAMIYOR, belgeyi bastırıp SAYIYOR.

Aynı gerekçe hedef için de geçerli: 14 sayfa isteniyorsa, 14 sayfanın kaç
karakter olduğu bu belgenin kendi ölçüsünden çıkarılıyor. Belge bir kez
basılıyor, sayfa sayısı ve karakter sayısı birlikte biliniyor, ikisinin oranı
bu biçim için sayfa başına karakteri veriyor. Sabit bir katsayı kullanmak,
kullanıcı yönergesi 11 punto derse sessizce yanlış olurdu.

Neden eksik sayfa "daha çok yaz" demek DEĞİL
--------------------------------------------
Kullanıcının şartı "dolu dolu": 14 sayfayı satır aralığını açarak ya da aynı
cümleyi tekrarlayarak tutturmak başarısızlık. Örnek yönerge bunu ayrıca
yasaklıyor ("Rapor hacmi ... aynı hususlar tekrar edilerek artırılamaz").

Bu yüzden eksik sayfa bildirimi biçime hiç dokunmuyor ve modele yapılacak
işi KAYNAK CİNSİNDEN söylüyor: hangi bölüm ince, ne kadar eksik ve eksiğin
nereden geleceği (``rapor_delil_oku`` ile okunmamış belgelerden). Şişirmenin
kendisi ayrıca ``uygunluk._sisirmeyi_denetle`` ile engel sayılıyor -- yani
"daha uzun yaz" demenin en kolay cevabı kapalı.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .pdf_cikti import donusturucu_bul, pdf_uret
from .sayfa_toplami import metin_sayfalarini_say
from .uygunluk import bolum_metni


@dataclass
class SayfaOlcumu:
    """Basılmış bir belgenin gerçek sayfa sayısı."""

    olculdu: bool
    sayfa: int = 0
    gerekce: str = ""

    def __bool__(self) -> bool:
        return self.olculdu


def olc(docx: str | Path) -> SayfaOlcumu:
    """Belgeyi bastır ve RAPOR METNİNİN kaç sayfa olduğunu say.

    Kapak, özet ve ek dizini sayılmıyor: yönerge sayfa numarasını yalnızca
    metne veriyor (``docx_yazici`` bölüm yapısı), dolayısıyla "rapor kaç
    sayfa" sorusunun cevabı numaralı sayfaların sayısı. Kapağı da saymak
    12 sayfalık bir hedefi 3 sayfa erken "tamam" gösterirdi.
    """
    docx = Path(docx)

    if not docx.exists():
        return SayfaOlcumu(False, gerekce=f"belge bulunamadı: {docx}")

    if donusturucu_bul() is None:
        return SayfaOlcumu(
            False,
            gerekce=(
                "Sayfa sayısı ölçülemedi: bu makinede DOCX'i PDF'e çevirecek "
                "bir program yok (LibreOffice). Sayfa aralığı DENETLENMEDİ."
            ),
        )

    sonuc = pdf_uret(docx)

    if not sonuc.basarili or sonuc.yol is None:
        return SayfaOlcumu(False, gerekce=sonuc.gerekce)

    sayfa = metin_sayfalarini_say(sonuc.yol)

    if sayfa < 1:
        return SayfaOlcumu(
            False,
            gerekce=(
                "Belge basıldı ama numaralı sayfa sayılamadı; sayfa aralığı "
                "denetlenemedi."
            ),
        )

    return SayfaOlcumu(True, sayfa)


# ---------------------------------------------------------------------------
# Hedefe göre yönlendirme
# ---------------------------------------------------------------------------


@dataclass
class SayfaDenetimi:
    """Sayfa sayısının hedef aralığa göre durumu ve yapılacak iş."""

    olculdu: bool
    sayfa: int = 0
    en_az: int = 0
    en_cok: int = 0
    #: Hedefe ulaşmak için eklenmesi gereken karakter (eksikse).
    eksik_karakter: int = 0
    #: Aralığın üstündeyse çıkarılması gereken karakter.
    fazla_karakter: int = 0
    #: Bu biçimde bir sayfanın kaç karakter tuttuğu -- ÖLÇÜLEN değer.
    sayfa_basina_karakter: int = 0
    #: Hangi bölümlerin derinleştirileceği, en ince olandan başlayarak.
    ince_bolumler: list[str] = field(default_factory=list)
    yonerge: str = ""

    @property
    def uygun(self) -> bool:
        """Ölçülemeyen sayfa sayısı UYGUN SAYILMIYOR.

        Aksi hâlde dönüştürücüsü olmayan bir makinede her rapor sessizce
        "sayfa aralığına uygun" çıkardı -- hiç ölçülmemişken.
        """
        return self.olculdu and not self.eksik_karakter and not self.fazla_karakter

    def sozluk(self) -> dict:
        return {
            "olculdu": self.olculdu,
            "sayfa": self.sayfa,
            "hedef": f"{self.en_az}-{self.en_cok}",
            "uygun": self.uygun,
            "eksik_karakter": self.eksik_karakter,
            "fazla_karakter": self.fazla_karakter,
            "sayfa_basina_karakter": self.sayfa_basina_karakter,
            "ince_bolumler": list(self.ince_bolumler),
            "yonerge": self.yonerge,
        }


def _metin_karakteri(taslak_sozlugu: dict) -> int:
    return sum(
        len(bolum_metni(b))
        for b in taslak_sozlugu.get("bolumler", [])
        if isinstance(b, dict)
    )


def _ince_bolumler(taslak_sozlugu: dict, en_fazla: int = 3) -> list[str]:
    """En kısa bölümler -- derinleştirmeye onlardan başlanıyor.

    Eksik karakteri bütün bölümlere eşit dağıtmak yanlış olurdu: bir raporda
    GİRİŞ zaten kısa olmalı, uzaması gereken İNCELEME VE ARAŞTIRMA. En ince
    bölümü göstermek, doldurulacak yeri değil DERİNLEŞTİRİLECEK yeri
    işaretliyor.
    """
    olculer = [
        (str(b.get("baslik", "")), len(bolum_metni(b)))
        for b in taslak_sozlugu.get("bolumler", [])
        if isinstance(b, dict)
    ]

    return [ad for ad, _ in sorted(olculer, key=lambda x: x[1])[:en_fazla]]


def degerlendir(
    sayfa: int,
    en_az: int,
    en_cok: int,
    taslak_sozlugu: dict | None = None,
    olculdu: bool = True,
    gerekce: str = "",
) -> SayfaDenetimi:
    """Ölçülmüş sayfa sayısını hedefle karşılaştır ve yapılacak işi söyle.

    ``olc``ten ayrı, çünkü sayfa sayısı çoğu zaman ZATEN ölçülmüş oluyor:
    ``arac.rapor_yaz`` belgeyi üretirken ``sayfa_toplami.sabitle`` onu bir kez
    bastırıp sayıyor. İkinci bir dönüştürme ölçülü olarak saniyeler sürüyor ve
    aynı sayıyı verirdi.
    """
    taslak_sozlugu = taslak_sozlugu or {}
    denetim = SayfaDenetimi(olculdu=olculdu, sayfa=sayfa, en_az=en_az, en_cok=en_cok)

    if not olculdu:
        denetim.yonerge = gerekce or "Sayfa sayısı ölçülemedi."
        return denetim

    karakter = _metin_karakteri(taslak_sozlugu)

    if sayfa > 0 and karakter > 0:
        denetim.sayfa_basina_karakter = int(round(karakter / sayfa))

    if en_az and sayfa < en_az:
        eksik_sayfa = en_az - sayfa
        denetim.eksik_karakter = eksik_sayfa * denetim.sayfa_basina_karakter
        denetim.ince_bolumler = _ince_bolumler(taslak_sozlugu)
        denetim.yonerge = (
            f"Rapor metni {sayfa} sayfa; yönerge en az {en_az} sayfa istiyor. "
            f"Bu biçimde bir sayfa ölçülen {denetim.sayfa_basina_karakter} "
            f"karakter tutuyor, yani yaklaşık {denetim.eksik_karakter} karakter "
            "daha gerekiyor. Bunu SATIR ARALIĞI ya da TEKRARLA değil, "
            "kaynaklardan YENİ TESPİT yazarak kapat: rapor_delil_listesi ile "
            "henüz kullanılmamış belgeleri gör, rapor_delil_oku ile ayrıntıyı "
            "al ve her yeni tespiti (Ek: n/m) atfıyla yaz. Önce şu bölümler "
            "derinleştirilmeli: " + ", ".join(denetim.ince_bolumler)
        )
    elif en_cok and sayfa > en_cok:
        fazla_sayfa = sayfa - en_cok
        denetim.fazla_karakter = fazla_sayfa * denetim.sayfa_basina_karakter
        denetim.yonerge = (
            f"Rapor metni {sayfa} sayfa; yönerge en fazla {en_cok} sayfa "
            f"istiyor. Yaklaşık {denetim.fazla_karakter} karakter fazla. "
            "Tespitleri SİLME -- tekrar eden anlatımı ve kaynağa dayanmayan "
            "yorumları kısalt; maddi tespitler ve ek atıfları kalsın."
        )
    else:
        denetim.yonerge = (
            f"Rapor metni {sayfa} sayfa; hedef aralık {en_az}-{en_cok}. Uygun."
        )

    return denetim


def denetle(
    docx: str | Path,
    en_az: int,
    en_cok: int,
    taslak_sozlugu: dict | None = None,
) -> SayfaDenetimi:
    """Belgeyi bastır, say ve hedefe göre değerlendir."""
    olcum = olc(docx)

    return degerlendir(
        olcum.sayfa,
        en_az,
        en_cok,
        taslak_sozlugu,
        olculdu=olcum.olculdu,
        gerekce=olcum.gerekce,
    )
