"""
70 sayfalık yönergeyi OKU, uyulacak kuralları çıkar -- bağlama sığdırmadan.

Kullanıcının iş akışındaki boşluk
---------------------------------
``cozumle.iskelet_cikar`` doldurulmuş bir ÖRNEK RAPORDAN öğreniyor: bölüm
başlıklarını sayıyor, ek atıflarını topluyor, tekrar eden yüklemleri kalıp
sayıyor. Bu, elinde örnek rapor olan bir müfettiş için doğru araç.

Kullanıcının elinde örnek rapor değil YÖNERGE var: raporun nasıl yazılacağını
DÜZ YAZIYLA anlatan ~70 sayfalık bir metin. Orada bölüm başlıkları bir raporun
içinde geçmiyor, "şu bölümlerden oluşur" diye SAYILIYOR; kenar boşluğu bir
belgenin XML'inde durmuyor, "sol kenardan 2,5 cm boşluk bırakılır" diye
YAZIYOR. İskelet çıkarıcı bu metne uygulandığında hiçbir şey bulmuyor --
çünkü aradığı şey orada yok.

Neden model değil kural
-----------------------
"Yönergeyi modele okut, kuralları söylesin" en kısa yol ve tam olarak
kullanıcının reddettiği yol: 70 sayfa zaten bağlama sığmıyor, sığsa bile
çıkan şey her koşuda biraz değişirdi. ``arac`` modülünün başındaki karar
burada da geçerli -- biçim ÜRETİLMİYOR, uygulanıyor. O yüzden çıkarım
kurallı: sayı, ölçü ve başlık listesi düzenli ifadeyle bulunuyor ve
bulunanın yanında YÖNERGENİN KENDİ CÜMLESİ duruyor.

Kural tabanlı çıkarım yanılabilir. Bu yüzden ``Sartname.ozet_metni`` var:
kullanıcı 70 sayfayı değil, çıkarılmış 20-30 satırı okuyup onaylıyor. Yanlış
çıkarım orada görülüyor -- 20 sayfalık bir belge üretildikten sonra değil.

Bulunamayan susmuyor
--------------------
Yönergede karşılığı bulunamayan her alan ``eksik_kurallar``a giriyor. Sessizce
``Bicim`` varsayılanına düşmek en kötü sonucu verirdi: kullanıcı "yönergeme
göre üretildi" sanırken, aslında hiç okunmamış bir kural uygulanmış olurdu.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .kaynak import Belge, oku
from .sartname import BEKLENEN_ALANLAR, Kural, Sartname
from .yonerge import cm, punto

# ---------------------------------------------------------------------------
# Yönergeyi maddelere ve fıkralara böl
# ---------------------------------------------------------------------------
#
# Her kuralın DAYANAĞI olması gerekiyor ("MADDE 8/(2)"), yoksa gözden geçirme
# 70 sayfayı yeniden aramak demek olurdu. Bu yüzden metin önce maddelere,
# sonra fıkralara bölünüyor ve çıkarım fıkra fıkra yapılıyor.

_MADDE = re.compile(r"^[ \t]*MADDE\s+(\d+)\s*[-–—]?", re.MULTILINE | re.IGNORECASE)

#: Fıkra numarası: ya satır başında "(3)" ya da madde çizgisinden hemen
#: sonra "MADDE 8- (2)". Serbest yerde aranmıyor -- "(210x297 mm)" ve
#: "(Ek: 5/3)" gibi parantezler fıkra sanılırdı.
_FIKRA = re.compile(r"(?:^[ \t]*|[-–—][ \t]*)\((\d{1,2})\)[ \t]+", re.MULTILINE)


@dataclass
class Birim:
    """Yönergenin tek bir fıkrası (ya da fıkrasız bir maddenin tamamı)."""

    dayanak: str
    metin: str

    def gecer(self, *sozcukler: str) -> bool:
        """Bu fıkrada verilen sözcüklerden biri geçiyor mu?"""
        dusuk = _kucuk(self.metin)
        return any(s in dusuk for s in sozcukler)


def _kucuk(metin: str) -> str:
    """Türkçe duyarlı küçültme -- 'I' noktasız 'ı' olmalı."""
    return metin.replace("İ", "i").replace("I", "ı").lower()


def birimlere_ayir(metin: str) -> list[Birim]:
    """Yönergeyi ``MADDE n/(m)`` birimlerine böl.

    Madde başlığı bulunamayan metin TEK birim olarak dönüyor: kullanıcı
    yönerge yerine düz bir kural listesi de verebilir ve o zaman dayanak
    boş kalıyor, çıkarım yine çalışıyor.
    """
    basliklar = list(_MADDE.finditer(metin))

    if not basliklar:
        return [Birim("", metin)]

    birimler: list[Birim] = []

    for sira, baslik in enumerate(basliklar):
        son = basliklar[sira + 1].start() if sira + 1 < len(basliklar) else len(metin)
        govde = metin[baslik.start() : son]
        madde = f"MADDE {baslik.group(1)}"

        fikralar = list(_FIKRA.finditer(govde))

        if not fikralar:
            birimler.append(Birim(madde, govde))
            continue

        # Fikra isaretinden ONCEKI metin (madde basligi) ilk fikraya degil
        # maddenin kendisine ait; bolum listesi bazen orada duruyor.
        if fikralar[0].start() > 0:
            onsoz = govde[: fikralar[0].start()].strip()
            if onsoz:
                birimler.append(Birim(madde, onsoz))

        for yer, fikra in enumerate(fikralar):
            bitis = (
                fikralar[yer + 1].start() if yer + 1 < len(fikralar) else len(govde)
            )
            birimler.append(
                Birim(f"{madde}/({fikra.group(1)})", govde[fikra.start() : bitis])
            )

    return birimler


# ---------------------------------------------------------------------------
# Bölüm listesi
# ---------------------------------------------------------------------------

#: "I. GİRİŞ", "IV. TARTIŞMA VE DEĞERLENDİRME" gibi bir başlık adayı.
#:
#: Başlık gövdesi SATIR İÇİNDE kalıyor (``[^\S\n]``): yönergede başlıklar
#: bazen alt alta, bazen "I. GİRİŞ, II. KONU, ... ve V. SONUÇ bölümlerinden
#: oluşur" diye tek cümlede sayılıyor. Boşluğa satır sonunu da katsaydım
#: alt alta yazılmış iki başlık tek başlık olarak okunurdu.
_BOLUM_ADAY = re.compile(
    r"([IVX]{1,6})[ \t]*[.\-)][ \t]*"
    r"([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9]*(?:[^\S\n]+[A-ZÇĞİÖŞÜ0-9]+)*)"
)

_ROMEN_DEGERI = {"I": 1, "V": 5, "X": 10}


def _romen(metin: str) -> int:
    """Roma rakamını sayıya çevir. Geçersizse 0."""
    toplam = 0
    onceki = 0

    for harf in reversed(metin.upper()):
        deger = _ROMEN_DEGERI.get(harf, 0)
        if deger == 0:
            return 0
        toplam += -deger if deger < onceki else deger
        onceki = max(onceki, deger)

    return toplam


@dataclass
class BolumListesi:
    """Yönergede sayılmış bir rapor iskeleti."""

    dayanak: str
    baslik: str
    bolumler: list[str]

    def __str__(self) -> str:
        return f"{self.baslik} [{self.dayanak}]: {len(self.bolumler)} bölüm"


#: Bir bölüm listesi sayılmak için en az kaç başlık gerekiyor.
#:
#: Üç, çünkü ikili bir dizi ("I. ... II. ...") yönergenin gövdesinde tesadüfen
#: oluşabiliyor -- örneğin bir mevzuat atfının fıkra numaraları. Gerçek bir
#: rapor iskeleti hiçbir zaman iki bölümlük değil.
ASGARI_BOLUM = 3


def bolum_listeleri(birimler: list[Birim]) -> list[BolumListesi]:
    """Yönergede sayılan bütün rapor iskeletlerini bul.

    BİRDEN ÇOK dönüyor ve bu bilerek: gerçek bir yönerge birkaç rapor türünü
    birden tanımlıyor (inceleme, ön inceleme, disiplin). Hangisinin yazılacağı
    yönergenin değil kullanıcının kararı; araç hepsini gösteriyor, seçimi
    kullanıcı yapıyor. Tek liste dönseydi araç bu kararı sessizce verirdi.
    """
    bulunan: list[BolumListesi] = []

    for birim in birimler:
        adaylar = list(_BOLUM_ADAY.finditer(birim.metin))

        if not adaylar:
            continue

        dizi: list[tuple[str, int]] = []

        def kapat(baslangic: int) -> None:
            if len(dizi) < ASGARI_BOLUM:
                return

            bulunan.append(
                BolumListesi(
                    dayanak=birim.dayanak,
                    baslik=_liste_basligi(birim.metin, baslangic),
                    bolumler=[b for b, _ in dizi],
                )
            )

        ilk_yer = 0

        for aday in adaylar:
            sira = _romen(aday.group(1))
            govde = " ".join(aday.group(2).split())

            # Baslik en az uc harf: "I. A" bir bolum degil, kirik bir
            # eslesme. Yonergede tek harfli bir rapor bolumu yok.
            if sira == 0 or len(govde) < 3:
                continue

            if sira == 1:
                kapat(ilk_yer)
                dizi = [(f"{aday.group(1)}. {govde}", sira)]
                ilk_yer = aday.start()
            elif dizi and sira == dizi[-1][1] + 1:
                dizi.append((f"{aday.group(1)}. {govde}", sira))
            else:
                kapat(ilk_yer)
                dizi = []

        kapat(ilk_yer)

    return bulunan


#: Liste başlığı için geriye bakılacak karakter sayısı. 200, çünkü
#: "Ön inceleme raporları aşağıda belirtilen bölümlerden oluşur:" gibi bir
#: giriş cümlesi bu uzunluğa rahat sığıyor, bir önceki fıkraya taşmıyor.
_BASLIK_PENCERESI = 200


#: Başlık cümlesinin başındaki fıkra işareti ("- (1) ") -- adın parçası değil.
_FIKRA_ONU = re.compile(r"^\s*[-–—]?\s*\(\d{1,2}\)\s*")


def _liste_basligi(metin: str, yer: int) -> str:
    """Listenin hemen öncesindeki cümle -- hangi rapor türü olduğunu söyler.

    Satır sonları ÖNCE siliniyor, sonra cümleye bölünüyor. Ters sırada
    yapıldığında ölçüldü: "...bölümlerden ve bu sırayla\\noluşur:" cümlesi
    satır sonundan bölünüyor ve listenin adı "oluşur" çıkıyordu -- yani
    kullanıcıya iki iskeleti ayırt etmesi için verilen tek ipucu kayboluyordu.
    """
    onceki = " ".join(metin[max(0, yer - _BASLIK_PENCERESI) : yer].split())
    cumleler = [c.strip() for c in re.split(r"[.:;]", onceki) if c.strip()]

    if not cumleler:
        return "(adsız liste)"

    return _FIKRA_ONU.sub("", cumleler[-1]).strip() or "(adsız liste)"


# ---------------------------------------------------------------------------
# Biçim kuralları
# ---------------------------------------------------------------------------

_CM = re.compile(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*(?:cm|santimetre)\b", re.IGNORECASE)
_PUNTO = re.compile(r"(\d{1,2})\s*punto", re.IGNORECASE)
_NK = re.compile(r"(\d{1,2})\s*(?:-|–|ilâ|ila)\s*(\d{1,2})\s*nk|(\d{1,2})\s*nk", re.IGNORECASE)

#: Font adı: her sözcüğü BÜYÜK HARFLE başlayan bir dizi ("Times New Roman").
#:
#: Bu parça BİLEREK büyük/küçük harfe duyarlı; yalnızca çevresindeki
#: "yazı tipi" kalıbı duyarsız (``(?i:...)``). Tamamı duyarsız olduğunda
#: ölçüldü: "Rapor metni Times New Roman yazı tipi ile" cümlesinden font adı
#: "metni Times New Roman" çıkıyordu -- yani belgeye var olmayan bir yazı
#: tipi yazılırdı ve Word sessizce başka bir fontla açardı. Türkçe resmî
#: metinde font adı her zaman büyük harfle başlıyor, cümlenin gövdesindeki
#: sıradan sözcük başlamıyor. Ayrımı yapan tek şey bu.
_FONT_GOVDESI = (
    r"([A-ZÇĞİÖŞÜ][A-Za-zÇĞİÖŞÜçğıöşü]+(?:\s+[A-ZÇĞİÖŞÜ][A-Za-zÇĞİÖŞÜçğıöşü]+){0,3})"
)

#: "Times New Roman yazı tipi" -- ad ÖNDE.
_FONT_ONDE = re.compile(_FONT_GOVDESI + r"\s+(?i:yazı\s*(?:tip|karakter|font))")

#: "yazı tipi Times New Roman" -- ad ARKADA.
_FONT_ARKADA = re.compile(
    r"(?i:yazı\s*(?:tipi|karakteri|fontu)\s*(?:olarak\s*)?)" + _FONT_GOVDESI
)

#: Kenar boşluğu ölçüsünün yönü. Türkçe küçültme sonrası aranıyor.
_YONLER = (("kenar_sol", "sol"), ("kenar_sag", "sağ"), ("kenar_ust", "üst"), ("kenar_alt", "alt"))

#: Bir cm ölçüsünün KENAR BOŞLUĞU sayılması için penceresinde geçmesi
#: gereken sözcük.
#:
#: Bu kapı olmadan "Paragraflara soldan 1 cm içeriden başlanır" cümlesi sol
#: kenar boşluğunu 1 cm yapıyordu -- yani yönergenin 2,5 cm'lik kuralını
#: yönergenin başka bir cümlesi eziyordu. İki ölçü de "sol" içeriyor; ayıran
#: şey "kenar".
_KENAR_KAPISI = ("kenar", "marj")

#: Girinti ölçüsünün kapısı.
_GIRINTI_KAPISI = ("içeriden", "girinti", "paragraf")

#: Bir cm ölçüsünün önünde bakılacak karakter sayısı. 80, çünkü "Sayfanın sol
#: kenarından" gibi bir niteleme bu uzunluğa sığıyor ve bir önceki ölçüye
#: taşmıyor -- taşsaydı "sağ ve üst kenarından 1,5 cm" ölçüsü kendinden önceki
#: "sol"u da toplardı.
_OLCU_PENCERESI = 80


def _cm_kurallari(birim: Birim) -> list[Kural]:
    """Fıkradaki santimetre ölçülerini kenar boşluğu / girintiye dağıt."""
    kurallar: list[Kural] = []
    onceki_son = 0

    for eslesme in _CM.finditer(birim.metin):
        bas = max(onceki_son, eslesme.start() - _OLCU_PENCERESI)
        pencere = _kucuk(birim.metin[bas : eslesme.start()])
        onceki_son = eslesme.end()

        deger = float(eslesme.group(1).replace(",", "."))
        alinti = _alinti(birim.metin, eslesme.start())

        if any(k in pencere for k in _KENAR_KAPISI):
            for alan, sozcuk in _YONLER:
                if sozcuk in pencere:
                    kurallar.append(Kural(alan, cm(deger), birim.dayanak, alinti))
        elif any(k in pencere for k in _GIRINTI_KAPISI):
            kurallar.append(
                Kural("paragraf_girinti", cm(deger), birim.dayanak, alinti)
            )

    return kurallar


def _yazi_kurallari(birim: Birim) -> list[Kural]:
    """Yazı tipi ve punto."""
    kurallar: list[Kural] = []

    eslesme = _FONT_ONDE.search(birim.metin) or _FONT_ARKADA.search(birim.metin)

    if eslesme:
        ad = " ".join(eslesme.group(1).split())
        # "Metin Times New Roman" -> "Metin" bas sozcugu ATILIYOR: cumle
        # baslangicindaki siradan sozcukler de buyuk harfle basliyor ve font
        # adiyla karisiyor.
        parcalar = ad.split()
        while parcalar and _kucuk(parcalar[0]) in _FONT_ONU_SOZCUKLER:
            parcalar.pop(0)
        if parcalar:
            kurallar.append(
                Kural(
                    "yazi_tipi",
                    " ".join(parcalar),
                    birim.dayanak,
                    _alinti(birim.metin, eslesme.start()),
                )
            )

    punto_eslesme = _PUNTO.search(birim.metin)

    if punto_eslesme:
        kurallar.append(
            Kural(
                "yazi_boyut",
                punto(int(punto_eslesme.group(1))),
                birim.dayanak,
                _alinti(birim.metin, punto_eslesme.start()),
            )
        )

    return kurallar


#: Font adından önce gelebilen, adın parçası OLMAYAN sözcükler. Cümle
#: başındaki büyük harf yüzünden düzenli ifadeye takılıyorlar.
_FONT_ONU_SOZCUKLER = frozenset(
    {"metin", "raporlar", "rapor", "yazılar", "belge", "belgeler", "bunlar", "tüm", "bütün"}
)


def _satir_araligi_kurali(birim: Birim) -> Kural | None:
    """Satır aralığı. OOXML'de 240 = tam bir satır."""
    dusuk = _kucuk(birim.metin)

    if "satır aralı" not in dusuk and "satir arali" not in dusuk:
        return None

    eslesme = re.search(r"(\d(?:[.,]\d)?)\s*satır\s*aralı", birim.metin, re.IGNORECASE)

    if eslesme:
        kat = float(eslesme.group(1).replace(",", "."))
        return Kural(
            "satir_araligi",
            int(round(240 * kat)),
            birim.dayanak,
            _alinti(birim.metin, eslesme.start()),
        )

    if "tek satır aralı" in dusuk:
        return Kural("satir_araligi", 240, birim.dayanak, _alinti(birim.metin, dusuk.find("tek")))

    if "bir buçuk satır" in dusuk:
        return Kural("satir_araligi", 360, birim.dayanak, _alinti(birim.metin, dusuk.find("bir buçuk")))

    return None


