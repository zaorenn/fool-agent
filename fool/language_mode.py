"""Cevap dili ve konuşma dili — AYRI iki karar.

Neden ayrı
----------
İstenen (kullanıcının kendi ifadesi):

    "cevap dili ingilizce ise ona türkçe konuşulsa bile ingilizce cevap
     verecek, ve ses dili japoncaysa seslendirme japonca olacak"

Bunlar tek bir ayar olamaz. Ekranda okunan metnin dili ile hoparlörden çıkan
dilin aynı olma zorunluluğu yok — kullanıcı cevabı **okuyabilmek** için
İngilizce istiyor, ama sesi Japonca duymak istiyor.

Neden persona ile çözülmedi
---------------------------
Persona tek bir dil söyleyebilir. "Japonca cevap ver" dersen kullanıcı cevabı
okuyamaz; "İngilizce cevap ver" dersen ses de İngilizce çıkar. İkisi aynı
anahtarda kaldığı sürece biri diğerini kaybettirir.

Neden modelin GÖRMESİ gerekiyor
-------------------------------
İstenen: "model bunu bilmeli, ona ses dilini değiştir dediğimizde net olarak
değiştirmeli ve kesin olmalı." Yapılandırmada duran ama isteme girmeyen bir
ayar, modelin göremediği bir ayardır: kullanıcı "ses dilini japonca yap" der,
model "tamam" der ve hiçbir şey değişmez. Bu yüzden iki taraf da var —
istemde **durum**, araçta **değiştirme**.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Final

logger = logging.getLogger(__name__)

#: Desteklenen diller. ``tools/tts_tool.py::SPEECH_LANGUAGE_NAMES`` ile aynı
#: küme olmak zorunda: kullanıcı burada kabul edilen bir dili seçip motorun
#: onu reddetmesi, sessiz bir başarısızlık olurdu.
LANGUAGE_NAMES: Final[Dict[str, str]] = {
    "ar": "Arabic", "da": "Danish", "de": "German", "el": "Greek",
    "en": "English", "es": "Spanish", "fi": "Finnish", "fr": "French",
    "he": "Hebrew", "hi": "Hindi", "it": "Italian", "ja": "Japanese",
    "ko": "Korean", "ms": "Malay", "nl": "Dutch", "no": "Norwegian",
    "pl": "Polish", "pt": "Portuguese", "ru": "Russian", "sv": "Swedish",
    "sw": "Swahili", "tr": "Turkish", "zh": "Chinese",
}

#: ``auto`` = kullanıcının yazdığı dile uy (varsayılan davranış).
AUTO: Final = "auto"

#: ``same`` = cevabın dilinde konuş (varsayılan davranış).
SAME: Final = "same"

REPLY_KEY: Final = "agent.reply_language"
SPEECH_KEY: Final = "tts.speech_language"


def normalize(value: Any, *, allow: str) -> str:
    """Dil kodunu doğrula. Tanınmayan değer ``""`` döner.

    ``allow`` bu alanın kabul ettiği özel değer (``auto`` ya da ``same``).
    """
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if raw == allow:
        return raw
    if raw in LANGUAGE_NAMES:
        return raw

    logger.warning(
        "[The Fool] dil kodu %r taninmadi. Gecerli: %s, %s",
        raw,
        allow,
        ", ".join(sorted(LANGUAGE_NAMES)),
    )
    return ""


def display(code: str) -> str:
    """Dil kodunun insan okunur adı."""
    return LANGUAGE_NAMES.get(code, code)


def _config() -> Dict[str, Any]:
    try:
        import yaml

        from fool_constants import get_config_path

        path = get_config_path()
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # pragma: no cover — okunamayan config cokmemeli
        logger.debug("dil ayari okunamadi: %s", exc)
        return {}


def current() -> tuple[str, str]:
    """``(reply_language, speech_language)`` — ayarlanmamışsa boş dize."""
    cfg = _config()
    agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
    tts_cfg = cfg.get("tts") if isinstance(cfg.get("tts"), dict) else {}

    reply = normalize(agent_cfg.get("reply_language"), allow=AUTO)
    speech = normalize(tts_cfg.get("speech_language"), allow=SAME)

    return reply, speech


def prompt_block() -> str:
    """Modelin GÖRECEĞİ kural bloğu. Hiçbiri ayarlı değilse boş.

    Boş dönmek önemli: kural yokken isteme "dil kuralı yok" diye bir bölüm
    eklemek, sıradan bir ajanın istemini sebepsiz büyütürdü.
    """
    # Yalnizca CEVAP dili okunuyor; konusma dili bilerek disarida (asagi bak).
    reply, _speech = current()

    lines: list[str] = []

    # ``auto`` KURAL YAZMIYORDU -- ve o boşluk kendi hatasını üretti.
    #
    # Ölçülen hâl: kullanıcı İngilizce yazdı, sohbet geçmişi Japonca'ydı ve
    # model Japonca devam etti. Kullanıcının bildirdiği: "yazı dili match me
    # olmadı, japonca devam etti."
    #
    # Sebep momentum: kural yokken model geçmişteki turların dilini sürdürüyor.
    # "Kullanıcıya uy" bir varsayılan değil, SÖYLENMESİ gereken bir talimat.
    #
    # Yalnızca konuşma dili ayarlıyken yazılıyor: momentum sorunu tam da o
    # kurulumda çıkıyor (ekranda bir dil, seste başka bir dil). Hiçbir ayarı
    # olmayan sıradan bir ajanın istemini sebepsiz büyütmüyor.
    if (not reply or reply == AUTO) and _speech and _speech != SAME:
        lines.append(
            "- **Reply language: match the user.** Write each reply in the "
            "language of the user's MOST RECENT message. Do not continue in a "
            "language just because earlier turns in this conversation used it "
            "— if the user switches language, you switch with them."
        )
    elif reply and reply != AUTO:
        name = display(reply)
        lines.append(
            f"- **Reply language: {name}.** Write EVERY reply in {name}, no "
            f"matter which language the user writes in. Do not mirror the "
            f"user's language, and do not switch even if asked casually — "
            f"this is a setting, not a preference of the moment."
        )

    # KONUSMA DILI MODELE SOYLENMIYOR -- bilerek.
    #
    # Once soyleniyordu, "do NOT write Japanese in the chat" uyarisiyla
    # birlikte. Olculen sonuc: kullanici Ingilizce "Hello, how are you?" yazdi,
    # ses dili Japonca'ydi ve model cevabi JAPONCA YAZDI:
    #
    #     [warm] こんにちは。元気ですよ！あなたはいかがですか？
    #
    # Kullanicinin bildirdigi: "cevap japonca geldi, ne dedigini anlamiyorum."
    # Yani ekranda okunamayan bir cevap -- ayarin tam tersi.
    #
    # Kucuk bir model icin istemde gecen "Japanese" kelimesi, etrafindaki
    # olumsuzlamadan daha guclu. Yasak yazmak yetmiyor; kelimenin ORADA
    # OLMAMASI gerekiyor.
    #
    # Zaten modelin bu bilgiye ihtiyaci yok: ceviri seslendirme katmaninda
    # yapiliyor (``tools/tts_tool.py::_apply_speech_language``) ve model ne
    # yazarsa yazsin o katman calisiyor. Ayari degistirmek isterse
    # ``set_language_mode`` aracinin aciklamasi ikisini de anlatiyor.

    if not lines:
        return ""

    return (
        "## LANGUAGE SETTINGS (ABSOLUTE)\n\n"
        + "\n".join(lines)
        + "\n\nThese are user-set switches. To change one, use the "
        "`set_language_mode` tool — never by just agreeing to it in text, "
        "which changes nothing."
    )


def apply(reply: str | None = None, speech: str | None = None) -> Dict[str, Any]:
    """Ayarları YAZ ve ne olduğunu döndür.

    Yazmadan "tamam" demek, kullanıcının bir daha aynı şeyi istemesine yol
    açan sessiz bir başarısızlıktı; bu yüzden dönen sözlük gerçekten yazılan
    değeri taşıyor.
    """
    from fool_cli.config import set_config_value

    changed: Dict[str, str] = {}
    rejected: list[str] = []

    if reply is not None:
        code = normalize(reply, allow=AUTO)
        if code:
            set_config_value(REPLY_KEY, code)
            changed["reply_language"] = code
        else:
            rejected.append(str(reply))

    if speech is not None:
        code = normalize(speech, allow=SAME)
        if code:
            set_config_value(SPEECH_KEY, code)
            changed["speech_language"] = code
        else:
            rejected.append(str(speech))

    return {"changed": changed, "rejected": rejected}
