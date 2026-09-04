"""Chatterbox TTS sağlayıcısı (Resemble AI, MIT).

Neden bu model
--------------
Yerel TTS'te iki eksen var: hız ve gerçekçilik. Piper hız tarafının ucunda ama
sesi robotik. Chatterbox gerçekçilik tarafının ucunda ve hâlâ küçük (0.5B —
16 GB VRAM'e fazlasıyla sığar). Üreticinin kör dinleme testinde ElevenLabs'a
%65.3'e %24.5 tercih edilmiş. MIT lisanslı, yani dağıtımda sorun yok.

Ek olarak **sıfır-atış ses klonlama** yapıyor: 5-10 saniyelik bir referans
kaydı yeterli, eğitim gerekmiyor.

Neden eklenti, neden yerleşik değil
-----------------------------------
``agent/tts_provider.py`` ABC'si tam bunun için var — dosyanın kendi ifadesiyle
*"the hook is additive infrastructure waiting for a real consumer"*. Eklenti
olarak eklemek upstream dosyalarına HİÇ dokunmamak demek, yani bu sağlayıcı
``git merge upstream/main`` sırasında asla çakışmaz.

Yapılandırma::

    tts:
      provider: chatterbox
      chatterbox:
        device: auto          # auto | cuda | cpu
        exaggeration: 0.5     # duygu yoğunluğu (0.25-2.0)
        cfg_weight: 0.5       # ifade/hız dengesi
        voice_sample: ~/.fool/voices/ben.wav   # ses klonlama referansı
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
from typing import Any, Dict, List, Optional

from agent.tts_provider import TTSProvider

logger = logging.getLogger(__name__)

#: Sidecar ortamının adı — ``fool/voice_models.py`` katalog kimliğiyle AYNI
#: olmak zorunda, yoksa panel "kurulu" derken sağlayıcı ortamı bulamaz.
SIDECAR_NAME = "chatterbox"

#: ``chatterbox.mtl_tts``in desteklediği diller (paketteki
#: ``SUPPORTED_LANGUAGES`` ile aynı).
#:
#: Burada KOPYA duruyor çünkü doğrulama ANA süreçte yapılıyor ve ``chatterbox``
#: orada içe aktarılamaz — motor kendi izole ortamında. Kopyayı okumak, geçersiz
#: bir dil kodunun alt sürece kadar gidip orada anlaşılmaz bir hatayla
#: düşmesinden iyi.
_SUPPORTED_LANGUAGES = frozenset(
    {
        "ar", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi", "it",
        "ja", "ko", "ms", "nl", "no", "pl", "pt", "ru", "sv", "sw", "tr", "zh",
    }
)

#: Kalıcı motor sürecinin AÇILIŞ kodu.
#:
#: Chatterbox katalogdaki en ağır motor; her cümlede yeniden yüklemek
#: dakikalar sürüyordu. Model burada BİR KEZ yükleniyor ve süreç açık
#: kaldığı sürece bellekte kalıyor.
_SETUP = """
import inspect

import torch
import torchaudio

_device = DEVICE
if _device == "auto":
    _device = "cuda" if torch.cuda.is_available() else "cpu"
if _device == "cuda" and not torch.cuda.is_available():
    _device = "cpu"

# TURBO tercih ediliyor -- olculdu (RTX 4070 Ti SUPER, ayni referanssiz metin):
#
#   chatterbox.tts        1,89 sn / cumle
#   chatterbox.tts_turbo  1,60 sn sentez -> 6,40 sn ses = gercek zamanin 4 KATI
#
# Turbo 350M ve token->mel cozucusu 10 adimi 1'e indiriyor; klonlama kalitesi
# ayni API ile geliyor (``audio_prompt_path``).
#
# Geri dusus ONEMLI: eski bir kurulumda ``chatterbox.tts_turbo`` yok ve
# oradaki kullaniciyi sessizce sessizlige dusurmek kabul edilemez.
#
# INGILIZCE DISI DIL AYRI BIR MODEL ISTIYOR
# -----------------------------------------
# Olculdu: Turkce bir cumle (``Merhaba. Ben Lynn.``) turbo motorla
# sentezlenip geri yaziya dokuldugunde ``Mehabal, denlin, baradiyam`` cikti --
# yani motor Turkce metni INGILIZCE fonetigiyle okuyor. Ses uretiliyor, hata
# yok, kullaniciya "TTS calismiyor" gibi gorunuyor. Sessiz basarisizlik.
#
# ``chatterbox.mtl_tts`` 23 dil destekliyor (``SUPPORTED_LANGUAGES``, Turkce
# dahil) ve klonlamayi ayni ``audio_prompt_path`` ile yapiyor. Ingilizce yolu
# turbo'da birakiliyor: olculen 1,60 sn/cumle ile en hizlisi o.
_lang = LANG_ID

