"""Sesin duygusu tur başına değişsin.

İstenen davranış
----------------
"Bir espri yaptığımızda gülebilsin, sesindeki duygu duruma göre değişebilsin."

Bugünkü hâl bunu taşımıyor. Chatterbox'ın iki kolu var -- ``exaggeration``
(duygu yoğunluğu) ve ``cfg_weight`` (ifade/hız dengesi) -- ama ikisi de
YAPILANDIRMADA duruyor, yani oturum boyunca sabit. Model ne söylerse söylesin
ses aynı tonda çıkıyor.

Motorun kendisi hazır: eklenti ikisini de İSTEK BAŞINA kabul ediyor
(``plugins/tts/fool-chatterbox``). Eksik olan, modelin niyetini oraya
taşıyacak yol.

Neden satır içi etiket, neden araç çağrısı değil
------------------------------------------------
Bir araç çağrısı tur başına fazladan bir gidiş dönüş demek ve konuşmanın
başlamasını geciktirir -- ilk sese kadar geçen süre, üzerinde en çok
çalışılan şey. Etiket cevabın kendisiyle birlikte geliyor, ek gecikme sıfır.

Etiket cümlenin BAŞINDA ve sabit bir sözlükten olmak zorunda. Serbest metin
kabul etmek, modelin ``[she sounds a bit unsure]`` gibi şeyler yazması ve
onların sesli okunması demekti. Tanınmayan bir etiket düz metin sayılıyor ve
olduğu gibi kalıyor -- yani kural yanlış tarafa düşerse en kötü ihtimalle
köşeli parantez okunuyor, ses kaybolmuyor.

Chatterbox'ın satır içi etiket ayrıştırıcısı YOK: ``[laughs]`` yazmak o
sözcüğü seslendirir. O yüzden etiket burada AYIKLANIYOR ve yerine iki sayı
geçiyor.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Varsayılan sentez ayarları -- Chatterbox'ın kendi varsayılanları.
DEFAULT_EXAGGERATION = 0.5
DEFAULT_CFG_WEIGHT = 0.5


@dataclass(frozen=True)
class Delivery:
    """Bir cümlenin nasıl söyleneceği.

    İki sayı ve bir AD taşıyor çünkü motorlar duyguyu aynı dilde konuşmuyor.
    Chatterbox iki kol veriyor (yoğunluk ve tempo); başka motorlar adlandırılmış
    duygular istiyor. Etiketin kendi adını da taşımak, her motorun anladığını
    almasını sağlıyor ve anlamadığını sessizce yok saymasına izin veriyor --
    ikisini birbirine çevirmeye çalışmaktan iyi.
    """

    #: Duygu yoğunluğu (0.25-2.0).
    exaggeration: float
    #: İfade/hız dengesi. DÜŞÜK = ağır ve yavaş, YÜKSEK = sıkı ve hızlı.
    cfg_weight: float
    #: Etiketin kendi adı (``warm``, ``laughing``...). ``as_config`` sonradan
    #: dolduruyor -- sözlükteki anahtar zaten bu.
    name: str = ""

    def as_config(self) -> dict:
        config = {"exaggeration": self.exaggeration, "cfg_weight": self.cfg_weight}

        if self.name:
            config["emotion"] = self.name

        return config


#: Etiket -> teslimat.
#:
#: Sayılar iki kolun ne yaptığından türüyor: ``exaggeration`` yoğunluğu
#: artırıyor ama konuşmayı HIZLANDIRIYOR, ``cfg_weight``i düşürmek
#: ağırlaştırıp yavaşlatıyor. Yani "yoğun ama ağır" bir ton için ikisi
#: birlikte oynatılıyor -- tek başına exaggeration yükseltmek, bağıran ve
#: aceleci bir ses veriyor.
DELIVERIES: dict[str, Delivery] = {
    "neutral": Delivery(0.5, 0.5, "neutral"),
    # Sıcak: biraz daha ifadeli, belirgin biçimde daha yavaş.
    "warm": Delivery(0.6, 0.40, "warm"),
    "affectionate": Delivery(0.65, 0.35, "affectionate"),
    "soft": Delivery(0.40, 0.30, "soft"),
    # Gülme ENERJİK: yoğunluk yüksek ve tempo da yüksek.
    "amused": Delivery(0.85, 0.55, "amused"),
    "laughing": Delivery(1.10, 0.60, "laughing"),
    "teasing": Delivery(0.75, 0.45, "teasing"),
    "excited": Delivery(1.00, 0.60, "excited"),
    "playful": Delivery(0.80, 0.55, "playful"),
    # Soğuk: düz ve ağır. Düşük yoğunluk + düşük cfg.
    "cold": Delivery(0.30, 0.35, "cold"),
    "flat": Delivery(0.25, 0.40, "flat"),
    "hurt": Delivery(0.45, 0.30, "hurt"),
    "sad": Delivery(0.40, 0.28, "sad"),
    "annoyed": Delivery(0.80, 0.50, "annoyed"),
    "angry": Delivery(1.15, 0.60, "angry"),
    "serious": Delivery(0.40, 0.45, "serious"),
    "sleepy": Delivery(0.30, 0.28, "sleepy"),
}

#: Etiket, metnin EN BAŞINDA ve sözlükte olmak zorunda.
_TAG_RE = re.compile(r"^\s*\[([a-z_]{3,14})\]\s*", re.IGNORECASE)


def split_delivery(text: str) -> tuple[str, Delivery | None]:
    """``(etiketsiz metin, teslimat)``.

    Etiket yoksa ya da tanınmıyorsa metin OLDUĞU GİBİ dönüyor ve teslimat
    ``None``: çağıran o zaman yapılandırmadaki ayarı kullanıyor.
    """
    if not text:
        return text, None

    match = _TAG_RE.match(text)

    if not match:
        return text, None

    delivery = DELIVERIES.get(match.group(1).lower())

    if delivery is None:
        # Tanınmayan etiket DÜZ METİN. Ayıklamak, modelin yazdığı gerçek bir
        # köşeli parantezi sessizce yutmak olurdu.
        return text, None

    return text[match.end():], delivery


def strip_tags(text: str) -> str:
    """Baştaki teslimat etiketini metinden çıkar (tanınmayanı bırakır).

    Etiket ayrıştırmayan yollar için: ayıklanmazsa Chatterbox onu SÖZCÜK
    olarak okur -- satır içi etiket ayrıştırıcısı yok.
    """
    cleaned, _delivery = split_delivery(text)

    return cleaned


def tag_vocabulary() -> list[str]:
    """Modele söylenecek etiket listesi."""
    return sorted(DELIVERIES)


def prompt_hint() -> str:
    """Sistem promptuna giren kullanım açıklaması."""
    return (
        "You may open a spoken reply with one delivery tag in square brackets — "
        + ", ".join("[" + name + "]" for name in tag_vocabulary())
        + " — and it will shape how the sentence is voiced without being read out. "
        "Use it when the delivery is not obvious from the words; skip it otherwise. "
        "One tag, at the very start, or none at all."
    )
