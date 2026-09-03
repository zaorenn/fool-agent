"""Seslendirme motorunu KONUŞULMADAN ÖNCE hazırla.

Ölçülen sorun
-------------
Aynı cümleyi seslendirmek, motor soğukken ve sıcakken taban tabana zıt:

    kokoro     soğuk 24,17 sn   sıcak 0,32 sn
    styletts2  soğuk 67,21 sn   sıcak 0,86 sn

Kullanıcının bildirdiği şey tam olarak bu farktı: "ayarlardan Listen'a
basınca 2,5 saniyede konuşuyor ama Friend modunda dakikalarca model
uyandırılıyor". Ayarlar panelinde motor zaten sıcaktı (az önce önizleme
yapılmıştı); Friend penceresi ise ilk cümlede soğuk yüklemeyi ödüyordu.

Yaklaşım ``fool/stt_warmup.py`` ile AYNI ve sebebi aynı: bekleme
kaçınılmaz (model diskten VRAM'e yüklenecek) ama kullanıcının onu BEKLEMESİ
kaçınılmaz değil. Sesli yüzey açıldığı anda yükleme arka planda başlıyor;
kullanıcı ilk cümlesini söylerken model çoktan hazır oluyor. STT ısıtması
zaten aynı anda koşuyor -- ikisi farklı süreçlerde, birbirini beklemiyorlar.

Neden sessiz bir cümle sentezlemek
----------------------------------
"Yükle ama üretme" diye bir yol yok: motorlar modeli ilk ``synthesize``
çağrısında kuruyor. O yüzden gerçekten kısa bir metin seslendiriliyor ve
çıktı ATILIYOR. Bedeli bir kez ödenen sentez, kazancı ilk gerçek cümlenin
anında çıkması.

Isıtma ASLA istem yolunu bloke etmiyor ve hata ASLA yayılmıyor: bu bir
iyileştirme, bir gereklilik değil. Başarısız olursa eski davranış aynen
geçerli -- ilk seslendirme modeli kendisi yükler.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

#: Isıtma metni KISA: amaç modeli kurmak, uzun bir çıktı üretmek değil.
#: Tek kelime bilerek değil -- bazı motorlar tek heceli girdide prosodi
#: hesaplarını atlıyor ve gerçek cümlede yine ilk-çağrı maliyeti çıkıyor.
WARMUP_TEXT = "Ready."

_lock = threading.Lock()
_thread: threading.Thread | None = None
_state: dict[str, Any] = {"status": "cold", "error": "", "provider": ""}


def status() -> dict[str, Any]:
    """``cold`` | ``warming`` | ``warm`` | ``failed``."""
    return dict(_state)


def _active_provider() -> str:
    """Şu an seçili TTS sağlayıcısı ("" = yok)."""
    try:
        from fool_cli.config import load_config

        cfg = load_config() or {}
    except Exception:
        return ""
    return str((cfg.get("tts") or {}).get("provider") or "").strip()


def _warm_now(provider: str) -> None:
    from fool import voice_preview

    entry_id = voice_preview.entry_for_provider(provider)
    if not entry_id:
        # ISTISNA firlatiliyor, durum burada YAZILMIYOR: basari/basarisizlik
        # kaydini tek yer tutsun (``_run``). Iki yerde yazmak, testlerde
        # ``_warm_now`` degistirilince durumun hic guncellenmemesine yol
        # acmisti -- yani gercek kod yolunda da kirilgan.
        raise ValueError(f"unknown provider: {provider}")

    voice_preview.preview(entry_id, text=WARMUP_TEXT)


def _run(provider: str) -> None:
    global _thread

    try:
        _warm_now(provider)
        _state.update(status="warm", error="")
    except Exception as exc:  # noqa: BLE001 - isitma hatasi sessiz kalmali
        # Kullaniciya HATA GOSTERILMIYOR: isitma basarisiz olduysa ilk gercek
        # cumle modeli kendisi yukler. Burada bir bildirim gostermek, hicbir
        # sey bozulmamisken kullaniciyi telaslandirmak olurdu.
        logger.debug("TTS isitma basarisiz (%s): %s", provider, exc)
        _state.update(status="failed", error=str(exc))
    finally:
        with _lock:
            _thread = None


def _still_resident(provider: str) -> bool:
    """Motor GERÇEKTEN ayakta mı?

    ``_state["status"] == "warm"`` bir kez yazılıyor ve bir daha hiç
    düşmüyordu. Oysa motor boşta 300 sn sonra boşaltılıyor
    (``fool/engine_host.py::SELECTED_IDLE_UNLOAD_SECONDS``). Yani ilk başarılı
    ısıtmadan sonra ``warm()`` kalıcı olarak hiçbir şey yapmıyor: durum
    "warm" diyor, süreç ölü, ve bir sonraki cümle soğuk yükleme bedelini
    yeniden ödüyor.

    Ölçüldü: kokoro soğuk 29,43 sn / sıcak 1,07 sn. Kullanıcının "ses
    dakikalar sonra geldi" dediği şey her uzun aradan sonra geri geliyordu.

    Hata YUTULUYOR ve "yerleşik değil" varsayılıyor: yanlış tarafa düşmenin
    bedeli fazladan bir ısıtma çağrısı (ucuz ve zaten korumalı), diğer tarafta
    ise sessizce ölü kalan bir ısıtma yolu var.
    """
    try:
        from fool import engine_host, voice_preview

        entry_id = voice_preview.entry_for_provider(provider)
        if not entry_id:
            return False

        return engine_host.is_running(entry_id)
    except Exception:  # noqa: BLE001
        return False


def warm(provider: str = "") -> dict[str, Any]:
    """Isıtmayı arka planda başlat ve HEMEN dön.

    Zaten ısınıyorsa ya da ısındıysa yeni bir iş başlatılmıyor: iki ısıtma
    aynı motoru iki kez yüklemeye çalışır ve tek-motor kuralı yüzünden
    (bkz. ``fool/engine_host.py``) yükle-boşalt döngüsüne girerdi.
    """
    global _thread

    target = (provider or _active_provider()).strip()
    if not target:
        return {"status": "cold", "error": "no provider selected", "provider": ""}

    with _lock:
        # Saglayici DEGISTIYSE yeniden isit: kullanici motoru degistirdiginde
        # eskisinin sicak olmasi ise yaramiyor.
        if _thread is not None and _state.get("provider") == target:
            return status()

        if (
            _state.get("status") == "warm"
            and _state.get("provider") == target
            and _still_resident(target)
        ):
            return status()

        _state.update(status="warming", error="", provider=target)
        _thread = threading.Thread(
            target=_run, args=(target,), daemon=True, name="fool-tts-warm"
        )
        _thread.start()

    return status()


def _mark_cold_locked() -> None:
    _state.update(status="cold", error="", provider="")


def mark_cold() -> None:
    """Motor DIŞARIDAN durduruldu -- durum bunu söylesin.

    Kullanıcı sistem tepsisinden "boşalt" dediğinde süreç ölüyor ama bu
    modülün durumu "warm" yazmaya devam ediyordu. ``_still_resident``
    sayesinde bir sonraki ``warm()`` yine de doğru davranıyor; yanlış olan
    ARADAKİ pencere: tepsi menüsü boşaltmanın hemen ardından "sıcak"
    gösteriyor ve kullanıcı isteğinin işlemediğini sanıyor.

    Bkz. ``fool/residency.py::_mark_cold``.
    """
    with _lock:
        _mark_cold_locked()


def reset_for_tests() -> None:
    global _thread

    with _lock:
        _thread = None
        _mark_cold_locked()
