"""``localhost`` Windows'ta iki saniye — ``127.0.0.1`` dört milisaniye.

Ölçülen hata
------------
Kullanıcının bildirdiği: "her mesajda minimum 10 saniye gecikme." Sıra sıra
elendi -- prompt boyutu değil (100 KB'lık istem bile 4,2 sn), backend değil
(tur logunda model çağrısı dışında hiçbir şey yok), düşünme değil, embedding
değil. Sonra çıkarım YAPMAYAN bir uç nokta ölçüldü::

    GET /v1/models  ->  2,047 sn

Yani süre modelde değil, bağlantıda. Aynı sunucu, aynı port, yalnızca konak
adı değişerek::

    localhost    ->  2,028 / 2,037 / 2,038 sn
    127.0.0.1    ->  0,002 / 0,013 / 0,004 sn
    [::1]        ->  bağlantı reddedildi

Sebep: Windows'ta ``localhost`` önce IPv6 ``::1``e çözülüyor. Yerel çıkarım
sunucuları (LM Studio, Ollama, llama.cpp) varsayılan olarak yalnızca IPv4
dinliyor, yani IPv6 denemesi zaman aşımına uğrayıp IPv4'e düşüyor. Bedel her
istekte iki saniye -- ve bir sohbet turu birden çok istek yapıyor.

Bu bir hız ayarı değil, ÖLÇÜLEN bir hata: kullanıcının şikayetinin en büyük
tek bileşeni.

Neden yeniden yazmak güvenli
----------------------------
``127.0.0.1`` ``localhost``un IPv4 karşılığı; aynı makine, aynı arayüz. Daha
DAR bir adres, farklı bir hedef değil. IPv6'da dinleyen bir sunucuyu bilerek
isteyen kullanıcı adresi açıkça yazabiliyor (``[::1]`` ya da bir konak adı) --
yeniden yazma yalnızca çıplak ``localhost`` için geçerli.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import re
from typing import Any, Final

#: Yerel OpenAI-uyumlu sunucunun varsayılan adresi. ``localhost`` DEĞİL.
LOCAL_OPENAI_BASE_URL: Final = "http://127.0.0.1:1234/v1"

#: Yalnızca çıplak ``localhost`` konağını yakalar; ``localhost.example.com``
#: ya da ``mylocalhost`` gibi adlara dokunmaz.
_LOCALHOST_HOST: Final = re.compile(r"(?i)(?<=://)localhost(?=[:/]|$)")


def prefer_ipv4_loopback(url: Any) -> Any:
    """``http://localhost:1234/v1`` -> ``http://127.0.0.1:1234/v1``.

    Dize olmayan ya da ``localhost`` içermeyen değer OLDUĞU GİBİ dönüyor:
    bu işlev bir yol boyunca çağrılıyor ve orada bir sürprizin bedeli
    sessiz bir bağlantı hatası olurdu.
    """
    if not isinstance(url, str):
        return url

    return _LOCALHOST_HOST.sub("127.0.0.1", url)


def normalize_config_urls(config: Any) -> Any:
    """Yapılandırmadaki her ``base_url`` değerini IPv4 loopback'e çevir.

    BELLEKTEKİ kopya üzerinde çalışıyor -- kullanıcının dosyası
    değiştirilmiyor. Sebebi tek cümle: bu bir hızlandırma, kullanıcının
    yazdığı şeyi değiştirmek değil. Dosyaya yazsaydık kullanıcı hiç
    istemediği bir düzenleme görürdü.
    """
    if isinstance(config, dict):
        return {
            key: (
                prefer_ipv4_loopback(value)
                if key == "base_url"
                else normalize_config_urls(value)
            )
            for key, value in config.items()
        }

    if isinstance(config, list):
        return [normalize_config_urls(item) for item in config]

    return config
