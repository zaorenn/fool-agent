"""Kyutai TTS sağlayıcısı (kyutai/tts-1.6b-en_fr).

Neden bu model
--------------
Diğer motorlar METİN OKUMAK için tasarlandı; bu, canlı konuşma için
tasarlandı (Moshi ekibi). Farkı katalogdaki hız satırında değil, üretim
biçiminde: ses cümle bitmeden akmaya başlıyor. Jarvis kipinin ihtiyacı ifade
değil kesinlik ve düşük gecikme -- bu onun profili.

Bağımlılık ağacı adaylar arasında en yalını: Python 3.13'te 38 pakete
çözülüyor (StyleTTS 2 133, F5-TTS 148 -- ``uv`` ile ölçüldü). Yine de kendi
ortamında, çünkü torch sürümünü kendisi pinliyor.

Neden ``simple_generate``
-------------------------
Kütüphanenin akışlı arayüzü daha düşük gecikme verebiliyor ama farklı bir
sözleşme istiyor (parça parça geri çağrım). ``fool/engine_host.py`` protokolü
istek/cevap; akışı buraya sokmak protokolü değiştirmek demek. Şimdilik tek
seferlik üretim kullanılıyor ve dosya döndürülüyor -- akışlı yol ayrı bir iş.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
from typing import Any, Dict, List, Optional

from agent.tts_provider import TTSProvider

logger = logging.getLogger(__name__)

SIDECAR_NAME = "kyutai"

#: ``kyutai/tts-voices`` deposundaki sesler. Ad DOSYA YOLU -- depo icindeki
#: goreli konum.
_VOICES: tuple[tuple[str, str], ...] = (
    ("expresso/ex03-ex01_happy_001_channel1_334s.wav", "Neseli, canli"),
    ("expresso/ex03-ex02_narration_001_channel1_674s.wav", "Anlatici, sakin"),
    ("expresso/ex04-ex01_happy_001_channel1_334s.wav", "Neseli, ikinci konusmaci"),
)

DEFAULT_VOICE = _VOICES[0][0]

_SETUP = """
import os

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Triton'in resmi Windows surumu YOK ve model ``torch.compile`` kullaniyor:
# derleme acikken ilk sentez ``TritonMissing`` ile dusuyor (olculdu).
# Dynamo kapatiliyor -- motor calisiyor ama Triton'lu hizina ulasmiyor
# (bu makinede 2,37 sn; Linux'ta derlemeyle belirgin daha hizli olurdu).
# Ortam degiskeni torch ITHAL EDILMEDEN once ayarlanmali.
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")

import torch

torch._dynamo.config.suppress_errors = True

_device = "cuda" if (DEVICE == "auto" and torch.cuda.is_available()) else DEVICE
if _device == "cuda" and not torch.cuda.is_available():
    _device = "cpu"

from moshi.models.loaders import CheckpointInfo
from moshi.models.tts import DEFAULT_DSM_TTS_REPO, DEFAULT_DSM_TTS_VOICE_REPO, TTSModel

_model = None


def _ensure():
    global _model
    if _model is None:
        info = CheckpointInfo.from_hf_repo(DEFAULT_DSM_TTS_REPO)
        _model = TTSModel.from_checkpoint_info(
            info,
            voice_repo=DEFAULT_DSM_TTS_VOICE_REPO,
            device=_device,
        )
    return _model


def handle(req):
    import numpy as np
    import soundfile as sf

    model = _ensure()
    voice = req.get("voice") or VOICE_FALLBACK

    frames = model.simple_generate(
        req["text"], voice=voice, show_progress=False
    )

    # ``simple_generate`` tensor listesi donduruyor; tek dalgaya birlestirip
    # PCM_16 yaziyoruz -- butun motorlarin uzerinde anlastigi bicim
    # (oynatma yolu ve ``wave`` modulu onu bekliyor).
    wav = torch.cat([f.reshape(-1).float().cpu() for f in frames]).numpy()
    rate = int(getattr(model.mimi, "sample_rate", 24000))
    sf.write(req["out"], wav, rate, subtype="PCM_16")

    return {"path": req["out"], "device": _device, "sample_rate": rate}
"""


class KyutaiTTSProvider(TTSProvider):
    @property
    def name(self) -> str:
        return "kyutai"

    @property
    def display_name(self) -> str:
        return "Kyutai TTS"

    def is_available(self) -> bool:
        """ASLA hata fırlatmaz — picker bunu çağırıyor."""
        try:
            from fool import sidecar

            return sidecar.is_ready(SIDECAR_NAME, "moshi")
        except Exception:
            return False

    def list_voices(self) -> List[Dict[str, Any]]:
        return [
            {"id": voice_id, "name": voice_id.split("/")[-1], "description": description}
            for voice_id, description in _VOICES
        ]

    def default_voice(self) -> str:
        return DEFAULT_VOICE

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
        from fool import engine_host, sidecar

        if not sidecar.is_ready(SIDECAR_NAME, "moshi"):
            raise RuntimeError("Kyutai TTS kurulu degil. Ayarlar > Voice altindan indirin.")

        config = extra.get("config") or {}
        cfg = config.get("kyutai") if isinstance(config, dict) else {}
        cfg = cfg if isinstance(cfg, dict) else {}

        # HAM tercih gonderiliyor: ana ortamda CUDA'li torch YOK, yani burada
        # sorulan her soru "cpu" der ve motor kendi CUDA torch'u dururken
        # CPU'da kosardi. Karar sidecar'a ait.
        device = str(cfg.get("device") or "auto").strip().lower()
        if device not in ("auto", "cpu", "cuda"):
            device = "auto"

        # Windows + no NVIDIA GPU: same native-crash class as
        # SYSTRAN/faster-whisper#1293, fixed for whisper in
        # tools/transcription_tools.py and documented in full in
        # plugins/tts/fool-chatterbox/__init__.py. shutil.which is a PATH
        # lookup, never a torch/CUDA call -- it carries none of the risk
        # it is guarding against, and an actual NVIDIA machine is untouched
        # (device stays "auto"/"cuda", the sidecar's own torch still decides).
        if (
            device in ("auto", "cuda")
            and platform.system() == "Windows"
            and shutil.which("nvidia-smi") is None
        ):
            device = "cpu"

        selected = voice or cfg.get("voice") or DEFAULT_VOICE
        known = {voice_id for voice_id, _ in _VOICES}
        if selected not in known:
            logger.warning("[Kyutai] bilinmeyen ses %r, %s kullanilacak", selected, DEFAULT_VOICE)
            selected = DEFAULT_VOICE

        target = output_path
        if not target.lower().endswith(".wav"):
            target = os.path.splitext(output_path)[0] + ".wav"

        result = engine_host.request(
            SIDECAR_NAME,
            _SETUP.replace("DEVICE", repr(device)).replace(
                "VOICE_FALLBACK", repr(DEFAULT_VOICE)
            ),
            {"out": target, "text": text, "voice": selected},
        )

        logger.debug("[Kyutai] %s uzerinde sentezlendi -> %s", result.get("device"), target)
        return target


def register(ctx: Any) -> None:
    ctx.register_tts_provider(KyutaiTTSProvider())
