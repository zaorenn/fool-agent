"""Qwen3-TTS sağlayıcısı (Alibaba, Apache-2.0).

Neden bu model
--------------
Kataloğun geri kalanı ağırlıklı olarak İngilizce'de iyi. Piper'ın sesleri dile
göre ayrı ayrı iniyor, Kokoro ve Chatterbox İngilizce ağırlıklı. Qwen3-TTS tek
model içinde 10 dil ve 9 konuşmacı taşıyor, tonlamayı da cümle bağlamına göre
kuruyor.

**Türkçe DESTEKLENMİYOR.** Modelin kendi ``get_supported_languages()``
çıktısından okundu: auto, chinese, english, french, german, italian, japanese,
korean, portuguese, russian, spanish. Bu, modeli isteyen kullanıcının ana dili
olduğu için panelde de açıkça yazılı — sessizce bozuk telaffuz üretmesindense
baştan söylemek doğru.

Neden AYRI bir ortamda çalışıyor
--------------------------------
``qwen-tts`` paketi ``transformers==4.57.3`` istiyor ve bu, ana ortamdaki
``huggingface-hub``ı 1.27.0'dan **0.36.2**'ye düşürüyor (ölçüldü, tahmin
değil). ``tools/lazy_deps.py`` hub'ın ``>=1.5.0`` kalması gerektiğini ve
altına inince Hindsight'ın açılışta çöktüğünü (#60783) açıkça yazıyor.
Ayrıca ``faster-whisper`` da aynı paketi paylaşıyor — yani Qwen'i ana ortama
kurmak kullanıcının ÇALIŞAN konuşma tanımasını bozardı.

Bu yüzden motor ``fool/sidecar.py`` üzerinden kendi sanal ortamına kuruluyor
ve buradan alt süreç olarak çağrılıyor. Ek fayda: motor çökerse ajan süreci
düşmüyor.

Neden eklenti, neden yerleşik değil
-----------------------------------
``agent/tts_provider.py`` ABC'si tam bunun için var. Eklenti olarak eklemek
upstream dosyalarına hiç dokunmamak demek — bu sağlayıcı ``git merge
upstream/main`` sırasında asla çakışmaz.

Yapılandırma::

    tts:
      provider: qwen3
      qwen3:
        device: auto          # auto | cuda | cpu
        voice: ryan           # bkz. list_voices()
        language: english     # auto | english | german | ...
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

#: Sidecar ortamının adı — ``fool/voice_models.py`` içindeki katalog
#: kimliğiyle AYNI olmak zorunda, yoksa panel "kurulu" derken sağlayıcı
#: ortamı bulamaz.
SIDECAR_NAME = "qwen3-tts"

#: Modelin GERCEK konusmaci kimlikleri — ``get_supported_speakers()``'tan
#: okundu, tahmin edilmedi. Yanlis bir ad modelde dogrulamadan geciyor ve
#: calisma aninda hata veriyor.
_VOICES: tuple[tuple[str, str], ...] = (
    ("ryan", "Dengeli erkek sesi — varsayılan"),
    ("serena", "Berrak kadın sesi"),
    ("aiden", "Genç erkek tonu"),
    ("dylan", "Alçak, sakin erkek"),
    ("eric", "Anlatı/sunum tonu"),
    ("vivian", "Sıcak kadın sesi"),
    ("ono_anna", "Japonca'da doğal kadın"),
    ("sohee", "Korece'de doğal kadın"),
    ("uncle_fu", "Çince'de olgun erkek"),
)

#: Modelin desteklediği diller. **Türkçe YOK** — kullanıcı Türkçe konuşuyor,
#: bu yüzden panelde de açıkça yazılı. Desteklenmeyen bir dil vermek sessizce
#: bozuk telaffuz üretirdi.
SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "auto", "chinese", "english", "french", "german",
    "italian", "japanese", "korean", "portuguese", "russian", "spanish",
)

DEFAULT_VOICE = "ryan"
#: 0.6B CustomVoice: hiz/kalite dengesi. 1.7B daha iyi ama CPU'da
#: kullanilamaz derecede yavas.
DEFAULT_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"

#: Alt süreçte çalışan sentez betiği.
#:
#: Neden dosya değil de gömülü dize: sidecar ortamının ``site-packages``ı
#: ayrı, ama betiğin kendisi bu paketle birlikte sürümlenmeli. Ayrı bir
#: dosyaya koymak, eklenti güncellendiğinde eski betiğin diskte kalması
#: riskini getirirdi.
#: Kalıcı motor sürecinin AÇILIŞ kodu.
#:
#: Model BİR KEZ yükleniyor. Önceki tasarımda her cümle için yeni bir süreç
#: açılıyor, torch içe aktarılıyor ve 2,4 GB'lık model diskten yeniden
#: yükleniyordu — bu Qwen'de en pahalı olan motordu.
_SETUP = """
import torch
from qwen_tts import Qwen3TTSModel
import soundfile as sf

