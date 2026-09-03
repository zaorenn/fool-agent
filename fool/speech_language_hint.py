"""Konuşma dili ayarlı değilken yabancı dil seslendirildi — BİR KEZ söyle.

Ölçülen bozulma
---------------
``tts.speech_language`` ayarlanmazsa Chatterbox tek dilli modeli yüklüyor ve
Türkçeyi İngilizce fonetiğiyle okuyor: ``Merhaba`` -> ``Mehabal``. Ses çıkıyor,
hata da yok; kullanıcı yalnızca "telaffuz bozuk" duyuyor ve sebebi hiçbir yerde
görünmüyor.

Neden İLK KURULUMDA SORULMUYOR
------------------------------
Kullanıcının kararı. Kuruluma bir soru daha eklemek, çoğu kullanıcı için
gereksiz bir adım -- İngilizce konuşan kimse bu ayarı hiç görmek zorunda
değil. Uyarı, sorun GERÇEKTEN ortaya çıktığı anda ve tam çözüldüğü yerde
(ses panelinde) çıkıyor.

Neden TAHMİN EDİP OTOMATİK AYARLAMIYORUZ
----------------------------------------
Latin alfabesinde Türkçe/İngilizce ayrımı güvenilir değil ve yanlış bir tahmin
kullanıcıyı hiç istemediği bir dile geçirirdi -- bozuk telaffuzdan daha kötü,
çünkü artık ayarda da yanlış yazıyor.

Burada yapılan tahmin DEĞİL: yalnızca YÜKSEK KESİNLİKLİ işaretler aranıyor.
Yanlış pozitifin bedeli kapatılabilir bir satır; yanlış negatifin bedeli
bugünkü durum, yani hiçbir şey kaybedilmiyor.

Bilinen SINIR
-------------
Saf ASCII Türkçe ayırt edilemiyor: ``Merhaba`` -- yani bu sorunun kanonik
örneğinin ta kendisi -- İngilizce'den ayrılamaz. Ayrılabildiğini iddia eden
her yöntem tahmindir ve yukarıdaki sebeple istenmiyor.

Pratikte bu bir gecikme, kayıp değil: ``note`` seslendirilen HER cümlede
çalışıyor ve ``ı``/``ğ``/``ş`` içermeyen bir Türkçe konuşmanın sürmesi
beklenmiyor. Uyarı ilk işaretli cümlede çıkıyor -- ölçülen bozulma da zaten
tek cümlede duyuluyor, yani kullanıcı sebebi hâlâ ilk dakikada öğreniyor.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Final

logger = logging.getLogger(__name__)

#: Yalnızca Türkçe (ve Azerice) yazımda geçen harfler.
#:
#: ``ç ö ü`` BİLEREK yok: Almanca, Fransızca, İsveççe ve daha fazlası onları
#: kullanıyor, yani işaret olarak kesinlikleri düşük. ``ı`` (noktasız i) ve
#: ``ğ`` pratikte Türkçeye özel.
_TURKISH_ONLY: Final = frozenset("ıİğĞşŞ")

#: Latin DIŞI yazı sistemleri: burada tahmine hiç gerek yok, metnin İngilizce
#: olmadığı kesin.
_SCRIPTS: Final[tuple[tuple[str, int, int], ...]] = (
    ("greek", 0x0370, 0x03FF),
    ("cyrillic", 0x0400, 0x04FF),
    ("hebrew", 0x0590, 0x05FF),
    ("arabic", 0x0600, 0x06FF),
    ("devanagari", 0x0900, 0x097F),
    ("thai", 0x0E00, 0x0E7F),
    ("hangul-jamo", 0x1100, 0x11FF),
    ("hiragana", 0x3040, 0x309F),
    ("katakana", 0x30A0, 0x30FF),
    ("cjk", 0x4E00, 0x9FFF),
    ("hangul", 0xAC00, 0xD7AF),
)


def detect_signal(text: str) -> str | None:
    """Metin İngilizce OLMADIĞINI kesin gösteren bir işaret taşıyor mu?

    Dönen değer bir dil TAHMİNİ değil, gözlenen işaretin adı. Panelde
    gösterilecek metin buna göre değil, yalnızca "bir dil ayarlaman gerekiyor"
    diye kuruluyor -- işaret sebebi anlatmak için var.
    """
    if not text:
        return None

    for ch in text:
        if ch in _TURKISH_ONLY:
            return "turkish"

        code = ord(ch)

        # ASCII en sık durum: tek karşılaştırmayla ele.
        if code < 0x0370:
            continue

        for name, low, high in _SCRIPTS:
            if low <= code <= high:
                return name

    return None


def _marker_path() -> Path:
    """İşaret MAKİNE evinde, profilde değil.

    Uyarı bir makine gerçeği ("bu makinede yabancı dil seslendirildi"), profil
    ayarı değil. Profil başına tutmak, aynı kullanıcıya aynı uyarıyı her
    profilde yeniden göstermek olurdu.
    """
    from fool.machine_assets import machine_home

    return machine_home() / "speech-language-hint.json"


def _speech_language_set() -> bool:
    """Kullanıcı konuşma dilini SEÇMİŞ mi?

    Seçtiği anda uyarının konusu kalmıyor -- ayrıca kapatmasına da gerek
    kalmamalı, yoksa çözülmüş bir sorun ekranda durmaya devam ederdi.
    """
    from fool import language_mode

    _reply, speech = language_mode.current()

    return bool(speech)


def note(text: str) -> None:
    """Seslendirilen metni GÖR, gerekiyorsa işareti bırak.

    Sessiz ve en iyi çaba: bu çağrı konuşma yolunun ortasında duruyor ve bir
    uyarı uğruna sesi düşürmek, çözmeye çalıştığından kötü bir hata olurdu.
    """
    try:
        if _speech_language_set():
            return

        signal = detect_signal(text)

        if not signal:
            return

        path = _marker_path()

        # ZATEN varsa dokunma: kullanıcı kapattıysa ``dismissed`` orada duruyor
        # ve her cümlede yeniden yazmak uyarıyı geri getirirdi.
        if path.exists():
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"signal": signal}), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 — uyarı sesi düşüremez
        logger.debug("konusma dili ipucu yazilamadi: %s", exc)


def pending() -> dict[str, Any] | None:
    """Panelde gösterilecek uyarı (``None`` = yok)."""
    try:
        if _speech_language_set():
            return None

        raw = json.loads(_marker_path().read_text(encoding="utf-8"))

        if not isinstance(raw, dict) or raw.get("dismissed"):
            return None

        signal = str(raw.get("signal") or "")

        if not signal:
            return None

        return {"signal": signal, "message": message(signal)}
    except FileNotFoundError:
        return None
    except Exception as exc:  # noqa: BLE001 — ipucu katalogu dusuremez
        logger.debug("konusma dili ipucu okunamadi: %s", exc)
        return None


def dismiss() -> None:
    """Kullanıcı kapattı — bir daha gösterme.

    Dosya SİLİNMİYOR, işaretleniyor: silmek, bir sonraki yabancı dilli cümlede
    uyarıyı geri getirirdi.
    """
    try:
        path = _marker_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"dismissed": True}), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.debug("konusma dili ipucu kapatilamadi: %s", exc)


def message(signal: str) -> str:
    """Ne olduğunu, neden olduğunu VE nereden düzelteceğini birlikte söyle.

    Denetimin YERİ geçiyor: "Voice" seçici ses panelinde DEĞİL, başlık
    çubuğundaki küre ikonunun altında. Uyarıyı okuyan kişi ses panelinde
    duruyor, yani yeri söylemeden "bir ayar var" demek onu aramaya
    göndermek olurdu.

    Örnek de geçiyor: "yanlış telaffuz" soyut, ``Merhaba -> Mehabal`` ise
    kullanıcının zaten duyduğu şey.
    """
    what = "Turkish" if signal == "turkish" else "a non-English script"

    return (
        f"Speech in {what} was sent to the voice engine while Voice language "
        'is still "Same as reply". Engines that load one language at a time '
        "read it with English phonetics — Merhaba becomes Mehabal. "
        "Set Voice from the globe icon in the title bar."
    )