if _lang and _lang != "en":
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS as _Engine

    _variant = "multilingual"
else:
    try:
        from chatterbox.tts_turbo import ChatterboxTurboTTS as _Engine

        _variant = "turbo"
    except Exception:
        from chatterbox.tts import ChatterboxTTS as _Engine

        _variant = "classic"

_model = _Engine.from_pretrained(device=_device)

# Turbo'nun imzasi klasikten DAR: ``exaggeration``/``cfg_weight`` orada
# olmayabiliyor ve bilinmeyen bir anahtar argumani TypeError ile dusuyor --
# yani kullanici hicbir ses duymuyor. Imza bir kez okunuyor.
try:
    _accepts = set(inspect.signature(_model.generate).parameters)
except (TypeError, ValueError):
    _accepts = set()

_SCRIPTS = (
    ("ja", lambda t: any(0x3040 <= ord(c) <= 0x309F or 0x30A0 <= ord(c) <= 0x30FF for c in t)),
    ("ko", lambda t: any(0xAC00 <= ord(c) <= 0xD7AF or 0x1100 <= ord(c) <= 0x11FF or 0x3130 <= ord(c) <= 0x318F for c in t)),
    ("zh", lambda t: any(0x4E00 <= ord(c) <= 0x9FFF for c in t)),
    ("ru", lambda t: any(0x0400 <= ord(c) <= 0x04FF for c in t)),
    ("ar", lambda t: any(0x0600 <= ord(c) <= 0x06FF for c in t)),
    ("he", lambda t: any(0x0590 <= ord(c) <= 0x05FF for c in t)),
    ("hi", lambda t: any(0x0900 <= ord(c) <= 0x097F for c in t)),
    ("el", lambda t: any(0x0370 <= ord(c) <= 0x03FF for c in t)),
)

_TR_UNIQUE = frozenset("ıİğĞşŞ")
_TR_DIACRITICS = frozenset("çÇöÖüÜ")

_VOCAB = {
    "en": frozenset({
        "i", "im", "the", "is", "are", "am", "you", "your", "my", "and", "to", "in", "it",
        "listening", "hello", "hi", "hey", "what", "why", "how", "can", "help", "for", "with",
        "on", "that", "this", "have", "has", "do", "does", "did", "not", "yes", "no", "sure",
        "okay", "ok", "please", "thanks", "thank", "good", "well", "will", "would", "could",
        "should", "be", "been", "there", "here", "we", "they", "our", "their", "of", "at", "by",
        "from", "as", "so", "just", "now", "about", "like", "see", "know", "think", "say", "go",
        "get", "make", "take", "come", "all", "any", "some", "me", "him", "her", "us", "them",
        "right", "got", "listen", "let", "want", "need", "ready", "start", "stop", "fine"
    }),
    "tr": frozenset({
        "ben", "sen", "o", "biz", "siz", "onlar", "bir", "ve", "veya", "ama", "fakat",
        "icin", "için", "ile", "bu", "su", "şu", "ne", "nasil", "nasıl", "neden", "niye",
        "kim", "tamam", "evet", "hayir", "hayır", "peki", "merhaba", "selam", "dinliyorum",
        "yardim", "yardım", "edebilirim", "yapabilirim", "var", "yok", "cok", "çok", "daha",
        "en", "gibi", "kadar", "sonra", "once", "önce", "simdi", "şimdi", "burada", "surada",
        "orada", "guzel", "güzel", "iyi", "kotu", "kötü", "olur", "olmaz", "lutfen", "lütfen",
        "tesekkur", "teşekkür", "ederim", "sagol", "sağol", "tamamdir", "tamamdır", "anladim",
        "anladım", "oldu", "bakarim", "bakarım", "bakarız", "bakariz", "gorusuruz", "görüşürüz",
        "dinle", "hazirim", "hazırım", "efendim", "tabii", "tabi", "aynen"
    }),
    "de": frozenset({
        "ich", "du", "er", "sie", "es", "wir", "ihr", "und", "der", "die", "das", "ein", "eine",
        "nicht", "ist", "sind", "ja", "nein", "danke", "bitte", "hallo", "gut", "sehr"
    }),
    "fr": frozenset({
        "je", "tu", "il", "elle", "nous", "vous", "ils", "elles", "et", "le", "la", "les", "un",
        "une", "pas", "est", "sont", "oui", "non", "merci", "bonjour", "salut", "bien"
    }),
    "es": frozenset({
        "yo", "tu", "tú", "el", "él", "ella", "nosotros", "ellos", "ellas", "y", "la", "los", "las",
        "un", "una", "no", "si", "sí", "es", "son", "gracias", "hola", "bien", "muy"
    })
}

