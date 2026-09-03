"""Bilinen medya sitelerinde bağlantıyı "oynatarak açan" biçime çevir.

Neden
-----
Kullanıcı "şu şarkıyı aç" dediğinde sayfanın açılması yetmiyor; oynaması
isteniyor. Ajanın otomasyon tarayıcısıyla gidip oynat düğmesine tıklaması ise
pahalı (sayfanın DOM'u on binlerce token), yavaş ve kullanıcının kontrol
edemediği ayrı bir pencere açıyor.

Çoğu site bunu URL parametresiyle zaten destekliyor. Parametreyi eklemek
bedava: çalışırsa şarkı oynar, çalışmazsa sayfa yine normal açılır.

Tarayıcı politikası — dürüst sınır
----------------------------------
Chrome/Edge/Arc, sesli otomatik oynatmayı **kullanıcı etkileşimi olmadan**
engeller. Ama istisna var: tarayıcı o sitedeki geçmiş etkileşimini ölçüyor
(Media Engagement Index). YouTube'u düzenli kullanan birinde `autoplay=1`
genellikle çalışır; hiç kullanmamış bir profilde çalışmaz.

Yani bu bir garanti değil, yüksek olasılıklı bir kestirme. Başarısız olduğunda
davranış bozulmuyor — sayfa açık, kullanıcı bir kez tıklıyor.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

#: Alan adı -> eklenecek sorgu parametreleri.
#: Sadece sitenin KENDİ desteklediği parametreler; uydurma yok.
_AUTOPLAY_PARAMS: dict[str, dict[str, str]] = {
    "youtube.com": {"autoplay": "1"},
    "www.youtube.com": {"autoplay": "1"},
    "music.youtube.com": {"autoplay": "1"},
    "youtu.be": {"autoplay": "1"},
    "vimeo.com": {"autoplay": "1"},
    "player.vimeo.com": {"autoplay": "1"},
    "soundcloud.com": {"auto_play": "true"},
    "twitch.tv": {"autoplay": "true"},
    "www.twitch.tv": {"autoplay": "true"},
    "dailymotion.com": {"autoplay": "1"},
    "www.dailymotion.com": {"autoplay": "1"},
}


def supports_autoplay(url: str) -> bool:
    """URL, oynatma parametresi bilinen bir siteye mi ait?"""
    try:
        return urlparse(url).netloc.lower() in _AUTOPLAY_PARAMS
    except ValueError:
        return False


def with_autoplay(url: str) -> str:
    """Bilinen bir medya sitesiyse oynatma parametresini ekle.

    Bilinmeyen site ya da bozuk URL: olduğu gibi döner — asla hata fırlatmaz,
    çünkü bu yolun başarısızlığı "sayfa yine de açılsın" ile sonuçlanmalı.

    Kullanıcının kendi yazdığı parametre KORUNUR: birisi ``autoplay=0``
    yazmışsa bunu bilinçli yapmıştır, üzerine yazmak yanlış olur.
    """
    try:
        parts = urlparse(url)
    except ValueError:
        return url

    params = _AUTOPLAY_PARAMS.get(parts.netloc.lower())
    if not params:
        return url

    existing = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in params.items():
        existing.setdefault(key, value)

    return urlunparse(parts._replace(query=urlencode(existing)))