#: Hizalama sözcükleri -> OOXML ``w:jc`` değeri.
_HIZALAMA = (
    ("iki yana yasl", "both"),
    ("iki yana hizal", "both"),
    ("blok yaz", "both"),
    ("sola yasl", "left"),
    ("sola dayal", "left"),
)


def _hizalama_kurali(birim: Birim) -> Kural | None:
    dusuk = _kucuk(birim.metin)

    for sozcuk, deger in _HIZALAMA:
        if sozcuk in dusuk:
            return Kural("hizalama", deger, birim.dayanak, _alinti(birim.metin, dusuk.find(sozcuk)))

    return None


def _sayfa_olcusu_kurallari(birim: Birim) -> list[Kural]:
    """Kâğıt ölçüsü. Şimdilik yalnızca A4 -- yönergelerin yazdığı tek ölçü."""
    if not re.search(r"\bA4\b", birim.metin):
        return []

    alinti = _alinti(birim.metin, birim.metin.find("A4"))

    # Word'un kendi yazdigi A4 degerleri. ``yonerge.Bicim`` ile ayni sayilar:
    # hesaplanarak degil, olculen degerle.
    return [
        Kural("sayfa_genislik", 11906, birim.dayanak, alinti),
        Kural("sayfa_yukseklik", 16838, birim.dayanak, alinti),
    ]