import re as _re

def _detect_sentence_language(text: str, default: str = "tr") -> str:
    if not text or not text.strip():
        return default

    # 1. Non-latin script detection (100% certainty)
    for lang, check in _SCRIPTS:
        if check(text):
            return lang

    # 2. Turkish unique letters
    if any(c in _TR_UNIQUE for c in text):
        return "tr"

    # 3. Tokenize words
    words = [w.replace("'", "") for w in _re.findall(r"[a-zA-ZçÇöÖüÜäÄßéÉèÈàÀâÂêÊôÔîÎùÙñÑíÍóÓúÚáÁ']+", text.lower())]
    if not words:
        return default

    scores = {lang: 0 for lang in _VOCAB}
    if any(c in _TR_DIACRITICS for c in text):
        scores["tr"] += 2

    for w in words:
        for lang, word_set in _VOCAB.items():
            if w in word_set:
                scores[lang] += 3

    best_lang, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score > 0:
        return best_lang

    return default


def handle(req):
    kwargs = {}
    if req.get("sample"):
        kwargs["audio_prompt_path"] = req["sample"]
    if req.get("exaggeration") and "exaggeration" in _accepts:
        kwargs["exaggeration"] = float(req["exaggeration"])
    if req.get("cfg_weight") and "cfg_weight" in _accepts:
        kwargs["cfg_weight"] = float(req["cfg_weight"])

    # Cok dilli modelde her cumleyi kendi orijinal dilinde seslendir:
    # 'I\\'m listening' -> Ingilizce, 'Tamam' -> Turkce, 'こんにちは' -> Japonca
    if "language_id" in _accepts:
        req_lang = (req.get("language") or "").strip().lower()
        fallback = req_lang if req_lang and req_lang != "auto" else (_lang or "en")
        kwargs["language_id"] = _detect_sentence_language(req["text"], default=fallback)

    wav = _model.generate(req["text"], **kwargs)
    torchaudio.save(req["out"], wav, _model.sr)

    return {"path": req["out"], "device": _device, "variant": _variant, "language_id": kwargs.get("language_id")}
