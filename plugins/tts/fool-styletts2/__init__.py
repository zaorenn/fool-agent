"""StyleTTS 2 sağlayıcısı (MIT).

Neden bu model
--------------
Yerel TTS'te Piper hız ucunda ama robotik, Chatterbox gerçekçilik ucunda ama
ağır. Kokoro ikisinin arasında ve hızlı, ama tonlaması hâlâ sınırlı.
StyleTTS 2 autoregressive DEĞİL: uzun cümlede kayma/tekrar üretmiyor ve
prozodisi belirgin daha doğal.

Bu makinede ölçüldü (RTX 4070 Ti SUPER, kısa cümle, sidecar'da CUDA torch):

    model yükleme : 5,04 sn   (süreç ömründe bir kez)
    ilk sentez    : 7,00 sn
    2. sentez     : 0,61 sn
    3. sentez     : 0,42 sn

Karşılaştırma için Kokoro ısınmış 0,14 sn. StyleTTS 2 üç kat yavaş ama hâlâ
gerçek zamanın çok altında -- ve ses kalitesi farkı orada.

Entegrasyonun ÜÇ tuzağı (hepsi ölçülerek bulundu)
-------------------------------------------------
1. **stdout kirliliği.** Kütüphane her sentezde ürettiği IPA fonemlerini
   ``print`` ediyor. ``fool/engine_host.py`` protokolü stdout'u JSON için
   kullanıyor, yani bu satırlar protokolü BOZAR. Çıkarım sırasında stdout
   yutuluyor.
2. **``torch.load``.** Paket 2024'ten ve torch 2.6+ ``weights_only=True``
   varsayılanıyla kontrol noktasını okuyamıyor. Yalnızca yükleme sırasında
   eski davranışa dönülüyor -- ağırlıklar modelin kendi deposundan.
3. **cp1254.** Windows konsolu IPA karakterlerini kodlayamıyor ve süreç
   ``UnicodeEncodeError`` ile düşüyordu. Alt süreç UTF-8'e sabitleniyor.

NLTK ``punkt_tab`` verisi kurulumdan sonra bir kez indiriliyor; olmadan ilk
sentez anlaşılmaz bir hatayla düşüyor (Kokoro'nun spaCy modeliyle aynı sınıf).
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
from typing import Any, Dict, List, Optional

from agent.tts_provider import TTSProvider

logger = logging.getLogger(__name__)

#: Sidecar ortamının adı — ``fool/voice_models.py`` katalog kimliğiyle AYNI.
SIDECAR_NAME = "styletts2"

#: StyleTTS 2 tek bir varsayılan sesle geliyor; farklı ses REFERANS KAYITTAN
#: klonlanıyor (``target_voice_path``). Ses klonlama akışı katalogdaki
#: ``clone`` mekanizmasıyla aynı yerden besleniyor.
DEFAULT_VOICE = "default"

#: Kalıcı motor sürecinin AÇILIŞ kodu. Model burada BİR KEZ yükleniyor.
_SETUP = """
import contextlib
import io
import os

import torch

# Windows konsolu (cp1254) IPA karakterlerini kodlayamiyor ve kutuphane
# onlari basiyor -- surec UnicodeEncodeError ile dusuyordu.
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# torch 2.6+ ``weights_only=True`` varsayiliyor; paket 2024'ten ve kontrol
# noktasi duz tensor degil. Agirliklar modelin KENDI deposundan geliyor.
_orig_load = torch.load
torch.load = lambda *a, **k: _orig_load(*a, **{**k, "weights_only": False})

from styletts2 import tts as _tts

_device = "cuda" if (DEVICE == "auto" and torch.cuda.is_available()) else DEVICE
if _device == "cuda" and not torch.cuda.is_available():
    _device = "cpu"

# Kutuphane cihazi kendi seciyor; zorlamak icin gorunur kartlari kisitliyoruz.
if _device == "cpu":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

_model = None


