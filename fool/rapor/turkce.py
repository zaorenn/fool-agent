"""
Türkçe büyük/küçük harf -- Python'un ``upper()``ı bu dilde YANLIŞ.

Ölçülen hata
------------
``"DSİ Teftiş Kurulu".upper()`` Python'da ``"DSİ TEFTIŞ KURULU"`` veriyor:
``i`` harfi ``I``ya dönüyor, oysa Türkçede ``i``nin büyüğü ``İ``. Yani
yönergenin "bölüm başlıkları tamamen büyük harfle yazılır" (MADDE 8(8))
kuralını uygularken kurumun KENDİ ADINI yanlış yazıyorduk.

Bu, resmî evrakta en pahalı hata türü: belge açılıyor, biçim doğru, ama
"TEFTIŞ KURULU BAŞKANLIĞI" yazıyor. Bir müfettişin gözüne ilk çarpacak
şey bu ve belgeyi kimin/neyin ürettiğini de ele veriyor.

Türkçede çift yönlü özel eşleme yalnızca i/ı çiftinde:

    küçük  i  ->  büyük  İ        küçük  ı  ->  büyük  I
    büyük  İ  ->  küçük  i        büyük  I  ->  küçük  ı

Diğer harflerde (ş, ğ, ü, ö, ç) Python zaten doğru davranıyor; onlara
dokunulmuyor.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import re

# Once ozel harfleri isaretle, sonra Python'a birak. Dogrudan degistirip
# ``upper()`` cagirmak i -> I -> ... zincirini geri getirirdi.
_BUYUK_ESLEME = str.maketrans({"i": "İ", "ı": "I"})
_KUCUK_ESLEME = str.maketrans({"I": "ı", "İ": "i"})


def buyuk(metin: str) -> str:
    """Türkçe kurallarıyla büyük harfe çevir."""
    return metin.translate(_BUYUK_ESLEME).upper()


def kucuk(metin: str) -> str:
    """Türkçe kurallarıyla küçük harfe çevir."""
    return metin.translate(_KUCUK_ESLEME).lower()


def sade_baslik(metin: str) -> str:
    """Başlığı KARŞILAŞTIRMA için sadeleştir -- yazıma değil, adına bak.

    "I.GİRİŞ", "I. GİRİŞ" ve "I . Giriş" aynı bölüm; yönerge "V. SONUÇ"
    derken rapor "V. SONUÇ VE ÖNERİLER" yazabiliyor. Kelimesi kelimesine
    karşılaştırma bitmiş bir raporu "bölüm yok" diye okuyordu.

    Burada duruyor çünkü aynı sadeleştirmeyi üç yer birden istiyor: taslağın
    eksik bölüm sayımı, çözümleyicinin bölüm eşlemesi ve uygunluk denetimi.
    Üç ayrı kopya, birinin düzeltilip diğerlerinin unutulacağı yerdi -- ve
    bunların ikisi "rapor tamam mı" sorusuna cevap veriyor.
    """
    metin = metin.replace("İ", "i").replace("I", "ı")

    return " ".join(re.sub(r"[^\w\s]", " ", metin.lower()).split())


def baslik(metin: str) -> str:
    """Her kelimenin ilk harfi büyük -- MADDE 8(8) alt başlık biçimi.

    ``str.title()`` kullanılmıyor: o hem Türkçe i/ı'yı bozuyor hem de
    kesmeden sonrasını yeni kelime sayıyor ("Müdürlüğü'Nün" gibi).
    """
    kelimeler = []

    for kelime in metin.split(" "):
        if not kelime:
            kelimeler.append(kelime)
            continue

        kelimeler.append(buyuk(kelime[0]) + kucuk(kelime[1:]))

    return " ".join(kelimeler)


# Roma rakamlari ASCII kurallariyla buyur.
#
# ``buyuk("iii. inceleme")`` Turkce kurali uyguladigi icin ``İİİ.`` uretiyordu.
# Bolum basliklari yonergede zaten buyuk Roma rakamiyla geliyor ("III. GIRIS"),
# ama basligi model uretirse kucuk gelebilir ve resmi bir raporda "İİİ. BOLUM"
# gormek, yanlis yazilmis kurum adi kadar goze batar.
_ROMA = re.compile(r"^([ivxlcdm]+)([.)])", re.IGNORECASE)


def bolum_basligi(metin: str) -> str:
    """Bölüm başlığını büyüt; baştaki Roma rakamına Türkçe kuralı uygulama."""
    eslesme = _ROMA.match(metin.strip())

    if not eslesme:
        return buyuk(metin)

    rakam, isaret = eslesme.groups()
    kalan = metin.strip()[eslesme.end():]

    return f"{rakam.upper()}{isaret}{buyuk(kalan)}"
