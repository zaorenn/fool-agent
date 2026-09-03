"""Kullanıcı hakkındaki bilgiler izinle yazılır ve iz bırakır.

Bugünkü hâli
------------
``memory(action=add, target=user, ...)`` çağrısı ``USER.md``ye doğrudan
yazıyor. Ne sorulan bir izin var ne de sonradan bakılabilecek bir kayıt.
Kullanıcının kurulu dosyasında bugün duran satırlar buna örnek: favori
şarkısı, indirilenler klasörünün yolu. Hiçbiri için "bunu hatırlayayım mı?"
diye sorulmadı ve hiçbiri bir listede görünmüyor.

Sohbet eden bir üründe bu, zamanla sessizce büyüyen bir profil demek. Sorun
"gizli" olması değil -- dosya kullanıcının kendi makinesinde. Sorun
GÖRÜNMEZ olması: kullanıcı ne bilindiğini bilmiyor, bir şeyi geri almak için
önce onun var olduğunu keşfetmesi gerekiyor.

Ne yapılıyor
------------
1. **Açık rıza.** ``ask`` kipinde (varsayılan) profil yazımı, modelin izni
   ALDIĞINI bildirmesini gerektiriyor. Model bunu ancak kullanıcıya sorup
   cevap aldıktan sonra dürüstçe yapabilir; rehber bunu söylüyor ve mekanizma
   bir eylem gerektirdiği için "farkında olmadan" olmuyor.
2. **Kayıt.** Kabul edilen her yazım günlüğe düşüyor. Kullanıcı ne zaman ne
   eklendiğini tek dosyada görebiliyor.
3. **Sert kapatma.** ``never`` kipi yazımı tamamen kapatıyor.

Rıza kararının kendisi bir YARGI ve yargıyı kod veremez -- kullanıcının
"şunu unutma" demesiyle konuşma arasında geçen bir ayrıntı arasındaki farkı
model ayırt ediyor. Kod burada mekanizmayı ve izlenebilirliği sağlıyor.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

#: ``ask``    - model izni aldığını bildirmeden yazamaz (varsayılan)
#: ``always`` - eski davranış: serbest yazım
#: ``never``  - profil hafızası kapalı
CONSENT_MODES = ("always", "ask", "never")

DEFAULT_MODE = "ask"


def consent_mode(config: Any) -> str:
    """``memory.profile_consent`` -- tanınmayan her şey varsayılana düşer."""
    if not isinstance(config, dict):
        return DEFAULT_MODE
    memory = config.get("memory")
    if not isinstance(memory, dict):
        return DEFAULT_MODE
    mode = str(memory.get("profile_consent") or "").strip().lower()
    return mode if mode in CONSENT_MODES else DEFAULT_MODE


#: Model izin almadan yazmaya kalkıştığında dönen metin. Ne yapacağını
#: SÖYLÜYOR: yalnızca "reddedildi" demek modeli aynı çağrıyı tekrar etmeye
#: iterdi.
NEEDS_CONSENT_MESSAGE = (
    "Refused: writing to the user profile needs the user's permission. "
    "Ask them first, in your own words -- for example \"want me to remember "
    "that?\" -- and only if they say yes, repeat this call with "
    "consent=granted. Do not assume permission from context."
)

DISABLED_MESSAGE = (
    "Refused: profile memory is turned off (memory.profile_consent = never). "
    "Nothing about the user is being stored. Turn it back on with "
    "`fool config set memory.profile_consent ask`."
)


def check_profile_write(mode: str, consent: Any) -> str | None:
    """Bu profil yazımı geçebilir mi? Geçemezse sebebi döndürür.

    ``None`` = geçebilir.
    """
    if mode == "never":
        return DISABLED_MESSAGE
    if mode == "always":
        return None

    # ``ask``: model izni ALDIGINI bildirmek zorunda.
    if isinstance(consent, str) and consent.strip().lower() in {"granted", "yes", "true"}:
        return None
    if consent is True:
        return None
    return NEEDS_CONSENT_MESSAGE


def journal_path():
    from pathlib import Path

    from fool_cli.config import get_hermes_home

    return Path(get_hermes_home()) / "memories" / "profile-journal.jsonl"


def record(content: str, *, mode: str, consent: Any = None) -> None:
    """Kabul edilen bir profil yazımını günlüğe düş.

    Günlük ASLA yazımı engellemez: bir kayıt hatası yüzünden kullanıcının
    isteyerek verdiği bilgiyi kaybetmek yanlış olurdu. Hata sessizce yutuluyor
    ama yazım devam ediyor.
    """
    try:
        path = journal_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "content": str(content)[:2000],
            "mode": mode,
            "consent": str(consent) if consent is not None else "",
        }
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_journal(limit: int = 50) -> list:
    """Son kayıtlar -- kullanıcı ne bilindiğini görebilsin diye."""
    try:
        with open(journal_path(), encoding="utf-8") as fh:
            lines = fh.readlines()
    except Exception:
        return []

    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


PROFILE_MEMORY_GUIDANCE = """REMEMBERING THINGS ABOUT THE USER
Before you store anything about the user in your profile memory
(memory action=add, target=user), ASK THEM. Say it plainly, in your own
words -- "want me to remember that?" -- and only write it if they agree.
Then repeat the call with consent=granted.

Ask for things like: their name, where they live or work, their schedule,
their preferences, their relationships, their health, their files and
folders. Do not infer permission from the fact that they told you something
in conversation; telling you is not the same as asking you to keep it.

You do NOT need to ask when they told you to remember it ("remember that
I...", "don't forget..."). That IS the permission -- just pass
consent=granted.

Everything you store is written to a journal the user can read. Write it the
way you would want it read back to you."""
