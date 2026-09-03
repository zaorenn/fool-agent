"""Kullanıcının kendi verisi — hiçbir kurulum/güncelleme buna dokunamaz.

Neden yazılı bir sözleşme
-------------------------
İstenen (kullanıcının kendi ifadesi): "hiçbir update asla ama asla kullanıcının
bilgilerini değiştirip silmemeli."

Bu kural bugüne kadar örtük duruyordu ve iki kez ölçülebilir biçimde çiğnendi:

1. ``install.ps1`` kurulum sonunda ``FOOL_HOME``u KULLANICI kapsamına yazıyordu.
   Masaüstünün ``test:desktop:fresh`` sınavı ``%TEMP%`` altındaki bir sandbox
   eviyle kurulum yapınca o geçici yol kalıcı oldu; uygulama o günden sonra her
   açılışta BOŞ bir dizine girdi. Kullanıcının gördüğü: "girlfriend gitmiş, ses
   klonlarım gitmiş, bütün sohbetlerim gitmiş." Hiçbiri silinmemişti -- uygulama
   başka yere bakıyordu. Silmek kadar kötü, çünkü kullanıcı için farkı yok.

2. Kaldırıcı ``%LOCALAPPDATA%\\fool``u sessizce bırakıyordu; yarım kalan bir
   kurulum sonraki her kurulumu da bozuyordu.

Örtük kural, kimsenin sınamadığı kuraldır. Bu dosya kuralı VERİ hâline getiriyor
ve ``tests/fool/test_user_data_contract.py`` onu tutuyor.

Sınıflandırma
-------------
``OWNED``       Kullanıcının ürettiği, yeniden üretilemeyen şeyler. Bir
                güncelleme bunları ne siler ne değiştirir ne taşır.
``REPLACEABLE`` Silinse yeniden elde edilen şeyler (depo klonu, sanal
                ortamlar, önbellekler, günlükler). Güncelleme bunlara
                dokunabilir.

Bir şey hangisine gireceği belli değilse ``OWNED`` sayılır: yanlış tarafa
düşmenin bedeli asimetrik -- gereksiz saklamak disk, yanlış silmek kullanıcının
hafızası.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

from typing import Final

#: Kullanıcının kendi verisi. ``FOOL_HOME`` köküne GÖRE adlar.
#:
#: Profil evleri (``profiles/<ad>/``) aynı yapıyı tekrarlıyor; bu yüzden liste
#: hem kök hem profil altında geçerli.
OWNED: Final[frozenset[str]] = frozenset(
    {
        # Yapılandırma ve kimlik
        ".env",
        "auth.json",
        "config.yaml",
        "profile.yaml",
        "SOUL.md",
        # Konuşmalar ve hafıza
        "state.db",
        "memories",
        "sessions",
        "checkpoints",
        # Kullanıcının kurduğu şeyler
        "profiles",
        "skills",
        "plugins",
        "desktop-plugins",
        "skins",
        # Ses: klonlar ve indirilen sesler
        "voices",
        # İş durumu
        "cron",
        "kanban",
        "kanban.db",
        "projects.db",
        "verification_evidence.db",
        "pets",
        "pairing",
        "whatsapp",
        "platforms",
        # Kullanıcının koyduğu dosyalar
        "assets",
        "scripts",
        "indirilenler",
    }
)

#: Silinebilir: hepsi yeniden üretiliyor.
REPLACEABLE: Final[frozenset[str]] = frozenset(
    {
        # Depo klonu — yeniden klonlanır. IKI ad da burada: dizin
        # ``hermes-agent`` -> ``fool-agent`` olarak göç etti
        # (``apps/desktop/electron/runtime-root.ts``) ve göç edememiş
        # kurulumlar eski adı taşımaya devam ediyor. Yalnızca yeni adı yazmak,
        # eski klonu "kullanıcı verisi" sayardı; yalnızca eskisini yazmak
        # -- ilk hali buydu -- göç etmiş bir kurulumda gigabaytlarca klonu
        # dokunulmaz ilan ederdi. İkisi de yeniden üretilebilir.
        "fool-agent",
        "hermes-agent",
        "sidecars",  # motor ortamları — yeniden kurulur (büyük ama üretilebilir)
        "cache",
        "audio_cache",
        "image_cache",
        "bootstrap-cache",
        "logs",
        "runtime",
        "state-snapshots",
        "gateway-service",
        "sandboxes",
        "terminal-sessions",
        "pending_messages",
        "__pycache__",
    }
)


def is_owned(name: str) -> bool:
    """``name`` kullanıcının verisi mi?

    Bilinmeyen ad ``True`` döner: sınıflandırılmamış bir şeyi silmek, bu
    dosyanın var olma sebebinin ta kendisi.
    """
    cleaned = name.strip().strip("/\\")
    if not cleaned:
        return True

    return cleaned not in REPLACEABLE


def sanity_check() -> None:
    """İki küme çakışamaz.

    Çakışsalardı ``is_owned`` sessizce ``REPLACEABLE`` tarafına düşer ve
    kullanıcı verisi silinebilir sayılırdı.
    """
    overlap = OWNED & REPLACEABLE
    if overlap:
        raise AssertionError(f"OWNED ve REPLACEABLE cakisiyor: {sorted(overlap)}")