def _paragraf_bosluk_kurali(birim: Birim) -> Kural | None:
    """Paragraflar arası boşluk (nk). 1 nk = 20 twip."""
    if "nk" not in _kucuk(birim.metin):
        return None

    eslesme = _NK.search(birim.metin)

    if not eslesme:
        return None

    # Aralik verilmisse UST SINIR aliniyor -- ``yonerge.Bicim``in aynen
    # yazdigi tercih: yogun bir metinde bolumleri gozle ayiriyor ve
    # yonergenin izin verdigi araligin icinde kaliyor.
    nk = int(eslesme.group(2) or eslesme.group(3) or eslesme.group(1))

    return Kural(
        "paragraf_bosluk", nk * 20, birim.dayanak, _alinti(birim.metin, eslesme.start())
    )


def _sayfa_no_kurali(birim: Birim) -> Kural | None:
    """Sayfa numarasının yeri."""
    dusuk = _kucuk(birim.metin)

    if "sayfa numara" not in dusuk:
        return None

    if "sağ" in dusuk:
        deger = "right"
    elif "orta" in dusuk:
        deger = "center"
    elif "sol" in dusuk:
        deger = "left"
    else:
        return None

    return Kural(
        "sayfa_no_hizalama", deger, birim.dayanak, _alinti(birim.metin, dusuk.find("sayfa numara"))
    )


