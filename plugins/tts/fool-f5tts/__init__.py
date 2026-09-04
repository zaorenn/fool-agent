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
import platform
import shutil
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

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

if os.name == "nt":
    import glob
    candidates = glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\\Microsoft\\WinGet\\Packages\\*FFmpeg*Shared*\\*\\bin"))
    for c in candidates:
        if os.path.isdir(c):
            try:
                os.add_dll_directory(c)
                os.environ["PATH"] = c + ";" + os.environ.get("PATH", "")
            except Exception:
                pass

import torch

_device = "cuda" if (DEVICE == "auto" and torch.cuda.is_available()) else DEVICE
if _device == "cuda" and not torch.cuda.is_available():
    _device = "cpu"

# torchaudio.load hook: soundfile is fast, robust, and doesn't fail on Windows
try:
    import soundfile as _sf
    import torchaudio as _ta

    def _safe_load(uri, *args, **kwargs):
        data, sr = _sf.read(uri, dtype="float32", always_2d=True)
        return torch.from_numpy(data.T), sr

    _ta.load = _safe_load
except Exception:
    pass

from f5_tts.api import F5TTS

_model = None


def _bundled_reference():
    for root in site.getsitepackages():
        for sub in ("", "Lib/site-packages"):
            candidate = (
                pathlib.Path(root) / sub / "f5_tts" / "infer" / "examples" / "basic" / "basic_ref_en.wav"
            )
            if candidate.exists():
                return str(candidate)
    try:
        import f5_tts
        for p in getattr(f5_tts, "__path__", []):
            cand = pathlib.Path(p) / "infer" / "examples" / "basic" / "basic_ref_en.wav"
            if cand.exists():
                return str(cand)
    except Exception:
        pass
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
        # ``nfe_step`` kalite/hiz dugmesi; 24 adim Turkce ve Ingilizce icin dengeli ve hizli.
        nfe_step=int(req.get("steps") or 24),
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

        target = output_path
        if not target.lower().endswith(".wav"):
            target = os.path.splitext(output_path)[0] + ".wav"

        # Referans dosyasi: voice argumani > yapilandirma
        reference = None
        if voice and voice != "default" and os.path.isfile(voice):
            reference = voice
        elif isinstance(cfg.get("reference"), str):
            candidate = os.path.expanduser(cfg["reference"])
            if os.path.isfile(candidate):
                reference = candidate

        # Hizli referans metni: Onceden cikartilmis metin yoksa yerel faster-whisper
        # ile bir kez yaziya dokulup yanina .txt olarak onbelleklenir. Boylece F5-TTS
        # alt sureci kendi icinde 1.6 GB'lik transformers whisper indirmek zorunda kalmaz.
        ref_text = cfg.get("reference_text")
        if not ref_text and reference and os.path.isfile(reference):
            txt_file = os.path.splitext(reference)[0] + ".txt"
            if os.path.isfile(txt_file):
                try:
                    with open(txt_file, "r", encoding="utf-8") as f:
                        ref_text = f.read().strip()
                except Exception:
                    pass
            if not ref_text:
                try:
                    from tools.transcription_tools import transcribe_audio
                    res = transcribe_audio(reference)
                    if res.get("success") and res.get("transcript"):
                        ref_text = res["transcript"].strip()
                        try:
                            with open(txt_file, "w", encoding="utf-8") as f:
                                f.write(ref_text)
                        except Exception:
                            pass
                except Exception:
                    pass

        result = engine_host.request(
            SIDECAR_NAME,
            _SETUP.replace("DEVICE", repr(device)).replace("REF_TEXT", repr(_BUNDLED_REF_TEXT)),
            {
                "out": target,
                "reference": reference,
                "reference_text": ref_text,
                "speed": speed or 1.0,
                "steps": cfg.get("nfe_step") or 24,
                "text": text,
            },
        )

        logger.debug("[F5-TTS] %s uzerinde sentezlendi -> %s", result.get("device"), target)
        return target


def register(ctx: Any) -> None:
    ctx.register_tts_provider(F5TTSProvider())