"""


class ChatterboxTTSProvider(TTSProvider):
    """Yerel, gerçekçi TTS + sıfır-atış ses klonlama."""

    @property
    def name(self) -> str:
        return "chatterbox"

    @property
    def display_name(self) -> str:
        return "Chatterbox (yerel, gerçekçi)"

    def is_available(self) -> bool:
        """Sidecar ortamı kurulu ve motor içinde mi?

        ASLA hata fırlatmaz — picker bunu çağırıyor ve bir istisna listeyi
        komple düşürürdü.
        """
        try:
            from fool import sidecar

            return sidecar.is_ready(SIDECAR_NAME, "chatterbox")
        except Exception:
            return False

    def list_voices(self) -> List[Dict[str, Any]]:
        """Chatterbox'ın sabit bir ses kataloğu yok — ses REFERANSTAN geliyor.

        Kullanıcının ``~/.fool/voices/`` altına koyduğu kayıtlar seçilebilir
        ses olarak listelenir; her biri sıfır-atış klonlama için referans.
        """
        voices: List[Dict[str, Any]] = [
            {"id": "default", "display": "Varsayılan (model sesi)", "language": "en"}
        ]

        try:
            from fool_constants import get_hermes_home

            voices_dir = get_hermes_home() / "voices"
            if voices_dir.is_dir():
                for path in sorted(voices_dir.iterdir()):
                    if path.suffix.lower() in {".wav", ".mp3", ".flac", ".ogg"}:
                        voices.append(
                            {
                                "id": str(path),
                                "display": f"{path.stem} (klonlanmış)",
                                "language": "*",
                            }
                        )
        except Exception as exc:  # pragma: no cover — listeleme asla çökmemeli
            logger.debug("[Chatterbox] ses listesi okunamadi: %s", exc)

        return voices

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Chatterbox",
            "badge": "yerel",
            "tag": "Gerçekçi + ses klonlama — CUDA'da hızlı",
            "env_vars": [],
        }

    def synthesize(
        self,
        text: str,
        output_path: str,
        *,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        speed: Optional[float] = None,
        format: str = "wav",
        **extra: Any,
    ) -> str:
        config = extra.get("config") or {}
        cfg = config.get("chatterbox") if isinstance(config, dict) else {}
        cfg = cfg if isinstance(cfg, dict) else {}


        # HAM tercih gonderiliyor, ``resolve()`` DEGIL.
        #
        # ``resolve()`` ana surecte ``cuda_available()`` soruyor ve ana ortamda
        # CUDA'li torch YOK -- yani her zaman False. Sonuc: kullanici "cuda"
        # secmis olsa bile istek "cpu" olarak sidecar'a gidiyordu ve motor,
        # kendi CUDA torch'u dururken CPU'da kosuyordu. Olculdu: Qwen'de 8,2 sn
        # yerine CUDA'da olmasi gereken sure.
        #
        # Karar sidecar'a ait: yetkili torch orada.
        device = str(cfg.get("device") or "auto").strip().lower()
        if device not in ("auto", "cpu", "cuda"):
            device = "auto"

        # BUG (measured directly): on Windows with no NVIDIA GPU, sending
        # "auto" through unresolved lets the sidecar's own
        # torch.cuda.is_available() run inside its process -- and on an
        # AMD/Intel integrated GPU that probe was observed taking the whole
        # backend down with a native crash (same STATUS_STACK_BUFFER_OVERRUN
        # class as SYSTRAN/faster-whisper#1293, fixed for the whisper path in
        # tools/transcription_tools.py). It reproduced ONLY through the
        # desktop app -- a bare `fool serve` never touches this code path
        # before a TTS request is made, so the crash-loop only showed up
        # once the GUI triggered a synthesis.
        #
        # This does not change the design above: an "auto"/"cuda" pick on a
        # machine that DOES have an NVIDIA GPU is still sent unresolved, so
        # the sidecar's own CUDA-enabled torch still decides. Only the
        # no-NVIDIA-on-Windows case is pinned to "cpu" here -- before the
        # sidecar ever imports torch -- and the check itself is a PATH
        # lookup (shutil.which), never a torch/CUDA call, so it carries none
        # of the crash risk it is guarding against.
        if (
            device in ("auto", "cuda")
            and platform.system() == "Windows"
            and shutil.which("nvidia-smi") is None
        ):
            device = "cpu"

        from fool import engine_host, sidecar

        if not sidecar.is_ready(SIDECAR_NAME, "chatterbox"):
            raise RuntimeError(
                "Chatterbox kurulu degil. Ayarlar > Voice altindan indirin."
            )

        # Ses referansı: açık `voice` argümanı > yapılandırma > yok.
        # "default" özel bir değer — modelin kendi sesi demek.
        sample = ""
        if voice and voice != "default" and os.path.isfile(voice):
            sample = voice
        elif isinstance(cfg.get("voice_sample"), str):
            candidate = os.path.expanduser(cfg["voice_sample"])
            if os.path.isfile(candidate):
                sample = candidate

        def _num(key: str) -> str:
            if key not in cfg:
                return ""
            try:
                return str(float(cfg[key]))
            except (TypeError, ValueError):
                logger.warning("[Chatterbox] gecersiz %s degeri, yok sayildi", key)
                return ""

        target = output_path
        if not target.lower().endswith(".wav"):
            target = os.path.splitext(output_path)[0] + ".wav"

        # Dil: yapilandirmadan gelir, bos birakilirsa STT yerel dili kontrol edilir
        # (orn. stt.local.language: tr). Hicbiri yoksa Ingilizce (turbo) yoluna duser.
        language = str(cfg.get("language") or "").strip().lower()
        if not language:
            stt_cfg = config.get("stt") if isinstance(config, dict) else {}
            stt_local = (stt_cfg.get("local") or {}) if isinstance(stt_cfg, dict) else {}
            stt_lang = stt_local.get("language") if isinstance(stt_local, dict) else None
            if not stt_lang and isinstance(config.get("language"), str):
                stt_lang = config.get("language")
            if isinstance(stt_lang, str) and stt_lang.strip().lower() in _SUPPORTED_LANGUAGES:
                language = stt_lang.strip().lower()

        if language and language not in _SUPPORTED_LANGUAGES:
            logger.warning(
                "[Chatterbox] desteklenmeyen dil %r yok sayildi; desteklenenler: %s",
                language,
                ", ".join(sorted(_SUPPORTED_LANGUAGES)),
            )
            language = ""

        result = engine_host.request(
            SIDECAR_NAME,
            _SETUP.replace("DEVICE", repr(device)).replace("LANG_ID", repr(language)),
            {
                "cfg_weight": _num("cfg_weight"),
                "exaggeration": _num("exaggeration"),
                "language": language,
                "out": target,
                "sample": sample,
                "text": text,
            },
        )


        logger.debug("[Chatterbox] %s uzerinde sentezlendi -> %s", result.get("device"), target)
        return target
        return output_path


def register(ctx) -> None:
    """Eklenti giriş noktası — sağlayıcıyı kayda ekler."""
    ctx.register_tts_provider(ChatterboxTTSProvider())