#: Bir kuralın yanında saklanan yönerge cümlesinin uzunluğu.
#:
#: 180 karakter: gözden geçiren kişinin kuralın doğru okunup okunmadığını
#: anlamasına yetiyor, şartname özetini okunmaz hâle getirecek kadar uzun
#: değil.
_ALINTI_UZUNLUGU = 180


def _alinti(metin: str, yer: int) -> str:
    """Kuralın çıkarıldığı cümle -- gözden geçirme için."""
    bas = metin.rfind(".", 0, yer) + 1
    son = metin.find(".", yer)
    son = son + 1 if son != -1 else len(metin)

    parca = " ".join(metin[bas:son].split())

    return parca[:_ALINTI_UZUNLUGU]


# ---------------------------------------------------------------------------
# İfadeler, sayfa aralığı, ek atfı, kapak
# ---------------------------------------------------------------------------

#: Tırnak içine alınmış ifade. Türkçe resmî metinde “ ” yaygın, ama düz
#: tırnak ve « » da geçiyor.
#:
#: İçerik TEK satır sonu geçebiliyor, boş satır geçemiyor. Satır sonunu hiç
#: kabul etmediğinde ölçüldü: yönergede satır kaydırılmış bir ifade
#: (``"soruşturma izni verilmesi\ngerektiği"``) hiç eşleşmiyor, kapanış
#: tırnağı AÇILIŞ sanılıyor ve iki ifadenin arasındaki bağlaç zorunlu ifade
#: olarak kaydediliyordu -- şartnameye ``“veya”`` diye bir kural giriyordu.
#: Boş satırın dışarıda kalması, kapanmamış bir tırnağın sayfalar boyu
#: yutmasını engelliyor.
_TIRNAKLI = re.compile(r"[“\"«]((?:[^”\"»\n]|\n(?!\s*\n)){4,120})[”\"»]")

