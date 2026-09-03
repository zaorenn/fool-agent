"""
Rapor biçim kuralları ve bölüm şablonları -- YÖNERGEDEN, koddan değil.

Neden bu dosya var
------------------
Resmî rapor biçimi tahmin edilecek bir şey değil: DSİ Teftiş Kurulu Başkanlığı
"Görev Usul ve Esaslarına İlişkin Yönerge"si kenar boşluğunu milimetre,
yazı tipini punto, sayfa numarasını "1/30" biçimiyle yazıyor. Bir dil modeli
bunları her seferinde doğru üretemez -- ve üretemediğinde ortaya çıkan şey
"biraz yanlış" bir resmî evrak oluyor, ki hiç olmamasından kötü.

O yüzden biçim ÜRETİLMİYOR, uygulanıyor: aşağıdaki değerler koda gömülü
sabitler değil VERİ. Yönerge değişirse (kullanıcı açıkça "bu yönergeler
değişebilir" dedi) tek yapılacak şey bu tabloyu değiştirmek ya da çalışma
anında ``Bicim`` nesnesini kendi değerleriyle kurmak; üretim kodu aynı kalıyor.

Kaynak: DSİ Teftiş Kurulu Başkanlığı Görev Usul ve Esaslarına İlişkin
Yönerge, MADDE 5-10 (şekil standartları) ve MADDE 17 (rapor bölümleri).
Ölçülen değerler yönergenin kendi metninden alındı, yorumlanmadı.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping, Sequence

# OOXML uzunlukları "twip" (1/20 punto, 1/1440 inç).
#
# Çevrim TAM yapılıyor (1440/2,54), yaklaşık 567 ile değil. Fark küçük ama
# yönü kötü: 567 ile 2,5 cm 1418 twip çıkıyor, Word'ün kendi yazdığı değer
# 1417. A4'te fark daha görünür -- 567 ile 11907x16840, gerçek A4 ise
# 11906x16838. Sayfa ölçüsü kayarsa sayfalama kayar, sayfalama kayarsa
# yönergenin "1/30" sayfa numarası yanlış toplamı gösterir.
TWIP_PER_CM = 1440.0 / 2.54


def cm(value: float) -> int:
    """Santimetreyi twip'e çevir."""
    return int(round(value * TWIP_PER_CM))


def punto(value: float) -> int:
    """Puntoyu OOXML'in yarım-punto birimine çevir (``w:sz``)."""
    return int(round(value * 2))


@dataclass(frozen=True)
class Bicim:
    """Yönergenin şekil standartları. MADDE 8 karşılığı."""

    # MADDE 8(2): A4 (210x297 mm) -- Word'ün yazdığı değerlerle birebir.
    sayfa_genislik: int = 11906
    sayfa_yukseklik: int = 16838

    # MADDE 8(2): sol 2,5 cm; sağ ve üst 1,5 cm; alt 3,0 cm.
    kenar_sol: int = cm(2.5)
    kenar_sag: int = cm(1.5)
    kenar_ust: int = cm(1.5)
    kenar_alt: int = cm(3.0)

    # MADDE 8(3): Times New Roman, 12 punto.
    yazi_tipi: str = "Times New Roman"
    yazi_boyut: int = punto(12)

    # MADDE 8(3): 1 satır aralığı, iki yana yaslı (blok).
    satir_araligi: int = 240  # 240 = tam 1 satır (w:lineRule="auto")
    hizalama: str = "both"

    # MADDE 8(4): her paragrafa soldan 1 cm içeriden başlanır.
    paragraf_girinti: int = cm(1.0)

    # MADDE 8(4): paragraflar arasında 3-6 nk boşluk. Aralığın ortası değil
    # ÜST SINIRI seçildi: 6 nk, yoğun bir metinde bölümleri gözle ayırıyor ve
    # yönergenin izin verdiği aralığın içinde.
    paragraf_bosluk: int = 120  # 6 nk = 120 twip

    # MADDE 8(9): sayfa numarası sağ üst köşede, "1/30" biçiminde.
    sayfa_no_hizalama: str = "right"

    def ile(self, **degisiklikler: object) -> "Bicim":
        """Yönerge değiştiyse: tek alanı değiştirilmiş yeni bir biçim."""
        return replace(self, **degisiklikler)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Rapor türleri -- MADDE 16 ve MADDE 17
