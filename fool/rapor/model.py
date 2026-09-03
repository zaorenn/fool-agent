"""
Rapor içerik modeli -- ne yazıldığı; nasıl göründüğü ``docx_yazici``ın işi.

Ayrımın sebebi
--------------
Yerel bir model metni üretiyor, biçimi ÜRETMİYOR. Model bu nesneleri
dolduruyor; kenar boşluğu, punto, sayfa numarası, ek numaralandırması
koddan geliyor. Bir dil modelinin 80 sayfa boyunca "Times New Roman 12,
sol 2,5 cm, sağ üstte 7/34" tutturması beklenemez -- ama bir tablo
dolduramaması da beklenemez. İş bölümü bu.

Uydurma karşıtı tasarım
-----------------------
Resmî evrakta uydurulmuş bir tarih, sayı ya da kanun maddesi, boş
bırakılmış bir alandan çok daha kötü: müfettiş imzalıyor ve sorumluluk
onda. O yüzden:

* Her maddi tespit bir eke dayanabilsin diye ``ek`` alanı var.
* Bilinmeyen alan uydurulmuyor, ``EKSIK`` ile işaretleniyor ve
  ``eksikler()`` bunları toplayıp müfettişe listeliyor.

``EKSIK`` metin olarak da göze batıyor (köşeli parantez), yani gözden
kaçıp imzaya giderse belgede görünür kalıyor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Sequence

#: Doldurulmamış alan. Uydurmak yerine bunu bırakıyoruz.
EKSIK = "[EKSİK]"


def eksik_mi(deger: object) -> bool:
    """Alan gerçekten dolu mu?

    Tür ZORLANIYOR. Alanlar bir dil modelinden geliyor ve model ``ek_adedi``yi
    ``"5"`` yerine ``5`` gönderiyor -- ölçüldü, yerel model tam bunu yaptı ve
    ``.strip()`` çağrısı ``AttributeError`` ile patladı. Raporun tamamı
    hazırken üretimin son adımında çökmek, kullanıcı için işin başa dönmesi
    demek; sayı gönderilmesi de zaten makul bir davranış.
    """
    if deger is None:
        return True

    metin = str(deger).strip()

    return not metin or metin == EKSIK


# ---------------------------------------------------------------------------
# Metin öğeleri
# ---------------------------------------------------------------------------


@dataclass
class Paragraf:
    """Düz paragraf. MADDE 8(4): soldan 1 cm girintili."""

    metin: str
    kalin: bool = False
    #: "(Ek: 5/3)" gibi bir dayanak. Boşsa paragraf maddi tespit taşımıyordur.
    ek: str = ""


@dataclass
class AltBaslik:
    """Alt bölüm başlığı. MADDE 8(8): her kelimenin ilk harfi büyük, koyu."""

    metin: str


@dataclass
class Alinti:
    """Başka bir belgeden AYNEN alıntı.

    MADDE 8(6): tırnak içinde ve italik. MADDE 4(2)(d) mevzuat alıntıları
    için aynı şeyi söylüyor. Tırnağı yazıcı koyuyor -- metne elle tırnak
    konursa çift tırnak çıkardı.
    """

    metin: str
    kaynak: str = ""
    ek: str = ""


@dataclass
class Tablo:
    """Numaralı tablo. Örnek raporda "Tablo 1: ..." biçiminde."""

    baslik: str
    basliklar: Sequence[str]
    satirlar: Sequence[Sequence[str]]

    def __post_init__(self) -> None:
        genislik = len(self.basliklar)
        for sira, satir in enumerate(self.satirlar, start=1):
            if len(satir) != genislik:
                raise ValueError(
                    f"tablo '{self.baslik}' {sira}. satirinda {len(satir)} hucre var, "
                    f"baslik sayisi {genislik}"
                )


Ogeler = Paragraf | AltBaslik | Alinti | Tablo


@dataclass
class Bolum:
    """Yönergenin saydığı ana bölümlerden biri (örn. "III. İNCELEME VE ARAŞTIRMA")."""

    baslik: str
    ogeler: list[Ogeler] = field(default_factory=list)

    def paragraf(self, metin: str, **kw: object) -> "Bolum":
        self.ogeler.append(Paragraf(metin, **kw))  # type: ignore[arg-type]
        return self


# ---------------------------------------------------------------------------
# Kapak -- MADDE 6
# ---------------------------------------------------------------------------


@dataclass
class Kapak:
    """MADDE 6(1)'in saydığı alanlar. Hepsi zorunlu."""

    bakanlik: str = EKSIK
    baskanlik: str = EKSIK
    #: MADDE 6(1)(b): raporun adını belirten başlık (örn. "İNCELEME RAPORU").
    baslik: str = EKSIK
    konu: str = EKSIK
    gorev_emri_tarih: str = EKSIK
    gorev_emri_sayi: str = EKSIK
    rapor_tarih: str = EKSIK
    rapor_sayi: str = EKSIK
    ek_adedi: str = EKSIK
    mufettis_ad: str = EKSIK
    mufettis_unvan: str = "Müfettiş"
    #: MADDE 6(4): kapağa kırmızı "GİZLİ" ibaresi.
    gizli: bool = False

    def eksikler(self) -> list[str]:
        """Doldurulmamış zorunlu kapak alanları."""
        zorunlu = {
            "Bakanlık adı": self.bakanlik,
            "Başkanlık adı": self.baskanlik,
            "Rapor başlığı": self.baslik,
            "Rapor konusu": self.konu,
            "Görev emri tarihi": self.gorev_emri_tarih,
            "Görev emri sayısı": self.gorev_emri_sayi,
            "Rapor tarihi": self.rapor_tarih,
            "Rapor sayısı": self.rapor_sayi,
            "Ek adedi": self.ek_adedi,
            "Müfettiş adı": self.mufettis_ad,
        }
        return [ad for ad, deger in zorunlu.items() if eksik_mi(deger)]


