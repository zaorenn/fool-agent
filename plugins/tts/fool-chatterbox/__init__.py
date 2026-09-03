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


def handle(req):
    kwargs = {}
    if req.get("sample"):
        kwargs["audio_prompt_path"] = req["sample"]
    if req.get("exaggeration") and "exaggeration" in _accepts:
        kwargs["exaggeration"] = float(req["exaggeration"])
    if req.get("cfg_weight") and "cfg_weight" in _accepts:
        kwargs["cfg_weight"] = float(req["cfg_weight"])
    # Cok dilli motorda ZORUNLU; tekdilli motorda parametre yok ve
    # gondermek TypeError ile sessizlige dusururdu.
    if _lang and "language_id" in _accepts:
        kwargs["language_id"] = _lang

    wav = _model.generate(req["text"], **kwargs)
    torchaudio.save(req["out"], wav, _model.sr)

    return {"path": req["out"], "device": _device, "variant": _variant}
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

        # Dil: yapilandirmadan gelir, bos birakilirsa Ingilizce (turbo) yol.
        # Desteklenmeyen bir kod SESSIZCE yok sayilmiyor -- yok sayilsaydi
        # kullanici Turkce secip Ingilizce fonetik duyar ve sebebini hicbir
        # yerden goremezdi.
        language = str(cfg.get("language") or "").strip().lower()
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
