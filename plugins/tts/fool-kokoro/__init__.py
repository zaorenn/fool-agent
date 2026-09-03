"""Kokoro TTS sağlayıcısı (hexgrad, Apache-2.0).

Neden bu var
------------
Kokoro ses modeli kataloğunda zaten listeleniyordu ama **hiçbir sağlayıcısı
yoktu**. Yani indirilebiliyor, panel "Installed" diyordu ve ajan onu asla
kullanamıyordu — kullanıcıya hiçbir hata da görünmüyordu. Sessiz başarı,
görünür hatadan çok daha kötü; bu dosya o boşluğu kapatıyor.

Neden bu model
--------------
Yerel TTS'te Piper hız ucunda ama robotik, Chatterbox gerçekçilik ucunda ama
2 GB ve CUDA istiyor. Kokoro ikisinin arasında: 82M parametre, ~350 MB, CPU'da
kullanılabilir hızda ve tonlaması Piper'dan belirgin biçimde iyi.

Neden AYRI bir ortamda çalışıyor
--------------------------------
``kokoro`` ana ortamda ``tokenizers``ı geriye düşürüyor — o paket
``faster-whisper`` ile paylaşılıyor. Ölçüldü, tahmin değil. Motor bu yüzden
``fool/sidecar.py`` üzerinden kendi sanal ortamına kuruluyor ve buradan alt
süreç olarak çağrılıyor.

Yapılandırma::

    tts:
      provider: kokoro
      kokoro:
        device: auto          # auto | cuda | cpu
        voice: af_heart       # bkz. list_voices()
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from agent.tts_provider import TTSProvider

logger = logging.getLogger(__name__)

#: Sidecar ortamının adı — ``fool/voice_models.py`` katalog kimliğiyle AYNI.
SIDECAR_NAME = "kokoro"

#: Kokoro'nun ses kimlikleri. Önek dili ve cinsiyeti kodluyor:
#: ``a``=Amerikan, ``b``=İngiliz; ``f``=kadın, ``m``=erkek.
_VOICES: tuple[tuple[str, str], ...] = (
    ("af_heart", "Amerikan kadın — sıcak, varsayılan"),
    ("af_bella", "Amerikan kadın — berrak"),
    ("af_nicole", "Amerikan kadın — yumuşak"),
    ("am_michael", "Amerikan erkek — dengeli"),
    ("am_puck", "Amerikan erkek — canlı"),
    ("bf_emma", "İngiliz kadın"),
    ("bm_george", "İngiliz erkek"),
)

DEFAULT_VOICE = "af_heart"

#: Kalıcı motor sürecinin AÇILIŞ kodu.
#:
#: Model burada BİR KEZ yükleniyor ve süreç açık kaldığı sürece bellekte
#: kalıyor. Önceki tasarımda her cümle için yeni bir süreç açılıyor, torch
#: içe aktarılıyor ve model diskten yeniden yükleniyordu — ölçüldü: beş
#: kelime için 48,7 sn.
_SETUP = """
import numpy as np
import soundfile as sf
import torch
from kokoro import KPipeline

_device = "cuda" if (DEVICE == "auto" and torch.cuda.is_available()) else DEVICE
if _device == "cuda" and not torch.cuda.is_available():
    _device = "cpu"

# lang_code sesin ilk harfinden geliyor: 'a' Amerikan, 'b' Ingiliz. Farkli
# harfli bir ses istendiginde boru hattinin yeniden kurulmasi gerekiyor, o
# yuzden harf basina onbellege aliniyor.
_pipelines = {}


def _pipeline(voice):
    code = voice[0]
    if code not in _pipelines:
        _pipelines[code] = KPipeline(lang_code=code, device=_device)
    return _pipelines[code]


def handle(req):
    chunks = []
    for _, _, audio in _pipeline(req["voice"])(
        req["text"], voice=req["voice"], speed=float(req.get("speed") or 1.0)
    ):
        chunks.append(audio)

    if not chunks:
        raise RuntimeError("kokoro ses uretmedi")

    wav = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
    sf.write(req["out"], wav, 24000)

    return {"path": req["out"], "device": _device, "sample_rate": 24000}
"""


class KokoroTTSProvider(TTSProvider):
    @property
    def name(self) -> str:
        return "kokoro"

    @property
    def display_name(self) -> str:
        return "Kokoro"

    def is_available(self) -> bool:
        """ASLA hata fırlatmaz — picker bunu çağırıyor."""
        try:
            from fool import sidecar

            return sidecar.is_ready(SIDECAR_NAME, "kokoro")
        except Exception:
            return False

    def list_voices(self) -> List[Dict[str, Any]]:
        return [
            {"id": voice_id, "name": voice_id, "description": description}
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
        from fool import engine_host

        from fool import sidecar

        if not sidecar.is_ready(SIDECAR_NAME, "kokoro"):
            raise RuntimeError("Kokoro kurulu degil. Ayarlar > Voice altindan indirin.")

        config = extra.get("config") or {}
        cfg = config.get("kokoro") if isinstance(config, dict) else {}
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

        selected = voice or cfg.get("voice") or DEFAULT_VOICE
        known = {voice_id for voice_id, _ in _VOICES}
        if selected not in known:
            # Bilinmeyen ses adı Kokoro'da anlaşılmaz bir hataya yol açıyor;
            # varsayılana düşüp UYARMAK sessizce çökmekten iyi.
            logger.warning("[Kokoro] bilinmeyen ses %r, %s kullanilacak", selected, DEFAULT_VOICE)
            selected = DEFAULT_VOICE

        target = output_path
        if not target.lower().endswith(".wav"):
            target = os.path.splitext(output_path)[0] + ".wav"

        result = engine_host.request(
            SIDECAR_NAME,
            _SETUP.replace("DEVICE", repr(device)),
            {"out": target, "speed": speed or 1.0, "text": text, "voice": selected},
        )

        logger.debug("[Kokoro] %s uzerinde sentezlendi -> %s", result.get("device"), target)
        return target


def register(ctx: Any) -> None:
    ctx.register_tts_provider(KokoroTTSProvider())