#: Raporun bittiği kalıbı tarif eden sözcükler.
_KAPANIS_ISARETLERI = ("son bulur", "sona erer", "biter", "cümlesiyle", "ifadesiyle bit")

#: Sonuç bölümünün seçenekli ifadelerini tarif eden sözcükler.
_SONUC_ISARETLERI = ("sonuç bölümünde", "sonuç bölümü", "kanaat", "önerilerden biri")


def _madde_adi(dayanak: str) -> str:
    """"MADDE 11/(7)" -> "MADDE 11". Fıkralar aynı maddeye ait sayılıyor."""
    return dayanak.split("/")[0].strip()


def _ifade_kurallari(
    birimler: list[Birim], tercih_maddesi: str = ""
) -> tuple[str, list[str], str]:
    """Kapanış ifadesi, sonuçta geçmesi gereken ifadeler ve dayanakları.

    İki liste ayrı kapsamda toplanıyor ve bu bilerek:

    * ``zorunlu_ifadeler`` RAPOR TÜRÜNE ait -- yönerge inceleme raporu için
      "kamu zararı tespit edilmiştir", ön inceleme için "soruşturma izni
      verilmesi gerektiği" diyor. Hepsini tek torbaya atmak, ön inceleme
      ifadesi yazılmış bir inceleme raporunu "uygun" saymak olurdu; denetim
      geçer, evrak yanlış çıkardı.
    * ``kapanis_ifadesi`` türden BAĞIMSIZ: yönerge onu bütün raporlar için
      bir kez söylüyor ("Rapor, ... ifadesiyle son bulur"). Tür maddesine
      hapsedilseydi seçilen tür onu tekrar etmediğinde kaybolurdu.
    """
    kapanis = ""
    dayanak = ""
    kapsamli: list[str] = []
    tumu: list[str] = []

    for birim in birimler:
        tirnaklilar = [" ".join(t.split()) for t in _TIRNAKLI.findall(birim.metin)]

        if not tirnaklilar:
            continue

        if not kapanis and birim.gecer(*_KAPANIS_ISARETLERI):
            kapanis = tirnaklilar[-1]
            dayanak = birim.dayanak

        if not birim.gecer(*_SONUC_ISARETLERI):
            continue

        hedef = (
            kapsamli
            if tercih_maddesi and _madde_adi(birim.dayanak) == tercih_maddesi
            else tumu
        )

        for ifade in tirnaklilar:
            if ifade not in hedef:
                hedef.append(ifade)

    zorunlu = kapsamli or tumu

    # Kapanis ifadesi zorunlu listede de duruyorsa cikariliyor: ikisi ayri
    # denetim ve ayni cumleyi iki kez istemek, bir kez yazan raporu iki kez
    # eksik gosterirdi.
    return kapanis, [i for i in zorunlu if i != kapanis], dayanak