# ---------------------------------------------------------------------------
# Ekler -- MADDE 9, MADDE 10
# ---------------------------------------------------------------------------


@dataclass
class Ek:
    """Rapora eklenen bir belge."""

    no: int
    icerik: str
    sayfa_sayisi: int = 1

    def __post_init__(self) -> None:
        if self.sayfa_sayisi < 1:
            raise ValueError(f"Ek {self.no}: sayfa sayisi en az 1 olmali")


@dataclass
class Rapor:
    """Tam rapor: kapak + özet + bölümler + ek dizini."""

    tur: str
    kapak: Kapak
    bolumler: list[Bolum] = field(default_factory=list)
    ozet: list[str] = field(default_factory=list)
    ekler: list[Ek] = field(default_factory=list)
    #: MADDE 17(9) kapanışının ardından gelen imza satırı.
    imza_yer: str = EKSIK
    imza_tarih: str = EKSIK

    def bolum(self, baslik: str) -> Bolum | None:
        for bolum in self.bolumler:
            if bolum.baslik == baslik:
                return bolum
        return None

    def metinler(self) -> Iterator[str]:
        """Rapordaki bütün düz metin -- denetimler bunun üstünden geçiyor."""
        for bolum in self.bolumler:
            for oge in bolum.ogeler:
                if isinstance(oge, (Paragraf, Alinti)):
                    yield oge.metin
                elif isinstance(oge, AltBaslik):
                    yield oge.metin
                elif isinstance(oge, Tablo):
                    yield oge.baslik
                    for satir in oge.satirlar:
                        yield from satir

    def eksikler(self) -> list[str]:
        """Uydurulmamış, boş bırakılmış her şey -- imzadan önce görülmeli."""
        bulunan = list(self.kapak.eksikler())

        if eksik_mi(self.imza_yer):
            bulunan.append("İmza yeri")
        if eksik_mi(self.imza_tarih):
            bulunan.append("İmza tarihi")

        for metin in self.metinler():
            if EKSIK in metin:
                bulunan.append(f"Metinde doldurulmamış alan: {metin[:60]}")

        return bulunan
