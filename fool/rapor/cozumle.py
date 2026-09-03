"""
Var olan bir raporu çözümle: örnek olarak ÖĞREN, ya da yarım kalmışı TAMAMLA.

İki iş, tek çözümleyici
-----------------------
Kullanıcının iki isteği aynı işlemin iki yüzü:

1. "Örnek olarak verilen inceleme raporunu tam anlamıyla öğrenmeli, nasıl
   yazılır diye." -- örnek rapordan İSKELET ve ÜSLUP çıkarmak.
2. "Yarım kalmış inceleme raporlarını tamamlayabilmeli." -- yarım rapordan
   NE VAR NE YOK'u çıkarmak.

İkisi de aynı şeyi gerektiriyor: bir ``.docx``i bölümlerine ayırmak. O yüzden
tek modül.

Neden modele "bu raporu oku, benzerini yaz" demiyoruz
-----------------------------------------------------
Örnek rapor ~6.400 token. Yarım rapor 70 sayfaya kadar çıkabiliyor, yani tek
başına 40-50 bin token. İkisini birden bağlama koyup üstüne on dilekçe eklemek
64 binlik pencereyi taşırıyor. Bunun yerine örnekten ÇIKARILAN iskelet
veriliyor: bölüm sırası, hangi bölümde ne yapıldığı, kalıp cümleler. Ölçüldü:
iskelet ~600 token, yani örneğin onda biri.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .kaynak import Belge
from .turkce import sade_baslik
from .yonerge import RAPOR_TURLERI, RaporTuru

#: "I. GİRİŞ", "IV. TARTIŞMA VE DEĞERLENDİRME", "X. SONUÇ" gibi bölüm başlıkları.
#: Nokta ZORUNLU değil: örnek raporda "I.GİRİŞ" boşluksuz yazılmış.
_BOLUM_BASI = re.compile(
    r"^\s*([IVX]{1,5})\s*[.\-)]\s*([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ\s,VE]{2,60})\s*$"
)

#: Sonuç bölümündeki "A. Disiplin Yönünden" gibi alt başlıklar.
_ALT_BASLIK = re.compile(r"^\s*([A-DÇ])\s*[.)]\s*(.{3,60})$")


@dataclass
class CozumlenmisBolum:
    """Rapordan çıkarılmış bir bölüm."""

    baslik: str
    satirlar: list[str] = field(default_factory=list)

    @property
    def bos(self) -> bool:
        """Başlık var ama altında metin yok -- yarım raporda olağan hâl."""
        return not any(s.strip() for s in self.satirlar)

    @property
    def karakter(self) -> int:
        return sum(len(s) for s in self.satirlar)


@dataclass
class CozumlenmisRapor:
    """Bir ``.docx`` raporun bölümlere ayrılmış hâli."""

    ad: str
    bolumler: list[CozumlenmisBolum] = field(default_factory=list)
    #: Bölüm başlığından ÖNCE gelen satırlar (kapak, başlık vb.).
    on_bilgi: list[str] = field(default_factory=list)

    def basliklar(self) -> list[str]:
        return [b.baslik for b in self.bolumler]

    def bul(self, baslik: str) -> CozumlenmisBolum | None:
        """Bölümü başlığından bul -- uygulamadaki yazım farklarına dayanıklı.

        Yönerge "V. SONUÇ" diyor, örnek rapor "V. SONUÇ VE ÖNERİLER" yazıyor.
        Tam eşleşme arayınca bitmiş bir rapor "sonuç bölümü yok" diye
        okunuyordu; yani kullanıcıya tamamlanmış raporunun yarım olduğu
        söylenirdi. Biri diğerinin başıysa aynı bölüm sayılıyor.
        """
        hedef = _sadelestir(baslik)

        for bolum in self.bolumler:
            mevcut = _sadelestir(bolum.baslik)
            if mevcut == hedef or mevcut.startswith(hedef) or hedef.startswith(mevcut):
                return bolum

        return None


#: Başlık sadeleştirmesi ``turkce``de duruyor -- taslak ve uygunluk denetimi
#: de aynı kuralı kullanıyor (gerekçe: ``turkce.sade_baslik``).
_sadelestir = sade_baslik


def bolumlere_ayir(belge: Belge) -> CozumlenmisRapor:
    """Raporu bölüm başlıklarından böl."""
    satirlar = [s for s in belge.metin.split("\n")]
    cozumlenmis = CozumlenmisRapor(ad=belge.ad)
    aktif: CozumlenmisBolum | None = None

    for satir in satirlar:
        eslesme = _BOLUM_BASI.match(satir)

        if eslesme:
            rakam, ad = eslesme.groups()
            aktif = CozumlenmisBolum(baslik=f"{rakam}. {ad.strip()}")
            cozumlenmis.bolumler.append(aktif)
            continue

        if aktif is None:
            if satir.strip():
                cozumlenmis.on_bilgi.append(satir.strip())
        else:
            aktif.satirlar.append(satir)

    return cozumlenmis


def tur_tahmin(cozumlenmis: CozumlenmisRapor) -> RaporTuru | None:
    """Bölüm başlıklarına bakarak rapor türünü bul.

    Ön inceleme raporunun on bölümü inceleme raporunun beşiyle karışmıyor;
    ayırt edici olan başlık KÜMESİ, sayısı değil.
    """
    mevcut = {_sadelestir(b) for b in cozumlenmis.basliklar()}

    if not mevcut:
        return None

    en_iyi: RaporTuru | None = None
    en_iyi_puan = 0.0

    for tur in RAPOR_TURLERI.values():
        beklenen = {_sadelestir(b) for b in tur.bolumler}
        ortak = mevcut & beklenen

        if not ortak:
            continue

        # Ortak baslik orani: hem beklenene hem mevcuda gore.
        puan = len(ortak) / len(beklenen)

        if puan > en_iyi_puan:
            en_iyi, en_iyi_puan = tur, puan

    # Yarisindan azi tutuyorsa tur tahmini guvenilir degil.
    return en_iyi if en_iyi_puan >= 0.5 else None


@dataclass
class Eksiklik:
    """Yarım raporda tamamlanması gereken bir bölüm."""

    baslik: str
    durum: str  # "yok" | "bos"

    def __str__(self) -> str:
        return f"{self.baslik} ({self.durum})"


def eksik_bolumler(
    cozumlenmis: CozumlenmisRapor, tur: RaporTuru | None = None
) -> list[Eksiklik]:
    """Türün gerektirdiği hangi bölümler eksik ya da boş?"""
    tur = tur or tur_tahmin(cozumlenmis)

    if tur is None:
        return []

    eksikler: list[Eksiklik] = []

    for baslik in tur.bolumler:
        bolum = cozumlenmis.bul(baslik)

        if bolum is None:
            eksikler.append(Eksiklik(baslik, "yok"))
        elif bolum.bos:
            eksikler.append(Eksiklik(baslik, "boş"))

    return eksikler


# ---------------------------------------------------------------------------
# Örnekten öğrenme
# ---------------------------------------------------------------------------

# Üslup kalıpları ÖRNEKTEN ÖĞRENİLİYOR, listeden değil.
#
# Önce burada sabit bir liste vardı ("görüş ve kanaatine varılmıştır",
# "Arz olunur", ...). Bu liste bu örnek rapor için doğruydu ve BAŞKA bir
# örnek için yanlış olurdu: kullanıcı örneği değiştirebileceğini söyledi ve
# yeni örneğin kendi kalıpları listede yer almadığı için hiç öğrenilmezdi.
#
# Onun yerine örneğin KENDİ cümle sonları sayılıyor: resmî raporda aynı
# bitiş biçimi defalarca geçiyor ("...varılmıştır", "...tespit edilmiştir")
# ve tekrar eden bitiş, o belgenin üslubu demek.

#: Bir kalıp sayılmak için cümle sonunun en az kaç kez geçmesi gerekiyor.
KALIP_ASGARI_TEKRAR = 2

#: Türkçe yüklem sonları -- bildirme ve geçmiş zaman ekleri.
#: Belgeye değil DİLE ait; örnek değişince bunlar değişmiyor.
_YUKLEM_SONLARI = (
    "mıştır", "miştir", "muştur", "müştür",
    "maktadır", "mektedir",
    "dır", "dir", "dur", "dür",
    "tır", "tir", "tur", "tür",
    "mıştı", "mişti", "lmiş", "lmış",
    "ılmıştır", "ilmiştir",
    "acaktır", "ecektir",
    "olunur", "verilir", "yapılır",
)

#: Cümle sonundan alınacak sözcük sayısı. Üç sözcük, kalıbı taşıyacak kadar
#: uzun ("görüş ve kanaatine varılmıştır" -> "ve kanaatine varılmıştır") ve
#: konuya bulaşmayacak kadar kısa.
KALIP_SOZCUK = 3


def _kaliplari_ogren(metin: str, en_fazla: int = 10) -> list[str]:
    """Örnekte tekrar eden cümle sonlarını çıkar.

    Tekrar eden şey YÜKLEM. Yalnızca üç sözcüklük kuyruklar sayıldığında
    hiçbir kalıp bulunamıyordu: "uygun olarak gerçekleştirilmiştir" ile
    "aynı şekilde gerçekleştirilmiştir" farklı kuyruklar, oysa üslup ikisinde
    de aynı. O yüzden her yüklem için TEKRAR EDEN EN UZUN kuyruk alınıyor --
    "ve kanaatine varılmıştır" gibi kalıplaşmış bir bitiş varsa o, yoksa
    yüklemin kendisi.
    """
    from collections import Counter

    kuyruklar: dict[int, Counter[str]] = {n: Counter() for n in (1, 2, 3)}

    for cumle in re.split(r"[.;:]\s+", metin):
        sozcukler = [k.strip() for k in cumle.split() if k.strip()]

        if not sozcukler:
            continue

        yuklem = sozcukler[-1].strip(".,").lower()

        # Kalip YUKLEMLE biter. Bu suzgec olmadan sirket ve kisi adlari kalip
        # sayiliyordu ("tasimacilik sinir tic") -- yani ornegin ICERIGI yeni
        # rapora sizacak yoldan geri geliyordu. Olcut dilin kendisi, bu
        # belgenin sozcukleri degil.
        if not yuklem.endswith(_YUKLEM_SONLARI):
            continue

        for n in (1, 2, 3):
            if len(sozcukler) < n:
                continue

            kuyruk = " ".join(sozcukler[-n:]).strip(".,").lower()

            # Rakam iceren bitisler kalip degil, veridir ("2 Yil 4 Ay").
            if any(k.isdigit() for k in kuyruk):
                continue

            kuyruklar[n][kuyruk] += 1

    # Her yuklem icin TEKRAR EDEN EN UZUN kuyruk.
    secilen: dict[str, tuple[int, str]] = {}

    for n in (1, 2, 3):
        for kuyruk, adet in kuyruklar[n].items():
            if adet < KALIP_ASGARI_TEKRAR or len(kuyruk) <= 4:
                continue

            yuklem = kuyruk.split()[-1]
            onceki = secilen.get(yuklem)

            if onceki is None or n > onceki[0]:
                secilen[yuklem] = (n, kuyruk)

    siralama = Counter({k: kuyruklar[1][y] for y, (_, k) in secilen.items()})

    return [kalip for kalip, _ in siralama.most_common(en_fazla)]


@dataclass
class Iskelet:
    """Örnek rapordan çıkarılan yazım şablonu -- modele verilen şey bu."""

    tur: str
    bolumler: list[str]
    bolum_uzunluklari: dict[str, int]
    ek_atif_bicimi: list[str]
    kalip_ifadeler: list[str]
    alt_basliklar: list[str]

    def metin(self) -> str:
        """Modele verilecek özet. Örneğin tamamı yerine bu gidiyor."""
        satirlar = [f"RAPOR TÜRÜ: {self.tur}", "", "BÖLÜMLER (bu sırayla):"]

        for baslik in self.bolumler:
            uzunluk = self.bolum_uzunluklari.get(baslik, 0)
            satirlar.append(f"  {baslik}  (örnekte ~{uzunluk} karakter)")

        if self.alt_basliklar:
            satirlar += ["", "SONUÇ ALT BAŞLIKLARI:"]
            satirlar += [f"  {a}" for a in self.alt_basliklar]

        if self.ek_atif_bicimi:
            satirlar += ["", "EK ATIF BİÇİMİ (aynen bu kalıpta):"]
            satirlar += [f"  {a}" for a in self.ek_atif_bicimi[:8]]

        if self.kalip_ifadeler:
            satirlar += ["", "KALIP İFADELER (üslup bunlara benzemeli):"]
            satirlar += [f"  {k}" for k in self.kalip_ifadeler]

        return "\n".join(satirlar)


def iskelet_cikar(belge: Belge) -> Iskelet:
    """Örnek rapordan iskelet çıkar.

    Metnin kendisi ALINMIYOR: iskelet biçimi anlatıyor, içeriği değil. Örnek
    raporun cümlelerini modele vermek, o cümlelerin yeni rapora sızması
    demek olurdu -- başka bir soruşturmanın isimleri ve tarihleriyle.
    """
    cozumlenmis = bolumlere_ayir(belge)
    tur = tur_tahmin(cozumlenmis)
    metin = belge.metin

    atiflar: list[str] = []
    for atif in re.findall(r"\(\s*Ek\s*[:.]\s*[^)]{1,24}\)", metin):
        duzgun = " ".join(atif.split())
        if duzgun not in atiflar:
            atiflar.append(duzgun)

    alt_basliklar: list[str] = []
    for satir in metin.split("\n"):
        eslesme = _ALT_BASLIK.match(satir.strip())
        # "Yönünden" DEGIL "Yön": ornek raporda "A. Disiplin Yönünden" ile
        # "B. Cezai Yönden" birlikte geciyor; yalnizca ilkini aramak
        # dordunden ucunu goz ardi ediyordu.
        if eslesme and "Yön" in eslesme.group(2):
            duzgun = f"{eslesme.group(1)}. {eslesme.group(2).strip()}"
            if duzgun not in alt_basliklar:
                alt_basliklar.append(duzgun)

    kaliplar = _kaliplari_ogren(metin)

    # Basliklar TEKILLESTIRILIYOR: iskelet yapiyi anlatiyor, belgedeki
    # tekrarlari degil. Tekilleştirmeden, ayni basligin birden cok kez gectigi
    # bir raporda iskelet belgeyle birlikte buyuyor ve baglami sigdirma amaci
    # kendiliginden bozuluyor -- olculdu: 100 bolumlu bir girdide iskelet
    # 1.621 token, yani belgenin yarisi.
    benzersiz: list[str] = []
    uzunluklar: dict[str, int] = {}

    for bolum in cozumlenmis.bolumler:
        if bolum.baslik not in uzunluklar:
            benzersiz.append(bolum.baslik)
            uzunluklar[bolum.baslik] = 0
        uzunluklar[bolum.baslik] += bolum.karakter

    return Iskelet(
        tur=tur.ad if tur else "belirlenemedi",
        bolumler=benzersiz,
        bolum_uzunluklari=uzunluklar,
        ek_atif_bicimi=atiflar,
        kalip_ifadeler=kaliplar,
        alt_basliklar=alt_basliklar,
    )
