"""
Belgenin TAMAMINI değil, işe yarayan kısmını seç.

Neden
-----
Rehber 73 sayfa, ~44 bin token. Yönerge tek başına ~135 bin token. Modelin
penceresi 64-128 bin. İkisini birden vermek imkânsız; vermek gerekse bile
gereksiz: "inceleme raporu nasıl yazılır" sorusunun cevabı rehberin disiplin
cezaları bölümünde değil.

Bu yüzden büyük kaynak belgeler (mevzuat, rehber) SORGUYA GÖRE okunuyor:
belge başlıklarından bölümlere ayrılıyor, bölümler sorguya benzerliğine göre
sıralanıyor ve yalnızca bütçeye sığan en ilgili olanlar veriliyor.

Neden gömme (embedding) yok
---------------------------
Gömme modeli çağırmak ya ağ ister ya da ayrı bir yerel model yükler. Kullanıcının
şartı belgelerin makineden çıkmaması ve her şeyin yerel çalışması. Sözcük
tabanlı sıralama (BM25) tamamen yerel, bağımlılıksız ve bu iş için yeterli:
aradığımız şey anlamsal benzerlik değil, resmî metinde GEÇEN terim -- "rapor
bölümleri", "zamanaşımı", "disiplin cezası" gibi.

DİKKAT: bu seçicilik yalnızca BÜYÜK KAYNAK belgeler için. Örnek rapor ve
tamamlanacak yarım rapor HER ZAMAN eksiksiz okunuyor (bkz. ``cozumle``) --
kullanıcının açık şartı. Yarım bir raporun okunmamış bir paragrafı, tamamlanan
metinle çelişen bir rapor demek.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .kaynak import Belge, token_tahmini
from .turkce import kucuk

#: Rehber/yönerge başlıkları: "B. TEMEL KAVRAM VE İLKELER", "MADDE 17- (1)",
#: "1. Temel Kavramlar", "III. İNCELEME VE ARAŞTIRMA".
_BASLIK = re.compile(
    r"^\s*(?:"
    r"(?:MADDE\s+\d+)"
    r"|(?:[A-ZÇĞİÖŞÜ]\s*[.)]\s+[A-ZÇĞİÖŞÜ0-9])"
    r"|(?:[IVX]{1,5}\s*[.)]\s*[A-ZÇĞİÖŞÜ])"
    r"|(?:\d+\s*[.)]\s+[A-ZÇĞİÖŞÜ])"
    r")"
)

#: Türkçe çekim ekleri -- kaba gövdeleme. Tam bir biçimbilim çözümleyicisi
#: değil; amaç "raporların" ile "rapor"u aynı saymak.
_EKLER = (
    "larının", "lerinin", "ların", "lerin", "ları", "leri", "lar", "ler",
    "ında", "inde", "unda", "ünde", "dan", "den", "tan", "ten",
    "nın", "nin", "nun", "nün", "ın", "in", "un", "ün",
    "ya", "ye", "na", "ne", "da", "de", "ta", "te", "ı", "i", "u", "ü",
)

#: Çok geçtiği için ayırt ediciliği olmayan sözcükler.
_DURAK = frozenset(
    """ve veya ile ise ancak fakat için gibi kadar daha çok az bir bu şu o
    olarak olan olup üzere göre yer alan tarafından hakkında dair""".split()
)


def _govdele(kelime: str) -> str:
    for ek in _EKLER:
        if len(kelime) > len(ek) + 2 and kelime.endswith(ek):
            return kelime[: -len(ek)]
    return kelime


def terimler(metin: str) -> list[str]:
    """Metni aranabilir terimlere ayır."""
    ham = re.findall(r"\w+", kucuk(metin), re.UNICODE)

    return [
        _govdele(k)
        for k in ham
        if len(k) > 2 and k not in _DURAK and not k.isdigit()
    ]


@dataclass
class Kesit:
    """Belgenin bir başlık altındaki bölümü."""

    belge: str
    baslik: str
    ilk_sayfa: int
    metin: str

    @property
    def atif(self) -> str:
        return f"{self.belge} s.{self.ilk_sayfa} · {self.baslik}"


def kesitlere_ayir(belge: Belge, azami_token: int = 4000) -> list[Kesit]:
    """Belgeyi kendi başlıklarından bölümlere ayır.

    Başlık sınırı, sabit uzunlukta kesmekten iyi: bir bölümün ortasından
    kesilen metin, sorguya uyan yarısını kaybediyor. Başlıksız uzun bölümler
    yine de bütçeye göre bölünüyor.
    """
    kesitler: list[Kesit] = []

    for no, sayfa in enumerate(belge.sayfalar, start=1):
        baslik = "(başlıksız)"
        yigin: list[str] = []

        def bosalt(baslik: str, sayfa_no: int) -> None:
            govde = "\n".join(yigin).strip()
            if govde:
                kesitler.append(Kesit(belge.ad, baslik, sayfa_no, govde))

        for satir in sayfa.split("\n"):
            sade = satir.strip()

            # Uzunluk sinirini "MADDE n" YEMEZ.
            #
            # Once "baslik 90 karakterden kisa olmali" kurali vardi ve mevzuat
            # metninde ters tepiyordu: DOCX'te her fikra TEK SATIR, yani
            # "MADDE 17- (1) Inceleme ve sorusturma gorevleri kapsaminda
            # duzenlenecek raporlar; I. GIRIS, II. KONU..." satiri 600
            # karakter. Baslik sayilmayinca bir onceki maddenin govdesine
            # yapisiyordu -- olculdu: rapor bolumlerini tanimlayan MADDE 17,
            # tam da onu soran sorguda hic bulunamiyordu.
            madde_mi = bool(re.match(r"^\s*MADDE\s+\d+", satir))
            yeni_baslik = bool(_BASLIK.match(satir)) and (madde_mi or len(sade) < 90)

            if yeni_baslik:
                if yigin:
                    bosalt(baslik, no)
                    yigin = []

                # Etiket kisaltiliyor ama satirin KENDISI govdeye giriyor:
                # maddenin hukmu basligin icinde duruyor.
                baslik = sade[:80]

                if madde_mi:
                    yigin.append(satir)

                continue

            yigin.append(satir)

            if token_tahmini("\n".join(yigin)) > azami_token:
                bosalt(baslik, no)
                yigin = []

        bosalt(baslik, no)

    return kesitler


def _bm25(kesitler: list[Kesit], sorgu: str) -> list[tuple[float, Kesit]]:
    """Klasik BM25 -- tamamen yerel, bağımlılıksız."""
    sorgu_terimleri = terimler(sorgu)

    if not sorgu_terimleri or not kesitler:
        return [(0.0, k) for k in kesitler]

    belgeler = [Counter(terimler(k.metin + " " + k.baslik)) for k in kesitler]
    uzunluklar = [sum(b.values()) for b in belgeler]
    ortalama = sum(uzunluklar) / len(uzunluklar) if uzunluklar else 1.0
    n = len(belgeler)

    # BM25 sabitleri: literatürdeki olagan degerler.
    k1, b = 1.5, 0.75
    puanlar: list[tuple[float, Kesit]] = []

    for sayac, uzunluk, kesit in zip(belgeler, uzunluklar, kesitler):
        puan = 0.0

        for terim in sorgu_terimleri:
            gecen = sum(1 for d in belgeler if terim in d)

            if gecen == 0:
                continue

            idf = math.log(1 + (n - gecen + 0.5) / (gecen + 0.5))
            frekans = sayac.get(terim, 0)

            if frekans == 0:
                continue

            payda = frekans + k1 * (1 - b + b * uzunluk / (ortalama or 1))
            puan += idf * frekans * (k1 + 1) / (payda or 1)

        # Baslikta gecen terim daha degerli: resmi belgede baslik konuyu
        # dogrudan soyluyor ("Rapor bolumleri", "Zamanasimi").
        baslik_terimleri = set(terimler(kesit.baslik))
        puan += 2.0 * len(baslik_terimleri & set(sorgu_terimleri))

        puanlar.append((puan, kesit))

    return puanlar


def ilgili_kesitler(
    belge: Belge, sorgu: str, token_butcesi: int = 8000
) -> list[Kesit]:
    """Sorguya en uygun, bütçeye sığan kesitleri döndür.

    Sıra korunuyor: seçilen kesitler puana göre değil BELGEDEKİ SIRAYLA
    veriliyor. Mevzuat metninde sıra anlam taşıyor -- madde 17'yi madde 8'den
    önce okumak, atıfları tersine çeviriyor.
    """
    kesitler = kesitlere_ayir(belge)
    puanlar = _bm25(kesitler, sorgu)

    secilen: list[Kesit] = []
    harcanan = 0

    for puan, kesit in sorted(puanlar, key=lambda p: p[0], reverse=True):
        if puan <= 0:
            break

        maliyet = token_tahmini(kesit.metin)

        if harcanan + maliyet > token_butcesi:
            continue

        secilen.append(kesit)
        harcanan += maliyet

    sira = {id(k): i for i, k in enumerate(kesitler)}

    return sorted(secilen, key=lambda k: sira[id(k)])
