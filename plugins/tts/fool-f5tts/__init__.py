"""F5-TTS sağlayıcısı (flow matching, zero-shot ses klonlama).

Neden bu model
--------------
Diğer yerel motorlar SABİT seslerle geliyor. Bu, birkaç saniyelik bir referans
kayıttan ses klonluyor — "kendi sesimle konuşsun" ya da "şu sesi istiyorum"
isteğinin karşılığı. Flow matching kullandığı için yaptığı iş için hızlı.

Referans nereden geliyor
------------------------
Kullanıcı bir klon seçtiyse (``fool/voice_models.py`` klon mekanizması) o
kayıt kullanılıyor. Seçmediyse paketin kendi örnek kaydına düşülüyor —
motorun ÇALIŞMASI için bir referans şart ve kullanıcıyı ilk denemede
"önce ses yükle" duvarına çarptırmak yanlış.

Referans METNİ de gerekiyor: F5-TTS referansın ne söylediğini bilmek zorunda.
Paketin örneği için metin sabit ve bilinen; kullanıcının kendi klonunda boş
bırakılıyor ve model kaydı kendisi yazıya döküyor (daha yavaş ama doğru).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from agent.tts_provider import TTSProvider

logger = logging.getLogger(__name__)

SIDECAR_NAME = "f5-tts"

DEFAULT_VOICE = "default"

#: Paketin kendi ornek kaydinin METNI. F5-TTS referansin ne soyledigini
#: bilmek zorunda; bos birakmak modeli kaydi yaziya dokmeye zorluyor ve
#: her sentezi yavaslatiyor.
_BUNDLED_REF_TEXT = "Some call me nature, others call me mother nature."

_SETUP = """
import os
import pathlib
import site

import torch

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

_device = "cuda" if (DEVICE == "auto" and torch.cuda.is_available()) else DEVICE
if _device == "cuda" and not torch.cuda.is_available():
    _device = "cpu"

# ``torchcodec`` PAYLASILAN FFmpeg kutuphanelerine ihtiyac duyuyor
# (avcodec/avformat/avutil DLL'leri) ve yalnizca FFmpeg 4-7'yi destekliyor.
# Statik bir ffmpeg.exe YETMIYOR -- olculdu: bu makinede winget'ten gelen
# FFmpeg 9 statik derleme ve hic DLL yok, motor ham bir DLL yiginiyla
# dusuyordu. Kullaniciya NE eksik oldugunu soylemek gerekiyor.
try:
    import torchcodec  # noqa: F401
except Exception as _codec_err:
    raise RuntimeError(
        "F5-TTS needs shared FFmpeg libraries (avcodec/avformat/avutil, "
        "version 4-7) that torchcodec loads at import. A static ffmpeg.exe "
        "is not enough. Install a shared FFmpeg build and make sure its "
        f"DLLs are on PATH. Underlying error: {_codec_err}"
    ) from _codec_err

from f5_tts.api import F5TTS

_model = None


def _bundled_reference():
    # Paketin kendi ornek kaydi. ``f5_tts.__file__`` None (ad alani paketi),
    # o yuzden site-packages uzerinden bulunuyor.
    for root in site.getsitepackages():
        candidate = (
            pathlib.Path(root) / "f5_tts" / "infer" / "examples" / "basic" / "basic_ref_en.wav"
        )
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("F5-TTS ornek referans kaydi bulunamadi")


def _ensure():
    global _model
    if _model is None:
        _model = F5TTS(device=_device)
    return _model


def handle(req):
    model = _ensure()

    reference = req.get("reference") or _bundled_reference()
    ref_text = req.get("reference_text")
    if ref_text is None:
        ref_text = REF_TEXT if not req.get("reference") else ""

    model.infer(
        ref_file=reference,
        ref_text=ref_text,
        gen_text=req["text"],
        file_wave=req["out"],
        # ``nfe_step`` kalite/hiz dugmesi; 32 varsayilan.
        nfe_step=int(req.get("steps") or 32),
        speed=float(req.get("speed") or 1.0),
        show_info=lambda *a, **k: None,
    )

    return {"path": req["out"], "device": _device, "sample_rate": 24000}
"""


class F5TTSProvider(TTSProvider):
    @property
    def name(self) -> str:
        return "f5tts"

    @property
    def display_name(self) -> str:
        return "F5-TTS"

    def is_available(self) -> bool:
        """ASLA hata fırlatmaz — picker bunu çağırıyor."""
        try:
            from fool import sidecar

            return sidecar.is_ready(SIDECAR_NAME, "f5_tts")
        except Exception:
            return False

    def list_voices(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": DEFAULT_VOICE,
                "name": "Reference clip",
                "description": "Clones whichever clip you upload; falls back to a bundled sample.",
            }
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

        if not sidecar.is_ready(SIDECAR_NAME, "f5_tts"):
            raise RuntimeError("F5-TTS kurulu degil. Ayarlar > Voice altindan indirin.")

        config = extra.get("config") or {}
        cfg = config.get("f5tts") if isinstance(config, dict) else {}
        cfg = cfg if isinstance(cfg, dict) else {}

        # HAM tercih: karar sidecar'a ait, yetkili torch orada.
        device = str(cfg.get("device") or "auto").strip().lower()
        if device not in ("auto", "cpu", "cuda"):
            device = "auto"

        target = output_path
        if not target.lower().endswith(".wav"):
            target = os.path.splitext(output_path)[0] + ".wav"

        result = engine_host.request(
            SIDECAR_NAME,
            _SETUP.replace("DEVICE", repr(device)).replace("REF_TEXT", repr(_BUNDLED_REF_TEXT)),
            {
                "out": target,
                "reference": cfg.get("reference") or None,
                "reference_text": cfg.get("reference_text"),
                "speed": speed or 1.0,
                "steps": cfg.get("nfe_step") or 32,
                "text": text,
            },
        )

        logger.debug("[F5-TTS] %s uzerinde sentezlendi -> %s", result.get("device"), target)
        return target


def register(ctx: Any) -> None:
    ctx.register_tts_provider(F5TTSProvider())