def _ensure_nltk():
    # ``punkt_tab`` olmadan ILK sentez anlasilmaz bir hatayla dusuyor.
    #
    # Kurulum adimi olarak degil BURADA yapiliyor: veri bir tekerlek
    # degil ve katalogun ``sidecar_wheels`` mekanizmasina girmiyor.
    # Kendi kendine iyilesen bir kontrol, kullanicinin gormedigi bir
    # kurulum adimindan saglam.
    import nltk

    try:
        nltk.data.find("tokenizers/punkt_tab")
        return
    except LookupError:
        pass

    with contextlib.redirect_stdout(io.StringIO()):
        nltk.download("punkt_tab", quiet=True)


def _ensure():
    global _model
    if _model is None:
        _ensure_nltk()
        # Yukleme de basiyor -- ayni yutma burada da gerekli.
        with contextlib.redirect_stdout(io.StringIO()):
            _model = _tts.StyleTTS2()
    return _model


def handle(req):
    model = _ensure()
    reference = req.get("reference") or None

    # KRITIK: kutuphane her sentezde IPA fonemlerini stdout'a basiyor ve
    # engine_host protokolu stdout'u JSON icin kullaniyor. Yutulmazsa
    # protokol bozuluyor.
    with contextlib.redirect_stdout(io.StringIO()):
        model.inference(
            req["text"],
            target_voice_path=reference,
            output_wav_file=req["out"],
            diffusion_steps=int(req.get("steps") or 5),
            embedding_scale=float(req.get("expressiveness") or 1.0),
        )

    # Kutuphane float32 WAV yaziyor; diger butun motorlar PCM_16 uretiyor
    # ve oynatma yolu ile ``wave`` modulu onu bekliyor (olculdu: sure
    # okumasi "unknown format: 3" ile dusuyordu). Bicim burada tekillesiyor.
    import soundfile as _sf

    _data, _rate = _sf.read(req["out"], dtype="float32")
    _sf.write(req["out"], _data, _rate, subtype="PCM_16")

    return {"path": req["out"], "device": _device, "sample_rate": _rate}
"""


class StyleTTS2Provider(TTSProvider):
    @property
    def name(self) -> str:
        return "styletts2"

    @property
    def display_name(self) -> str:
        return "StyleTTS 2"

    def is_available(self) -> bool:
        """ASLA hata fırlatmaz — picker bunu çağırıyor."""
        try:
            from fool import sidecar

            return sidecar.is_ready(SIDECAR_NAME, "styletts2")
        except Exception:
            return False

    def list_voices(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": DEFAULT_VOICE,
                "name": "Default",
                "description": "Built-in voice. Drop a reference clip in to clone another.",
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

        if not sidecar.is_ready(SIDECAR_NAME, "styletts2"):
            raise RuntimeError(
                "StyleTTS 2 kurulu degil. Ayarlar > Voice altindan indirin."
            )

        config = extra.get("config") or {}
        cfg = config.get("styletts2") if isinstance(config, dict) else {}
        cfg = cfg if isinstance(cfg, dict) else {}

        # HAM tercih gonderiliyor, cozulmus DEGIL: ana ortamda CUDA'li torch
        # YOK, yani burada sorulan her soru "cpu" cevabini verir ve motor
        # kendi CUDA torch'u dururken CPU'da kosardi. Karar sidecar'a ait.
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

        result = engine_host.request(
            SIDECAR_NAME,
            _SETUP.replace("DEVICE", repr(device)),
            {
                "expressiveness": cfg.get("expressiveness") or 1.0,
                "out": target,
                # Klonlama icin referans kayit; yoksa yerlesik ses.
                "reference": cfg.get("reference") or None,
                # ``diffusion_steps`` kalite/hiz dugmesi. 5 varsayilan;
                # dusurmek hizlandiriyor, prozodiyi duzlestiriyor.
                "steps": cfg.get("diffusion_steps") or 5,
                "text": text,
            },
        )

        logger.debug("[StyleTTS2] %s uzerinde sentezlendi -> %s", result.get("device"), target)
        return target


def register(ctx: Any) -> None:
    ctx.register_tts_provider(StyleTTS2Provider())