#: Rapor metninin sayfa aralığı. Üç ayrı yazım biçimi de geçiyor.
_ARALIK_KALIPLARI = (
    re.compile(r"en\s+az\s+(\d{1,3})[^.\n]{0,20}?en\s+(?:fazla|çok)\s+(\d{1,3})\s*sayfa", re.IGNORECASE),
    re.compile(r"(\d{1,3})\s*(?:ilâ|ila|-|–|—)\s*(\d{1,3})\s*sayfa", re.IGNORECASE),
)
_EN_AZ = re.compile(r"(\d{1,3})\s*sayfadan\s+az\s+olama", re.IGNORECASE)
_EN_COK = re.compile(r"(\d{1,3})\s*sayfayı\s+(?:geçeme|aşama)", re.IGNORECASE)


def _sayfa_araligi(birimler: list[Birim]) -> tuple[int, int, str, str]:
    """Rapor metninin sayfa aralığı ve dayanağı.

    Kapı ``rapor``: bir yönergede "ek dizini 2 sayfayı geçemez" gibi başka
    sayfa kuralları da var ve onları raporun kendi aralığı sanmak, 20 sayfalık
    bir raporu 2 sayfaya sıkıştırmaya çalışmak olurdu.
    """
    for birim in birimler:
        if not birim.gecer("rapor"):
            continue

        for kalip in _ARALIK_KALIPLARI:
            eslesme = kalip.search(birim.metin)
            if eslesme:
                az, cok = int(eslesme.group(1)), int(eslesme.group(2))
                if 0 < az < cok:
                    return az, cok, birim.dayanak, _alinti(birim.metin, eslesme.start())

    az = cok = 0
    dayanak = alinti = ""

    for birim in birimler:
        if not birim.gecer("rapor"):
            continue

        if not az and (eslesme := _EN_AZ.search(birim.metin)):
            az = int(eslesme.group(1))
            dayanak, alinti = birim.dayanak, _alinti(birim.metin, eslesme.start())

        if not cok and (eslesme := _EN_COK.search(birim.metin)):
            cok = int(eslesme.group(1))
            dayanak = dayanak or birim.dayanak
            alinti = alinti or _alinti(birim.metin, eslesme.start())

    return az, cok, dayanak, alinti


_EK_ATIF = re.compile(r"\(\s*Ek\s*[:.]\s*[^)\n]{1,24}\)")

#: Kapak alanlarını sayan madde: "a) Bakanlık adı", "ç) Rapor konusu".
_KAPAK_MADDESI = re.compile(r"^[ \t]*([a-zçğöşü])\s*\)\s*(.{3,80})$", re.MULTILINE)