# CUDA ``device_map`` ile veriliyor. ``.to(device)`` YOK: Qwen3TTSModel bir
# sarmalayici ve o metodu tasimiyor -- denenip dogrulandi.
# "auto" da CUDA'ya cozulmeli: yalnizca "cuda" esitligine bakmak, varsayilan
# ayarda modelin sessizce CPU'da kosmasi demekti -- olculdu, 8,2 sn.
_want = DEVICE
if _want == "auto":
    _want = "cuda" if torch.cuda.is_available() else "cpu"

_kwargs = {}
if _want == "cuda" and torch.cuda.is_available():
    _kwargs = {"device_map": "cuda:0", "dtype": torch.bfloat16}

_model = Qwen3TTSModel.from_pretrained(MODEL, **_kwargs)
_device = "cuda" if _kwargs else "cpu"


def handle(req):
    wavs, sample_rate = _model.generate_custom_voice(
        text=req["text"], speaker=req["speaker"], language=req.get("language") or None
    )
    sf.write(req["out"], wavs[0], sample_rate)

    return {"path": req["out"], "device": _device, "sample_rate": sample_rate}
"""


class Qwen3TTSProvider(TTSProvider):
    @property
    def name(self) -> str:
        return "qwen3"

    @property
    def display_name(self) -> str:
        return "Qwen3-TTS"

    def is_available(self) -> bool:
        """Sidecar ortamı kurulu ve motor içinde mi?

        ABC'nin sözleşmesi gereği ASLA yükselmez: bu çağrı seçicide ve
        ``fool setup``ta kullanılıyor ve orada bir istisna listeyi komple
        düşürürdü.
        """
        try:
            from fool import sidecar

            return sidecar.is_ready(SIDECAR_NAME, "qwen_tts")
        except Exception:
            return False

    def list_voices(self) -> List[Dict[str, Any]]:
        return [
            {"id": voice_id, "name": voice_id, "description": description}
            for voice_id, description in _VOICES
        ]

    def default_voice(self) -> str:
        return DEFAULT_VOICE

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"id": DEFAULT_MODEL, "name": "Qwen3-TTS 0.6B CustomVoice"},
            {"id": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", "name": "Qwen3-TTS 1.7B CustomVoice"},
        ]

    def default_model(self) -> str:
        return DEFAULT_MODEL

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

        if not sidecar.is_ready(SIDECAR_NAME, "qwen_tts"):
            raise RuntimeError(
                "Qwen3-TTS kurulu degil. Ayarlar > Voice altindan indirin."
            )

        config: Dict[str, Any] = extra.get("provider_config") or {}
        # HAM tercih gonderiliyor, ``resolve()`` DEGIL.
        #
        # ``resolve()`` ana surecte ``cuda_available()`` soruyor ve ana ortamda
        # CUDA'li torch YOK -- yani her zaman False. Sonuc: kullanici "cuda"
        # secmis olsa bile istek "cpu" olarak sidecar'a gidiyordu ve motor,
        # kendi CUDA torch'u dururken CPU'da kosuyordu. Olculdu: Qwen'de 8,2 sn
        # yerine CUDA'da olmasi gereken sure.
        #
        # Karar sidecar'a ait: yetkili torch orada.
        device = str(config.get("device") or "auto").strip().lower()
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

        # Model WAV yaziyor. Istenen bicim farkliysa uzantiyi zorlamak yerine
        # WAV'a yazip yolu oyle donduruyoruz: ABC "desteklenmiyorsa en yakinini
        # sec ve output_path'in uzantisi dogru olsun" diyor.
        target = output_path
        if not target.lower().endswith(".wav"):
            target = os.path.splitext(output_path)[0] + ".wav"

        # Dil verilmezse "auto": model kendi tespit ediyor. Desteklenmeyen
        # bir dili zorlamak sessizce bozuk telaffuz uretir, o yuzden listede
        # olmayan deger "auto"ya dusuruluyor.
        language = str(config.get("language") or extra.get("language") or "auto").lower()
        if language not in SUPPORTED_LANGUAGES:
            logger.warning("Qwen3-TTS %r dilini desteklemiyor; auto kullanilacak", language)
            language = "auto"

        # Bilinmeyen model kimligi HATA DEGIL, varsayilana dusus.
        #
        # Neden: cagiran katman bazen baska bir saglayicinin model adini
        # geciriyor ve transformers onu tanimayinca "Try: pip install
        # transformers -U" diyor -- kullanici icin tamamen anlamsiz bir mesaj
        # ve sesin neden cikmadigina dair hicbir ipucu yok.
        known = {entry["id"] for entry in self.list_models()}
        requested = model or DEFAULT_MODEL
        if requested not in known:
            logger.warning(
                "Qwen3-TTS %r modelini tanimiyor; %s kullanilacak", requested, DEFAULT_MODEL
            )
            requested = DEFAULT_MODEL

        setup = _SETUP.replace("DEVICE", repr(device)).replace("MODEL", repr(requested))
        result = engine_host.request(
            SIDECAR_NAME,
            setup,
            {"language": language, "out": target, "speaker": voice or DEFAULT_VOICE, "text": text},
        )

        logger.debug("Qwen3-TTS synthesized on %s -> %s", result.get("device"), target)
        return target


def register(ctx: Any) -> None:
    ctx.register_tts_provider(Qwen3TTSProvider())
