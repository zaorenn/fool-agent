"""Upstream ortam değişkenleri için geriye dönük uyumluluk.

Tam yeniden adlandırma ``HERMES_*`` öneklerini ``FOOL_*`` yaptı. Kod tarafı
tutarlı, ama **kullanıcının kendi makinesindeki ayarlar öyle değil**:

* ``setx HERMES_HOME ...`` ile kalıcı ayarlamış olabilir
* systemd unit'i, Docker compose dosyası, CI secret'ı ``HERMES_*`` taşıyor olabilir
* upstream dokümanlarını takip eden herkes ``HERMES_*`` yazıyor

Bunlar sessizce yok sayılırsa belirti çok kötü olur: uygulama açılır, hiçbir
hata vermez, ama yanlış veri dizinini kullanır — yani kullanıcının oturumları
ve hafızası "kaybolmuş" görünür.

Bu modül tek bir kural uygular::

    FOOL_X varsa onu kullan, yoksa HERMES_X'e bak.

Yeni ad her zaman kazanır, böylece ikisi birden ayarlıysa davranış belirsiz
kalmaz.
"""

from __future__ import annotations

import os
from typing import Final

#: Yeni önek -> eski önek.
_NEW: Final[str] = "FOOL_"
_OLD: Final[str] = "HERMES_"


def getenv(name: str, default: str = "") -> str:
    """``FOOL_*`` oku, yoksa ``HERMES_*`` karşılığına düş.

    ``name`` yeni adla verilir (``FOOL_HOME``). Öneki taşımayan bir ad
    verilirse doğrudan okunur.

    >>> import os
    >>> os.environ["HERMES_EXAMPLE"] = "eski"
    >>> getenv("FOOL_EXAMPLE")
    'eski'
    >>> os.environ["FOOL_EXAMPLE"] = "yeni"
    >>> getenv("FOOL_EXAMPLE")
    'yeni'
    """
    value = os.environ.get(name, "")
    if value:
        return value

    if name.startswith(_NEW):
        legacy = _OLD + name[len(_NEW):]
        value = os.environ.get(legacy, "")
        if value:
            return value

    return default


def legacy_name(name: str) -> str | None:
    """``FOOL_X`` için ``HERMES_X`` döndür; önek yoksa ``None``."""
    if name.startswith(_NEW):
        return _OLD + name[len(_NEW):]
    return None


def active_legacy_vars() -> dict[str, str]:
    """Hâlâ eski adla ayarlanmış değişkenleri döndür.

    Teşhis için: kullanıcı "ayarım neden çalışmıyor" dediğinde hangi eski
    değişkenlerin devrede olduğunu göstermek üzere.
    """
    found: dict[str, str] = {}
    for key, value in os.environ.items():
        if not key.startswith(_OLD) or not value:
            continue
        new_key = _NEW + key[len(_OLD):]
        if not os.environ.get(new_key):
            found[key] = value
    return found