def _kapak_alanlari(birimler: list[Birim]) -> tuple[list[str], str]:
    """Kapakta bulunması zorunlu alanlar, yönergedeki yazımıyla.

    "kapak" sözcüğünün listeden ÖNCE geçmesi şart. Yalnızca fıkrada geçmesini
    aramak yanlış maddeyi seçiyordu ve sebebi yapısal: bir maddenin metni bir
    sonraki MADDE başlığına kadar sürüyor, yani araya giren bölüm başlığı
    ("İKİNCİ BÖLÜM / Kapak sayfası") bir önceki maddenin SON fıkrasına
    yapışıyor. Ölçüldü -- kapak alanları olarak MADDE 4/(2)'nin yazım
    kuralları ("Kısaltmalar ilk geçtiği yerde açık yazılır") çıkıyordu.

    Sıra koşulu bu bulaşmayı kesiyor ve gerçek bir yapıya dayanıyor: yönerge
    listeyi önce tanıtıp sonra sayıyor, sonuna iliştirmiyor.
    """
    for birim in birimler:
        if not birim.gecer("kapak", "kapağın"):
            continue

        maddeler = list(_KAPAK_MADDESI.finditer(birim.metin))

        if len(maddeler) < 3:
            continue

        dusuk = _kucuk(birim.metin[: maddeler[0].start()])

        if "kapak" not in dusuk and "kapağ" not in dusuk:
            continue

        return [
            " ".join(m.group(2).split()).rstrip(",;.") for m in maddeler
        ], birim.dayanak

    return [], ""


# ---------------------------------------------------------------------------
# Öğrenme
# ---------------------------------------------------------------------------


@dataclass
class Ogrenme:
    """Bir yönergeden çıkarılanların tamamı."""

    sartname: Sartname
    #: Yönergede bulunan BÜTÜN rapor iskeletleri. Şartnameye yalnızca biri
    #: girdi; kullanıcı başkasını seçebilsin diye hepsi burada.
    bolum_adaylari: list[BolumListesi] = field(default_factory=list)
    #: Yönergenin kaç birime ayrıldığı -- çıkarımın gerçekten metnin
    #: tamamını gezdiğini gösteriyor.
    birim_sayisi: int = 0


#: Aynı alan için birden çok kural bulunduğunda hangisi kazanıyor.
#:
#: SONUNCUSU. Yönergeler kuralı önce genel söyleyip sonra özelleştiriyor
#: ("yazılar 12 punto yazılır ... dipnotlar 10 punto"); ama asıl sebep daha
#: basit: ilk eşleşmeyi almak, ölçünün bir tanım cümlesinden mi yoksa bir
#: istisnadan mı geldiğini ayırt edemiyor. Tek bir seçim kuralı olması ve
#: seçilenin dayanağıyla birlikte görünmesi, hangisi olduğundan daha önemli.
def _kurallari_topla(birimler: list[Birim]) -> list[Kural]:
    toplanan: list[Kural] = []

    for birim in birimler:
        toplanan += _cm_kurallari(birim)
        toplanan += _yazi_kurallari(birim)
        toplanan += _sayfa_olcusu_kurallari(birim)

        for kural in (
            _satir_araligi_kurali(birim),
            _hizalama_kurali(birim),
            _paragraf_bosluk_kurali(birim),
            _sayfa_no_kurali(birim),
        ):
            if kural is not None:
                toplanan.append(kural)

    return toplanan


def ogren(
    yol: str | Path,
    kimlik: str,
    bolum_secimi: str = "",
    sayfa_en_az: int = 0,
    sayfa_en_cok: int = 0,
) -> Ogrenme:
    """Yönergeyi oku ve şartname çıkar.

    ``bolum_secimi`` yönergede birden çok iskelet varsa hangisinin
    kullanılacağını seçiyor -- dayanak ("MADDE 17/(2)") ya da başlığın bir
    parçası verilebiliyor. Verilmezse EN UZUN liste seçiliyor ve seçilmeyenler
    ``bolum_adaylari``nda duruyor: araç kararı gizlemiyor, gösteriyor.

    ``sayfa_en_az``/``sayfa_en_cok`` yönergede sayfa aralığı yazmıyorsa
    kullanıcının kendi hedefini koymasına yarıyor; yönergede yazıyorsa
    yönerge kazanıyor -- yönergeyi kullanıcı tercihiyle ezmek, "yönergeye
    uygun" sözünü boşa çıkarırdı.
    """
    hedef = Path(yol)

    if not hedef.exists():
        raise FileNotFoundError(f"yönerge bulunamadı: {hedef}")

    belge = oku(hedef)

    if not belge.kalite.guvenilir:
        raise ValueError(
            f"yönergenin metni güvenilir değil: {belge.kalite.gerekce}"
        )

    return belgeden_ogren(belge, kimlik, bolum_secimi, sayfa_en_az, sayfa_en_cok)