# ---------------------------------------------------------------------------
#
# Bölüm başlıkları YÖNERGEDEKİ SIRAYLA ve yönergedeki yazımla. Roma rakamı
# başlığın parçası: yönerge "I. GİRİŞ" diye yazıyor, "1. Giriş" değil.


@dataclass(frozen=True)
class RaporTuru:
    """Bir rapor çeşidi ve zorunlu bölümleri."""

    kimlik: str
    ad: str
    bolumler: Sequence[str]
    # MADDE 17(8): her rapor türünün sonuç bölümünde BULUNMASI GEREKEN
    # kesin ifadelerden en az biri. Boş liste = yönerge kesin ifade dayatmıyor.
    sonuc_ifadeleri: Sequence[str] = field(default_factory=tuple)


# MADDE 17(1): inceleme ve soruşturma raporları.
_INCELEME_BOLUMLERI = (
    "I. GİRİŞ",
    "II. KONU",
    "III. İNCELEME VE ARAŞTIRMA",
    "IV. TARTIŞMA VE DEĞERLENDİRME",
    "V. SONUÇ",
)

# MADDE 17(2): ön inceleme raporları -- tamamen ayrı bir iskelet.
_ON_INCELEME_BOLUMLERI = (
    "I. GİRİŞ",
    "II. MUHBİR VE MÜŞTEKİ",
    "III. İDDİA",
    "IV. OLAYIN ÖĞRENİLME TARİHİ",
    "V. OLAY YERİ VE TARİHİ",
    "VI. HAKKINDA ÖN İNCELEME YAPILANLAR",
    "VII. ÖN İNCELEME KONUSU",
    "VIII. HAKKINDA ÖN İNCELEME YAPILANLARIN İFADELERİ",
    "IX. İNCELEME VE DEĞERLENDİRME",
    "X. SONUÇ",
)

RAPOR_TURLERI: Mapping[str, RaporTuru] = {
    "inceleme": RaporTuru(
        kimlik="inceleme",
        ad="İNCELEME RAPORU",
        bolumler=_INCELEME_BOLUMLERI,
        # MADDE 17(8)(a)
        sonuc_ifadeleri=(
            "ön inceleme yapılması gerektiği",
            "disiplin soruşturması yapılması gerektiği",
            "Cumhuriyet Başsavcılığına bildirimde bulunulması gerektiği",
            "kamu zararı tespit edilmiştir",
            "kamu zararı tespit edilmemiştir",
            "yapılacak işlem bulunmadığı",
        ),
    ),
    "disiplin": RaporTuru(
        kimlik="disiplin",
        ad="DİSİPLİN SORUŞTURMA RAPORU",
        bolumler=_INCELEME_BOLUMLERI,
        # MADDE 17(8)(b): ceza önerisi kanun maddesi VE bendi ile.
        sonuc_ifadeleri=(
            "disiplin cezasını gerektirmediği",
            "disiplin cezasını gerektirdiği",
        ),
    ),
    "adli": RaporTuru(
        kimlik="adli",
        ad="ADLİ SORUŞTURMA RAPORU",
        bolumler=_INCELEME_BOLUMLERI,
        # MADDE 17(8)(c)
        sonuc_ifadeleri=(
            "yetkili mercie bildirimde bulunulması gerekmektedir",
            "yapılacak işlem bulunmamaktadır",
        ),
    ),
    "on_inceleme": RaporTuru(
        kimlik="on_inceleme",
        ad="ÖN İNCELEME RAPORU",
        bolumler=_ON_INCELEME_BOLUMLERI,
        # MADDE 17(8)(ç)
        sonuc_ifadeleri=(
            "soruşturma izni verilmesi gerektiği",
            "soruşturma izni verilmemesi gerektiği",
        ),
    ),
}

# MADDE 17(9): rapor bu ifadeyle biter. Tür ne olursa olsun.
KAPANIS_IFADESI = "görüş ve kanaatine varılmıştır"

# MADDE 7: raporun her 30 sayfası için EN FAZLA 1 sayfa özet.
OZET_SAYFA_ORANI = 30


def ozet_sayfa_siniri(metin_sayfa_sayisi: int) -> int:
    """MADDE 7'nin izin verdiği azami özet sayfası."""
    if metin_sayfa_sayisi <= 0:
        return 0

    # "her 30 sayfa için en fazla 1 sayfa": 30 sayfaya kadar 1, 31'de 2.
    return (metin_sayfa_sayisi + OZET_SAYFA_ORANI - 1) // OZET_SAYFA_ORANI
