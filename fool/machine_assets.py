"""Profil DEĞİL MAKİNE düzeyindeki varlıkların kökü.

Ölçülen hata
------------
``sidecar_root()`` ve ``voice_dir()`` doğrudan ``get_hermes_home()`` altına
yazıyordu. Masaüstü bir profili çalıştırırken ``FOOL_HOME`` o profilin dizinini
gösteriyor (``.../fool/profiles/<ad>``), yani her profil KENDİ motor
kurulumunu istiyordu.

Kullanıcının makinesinde ölçüldü::

    fool/sidecars/                       chatterbox, f5-tts, kokoro,
                                         kyutai, qwen3-tts, styletts2
    fool/profiles/persona/sidecars/   YOK

Sonuç: ``persona`` profilinde konuşma denemesi "Chatterbox kurulu degil"
ile düşüyor -- oysa Chatterbox kurulu, sadece bir dizin yukarıda. Kullanıcının
gördüğü, motoru seçmiş olmasına rağmen hiç ses çıkmaması.

Düzeltmenin gerekçesi tek cümle: bunlar KULLANICI DURUMU değil, MAKİNE
varlıkları. Bir sidecar ortamı gigabaytlarca, değişmez ve profil başına
kopyalanması anlamsız -- indirilen ses ağırlıkları da öyle.

Masaüstü tarafı bu ayrımı zaten biliyor: ``electron/backend-env.ts``
içindeki ``normalizeFoolHomeRoot`` profil yolunu köke çeviriyor. Python
tarafında karşılığı yoktu.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

from pathlib import Path

#: Profil dizinlerinin altında durduğu klasör adı.
_PROFILES_DIRNAME = "profiles"


def machine_home() -> Path:
    """``FOOL_HOME`` -- ama bir PROFİL evi ise kökü.

    ``.../fool/profiles/persona`` -> ``.../fool``
    ``.../fool``                     -> ``.../fool``
    """
    from fool_constants import get_hermes_home

    home = Path(get_hermes_home()).resolve()

    if home.parent.name.lower() == _PROFILES_DIRNAME:
        return home.parent.parent

    return home
