"""Nefes: cümleler arasına gerçek sessizlik konuyor.

Sorun
-----
Akan seslendirme metni cümle cümle sentezliyor ve parçaları arka arkaya
çalıyor. Aradaki tek boşluk motorun bir sonraki parçayı ÜRETME süresi -- yani
motor ne kadar hızlanırsa konuşma o kadar sıkışıyor. Ölçülen rakamlarla:
Kokoro sonraki çağrılarda 0,08 sn'ye iniyor ve cümleler neredeyse üst üste
biniyor. Teknik olarak mükemmel, kulakta nefessiz.

Bu, hızlandırmanın kendi ürettiği bir kusur: yavaş motorda (Chatterbox 28 sn)
kimse fark etmiyordu.

Yaklaşım
--------
Duraklama AÇIKÇA üretiliyor ve motorun hızına bırakılmıyor. Süreler insan
konuşmasındaki tipik aralıklardan: cümle arası 300-500 ms, virgülde
150-250 ms, asılı bırakılan bir cümleden sonra daha uzun.

Sessizlik PCM olarak EKLENİYOR, beklenerek değil. Akış boru hattında bir
``sleep`` bir sonraki parçanın sentezini de geciktirirdi ve kazanılan
gecikmeyi geri verirdi -- sessizlik veriyken sentez arka planda devam ediyor.
"""

from __future__ import annotations

from typing import Any

#: Cümle sonu (``.`` ``!`` ``?``). İnsan konuşmasında tipik aralık 300-500 ms;
#: alt uca yakın duruyoruz çünkü sohbet temposu okumadan hızlı.
SENTENCE_PAUSE_MS = 320

#: Asılı biten cümle (``...`` ``…`` ``--`` ``—``). "Devam edeceğim" demek;
#: hemen devam etmek düşünmeden konuşuyor gibi duyuluyor.
TRAILING_PAUSE_MS = 480

#: Yan cümle (``,`` ``;`` ``:``). Nefes değil, vurgu.
CLAUSE_PAUSE_MS = 170

#: Paragraf sonu. Konu değişiyor; en uzun aralık.
PARAGRAPH_PAUSE_MS = 560

#: Noktalamasız parça: cümlenin ORTASI. Zorla boşaltma ya da uzunluk sınırı
#: yüzünden bölünmüş. Orada durmak kekelemek olurdu.
CONTINUATION_PAUSE_MS = 60

#: Üst sınır. Bozuk bir hesap yüzünden saniyelerce sessizlik konuşmayı
#: öldürürdü; kullanıcı uygulamanın donduğunu sanır.
MAX_PAUSE_MS = 1_500

#: Sondaki tırnak/parantez kararı değiştirmemeli: ``"Tamam."`` ile ``Tamam.``
#: aynı şey.
_TRIM = " \t\r\"'`)]}»”’"

_TRUE = frozenset({"1", "on", "true", "yes", "y"})
_FALSE = frozenset({"0", "off", "false", "no", "n"})


def pauses_enabled(config: Any) -> bool:
    """``tts.pauses`` -- varsayılan açık.

    Kapatılabilir olması gerekiyor: bazı motorlar (özellikle uzun metni tek
    seferde işleyenler) kendi duraklamasını zaten koyuyor ve üstüne eklemek
    ağır duyuluyor.
    """
    if not isinstance(config, dict):
        return True
    tts = config.get("tts")
    if not isinstance(tts, dict):
        return True
    raw = tts.get("pauses")
    if raw is None:
        return True
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in _FALSE:
            return False
        if value in _TRUE:
            return True
    return True


def pause_ms_after(text: Any) -> int:
    """Bu parçadan SONRA ne kadar sessizlik gerekiyor?"""
    if not isinstance(text, str):
        return 0

    if text.endswith("\n\n") or text.rstrip(" \t\r").endswith("\n\n"):
        return PARAGRAPH_PAUSE_MS

    stripped = text.strip().rstrip(_TRIM)
    if not stripped:
        return 0

    if stripped.endswith(("...", "…", "--", "—", "–")):
        return TRAILING_PAUSE_MS
    if stripped.endswith((".", "!", "?", "！", "？", "。")):
        return SENTENCE_PAUSE_MS
    if stripped.endswith((",", ";", ":", "，", "；", "：")):
        return CLAUSE_PAUSE_MS
    return CONTINUATION_PAUSE_MS


def silence_pcm(duration_ms: int, sample_rate: int, *, channels: int = 1) -> bytes:
    """``duration_ms`` kadar int16 sessizlik.

    Akış sözleşmesi int16 little-endian mono; sessizlik de aynı biçimde
    olmak zorunda, yoksa oynatıcı gürültü duyar.
    """
    try:
        duration = int(duration_ms)
        rate = int(sample_rate)
        chans = max(1, int(channels))
    except (TypeError, ValueError):
        return b""

    if duration <= 0 or rate <= 0:
        return b""

    duration = min(duration, MAX_PAUSE_MS)
    frames = duration * rate // 1000
    return b"\x00" * (frames * 2 * chans)


def pause_pcm_after(
    text: Any, sample_rate: int, *, channels: int = 1, enabled: bool = True
) -> bytes:
    """Parçadan sonra çalınacak sessizliği üret. Kapalıysa boş."""
    if not enabled:
        return b""
    return silence_pcm(pause_ms_after(text), sample_rate, channels=channels)