def belgeden_ogren(
    belge: Belge,
    kimlik: str,
    bolum_secimi: str = "",
    sayfa_en_az: int = 0,
    sayfa_en_cok: int = 0,
) -> Ogrenme:
    """Okunmuş bir yönergeden şartname çıkar.

    ``ogren``den ayrı, çünkü testler ve yeniden öğrenme belgeyi bir kez okuyup
    çıkarımı birden çok kez çalıştırıyor -- 70 sayfayı her seferinde yeniden
    ayrıştırmanın anlamı yok.
    """
    birimler = birimlere_ayir(belge.metin)
    kurallar = _kurallari_topla(birimler)

    bicim_degerleri: dict[str, object] = {}
    secilen: dict[str, Kural] = {}

    for kural in kurallar:
        bicim_degerleri[kural.alan] = kural.deger
        secilen[kural.alan] = kural

    adaylar = bolum_listeleri(birimler)
    secilen_liste = _liste_sec(adaylar, bolum_secimi)

    kapanis, zorunlu, ifade_dayanagi = _ifade_kurallari(
        birimler, _madde_adi(secilen_liste.dayanak) if secilen_liste else ""
    )
    az, cok, sayfa_dayanagi, sayfa_alintisi = _sayfa_araligi(birimler)
    kapak, kapak_dayanagi = _kapak_alanlari(birimler)

    if not az and not cok:
        az, cok = sayfa_en_az, sayfa_en_cok
        sayfa_dayanagi = "kullanıcı" if (az or cok) else ""

    ek_atiflar = _EK_ATIF.findall(belge.metin)

    # Cikarilan her sey, secildigi dayanakla birlikte kaydediliyor. Bicim
    # disindaki kurallarin da burada durmasi onemli: ``ozet_metni`` tek bir
    # listeden okuyor ve gozden gecirende "bu nereden geldi" sorusu kalmiyor.
    kayit = [kural.__dict__ for kural in secilen.values()]

    if secilen_liste:
        kayit.append(
            Kural("bolumler", len(secilen_liste.bolumler), secilen_liste.dayanak,
                  secilen_liste.baslik).__dict__
        )
    if kapanis:
        kayit.append(Kural("kapanis_ifadesi", kapanis, ifade_dayanagi).__dict__)
    if az or cok:
        kayit.append(Kural("sayfa_araligi", f"{az}-{cok}", sayfa_dayanagi, sayfa_alintisi).__dict__)
    if kapak:
        kayit.append(Kural("kapak_alanlari", len(kapak), kapak_dayanagi).__dict__)

    sartname = Sartname(
        kimlik=kimlik,
        ad=secilen_liste.baslik if secilen_liste else belge.ad,
        kaynak=belge.ad,
        bolumler=list(secilen_liste.bolumler) if secilen_liste else [],
        bolum_dayanagi=secilen_liste.dayanak if secilen_liste else "",
        bicim_degerleri=bicim_degerleri,
        sayfa_en_az=az,
        sayfa_en_cok=cok,
        zorunlu_ifadeler=zorunlu,
        kapanis_ifadesi=kapanis,
        ek_atif_bicimi=" ".join(ek_atiflar[0].split()) if ek_atiflar else "",
        kapak_alanlari=kapak,
        kurallar=kayit,
        eksik_kurallar=_eksikleri_bul(bicim_degerleri, secilen_liste),
    )

    return Ogrenme(sartname, adaylar, len(birimler))


def _liste_sec(adaylar: list[BolumListesi], secim: str) -> BolumListesi | None:
    """İstenen iskeleti seç; istenmediyse en uzununu.

    En uzun, çünkü bir yönergede kısa listeler çoğu zaman bir bölümün alt
    başlıkları oluyor; rapor iskeleti sayılan listelerin en kapsamlısı.
    Seçim yanlışsa ``bolum_adaylari`` hepsini gösteriyor ve tek bir çağrıyla
    düzeltiliyor.
    """
    if not adaylar:
        return None

    if secim:
        sade = _kucuk(secim)
        for aday in adaylar:
            if sade in _kucuk(aday.dayanak) or sade in _kucuk(aday.baslik):
                return aday

    return max(adaylar, key=lambda a: len(a.bolumler))


def _eksikleri_bul(
    bicim_degerleri: dict[str, object], liste: BolumListesi | None
) -> list[str]:
    """Yönergede aranıp bulunamayanlar -- varsayılana düşülen her alan."""
    eksik = [alan for alan in BEKLENEN_ALANLAR if alan not in bicim_degerleri]

    if liste is None:
        eksik.append("bölüm listesi")

    return eksik
