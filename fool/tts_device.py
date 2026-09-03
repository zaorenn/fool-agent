"""TTS motorları için birleşik cihaz seçimi (CUDA / CPU).

Sorun
-----
Upstream'de cihaz seçimi sağlayıcıdan sağlayıcıya farklıydı:

* Piper      ``use_cuda: true``      (bool)
* NeuTTS     ``device: "cpu"``       (string)
* diğerleri  hiç yok

Kullanıcı "TTS'i GPU'da çalıştır" demek istediğinde hangi sağlayıcıda hangi
anahtarı yazacağını bilemiyordu; üstelik CUDA yoksa ne olacağı da tanımsızdı.

Bu modül tek bir sözleşme sunar::

    device: auto | cuda | cpu

``auto`` (varsayılan) CUDA varsa onu, yoksa CPU'yu seçer. Sağlayıcıya özel
anahtarlar (``use_cuda``) hâlâ okunur — mevcut yapılandırmalar bozulmasın.

Neden ``auto`` varsayılan
-------------------------
Yanlış tarafa düşmenin iki maliyeti simetrik değil: CUDA varken CPU'ya düşmek
yalnızca yavaşlatır, CPU-only makinede CUDA'yı zorlamak ise **çalışmaz**.
Otomatik seçim, kullanıcının donanımını bilmeden doğru tarafa düşer.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Final, Literal

logger = logging.getLogger(__name__)

Device = Literal["cuda", "cpu"]

#: Geçerli yapılandırma değerleri.
VALID: Final[frozenset[str]] = frozenset({"auto", "cuda", "cpu"})

_cuda_available: bool | None = None


def cuda_available() -> bool:
    """CUDA gerçekten kullanılabilir mi? Süreç başına bir kez ölçülür.

    Sırayla dener: torch (Chatterbox/Qwen3 bunu kullanıyor), sonra
    onnxruntime (Piper bunu kullanıyor). İkisi de yoksa ``False``.
    """
    global _cuda_available
    if _cuda_available is not None:
        return _cuda_available

    # Kullanıcı açıkça kapatmışsa sorgulamaya hiç girme.
    if os.environ.get("FOOL_TTS_FORCE_CPU", "").strip().lower() in {"1", "true", "yes"}:
        _cuda_available = False
        return False

    try:
        import torch  # noqa: PLC0415 — isteğe bağlı, ağır import

        if torch.cuda.is_available():
            _cuda_available = True
            return True
    except Exception:  # pragma: no cover — torch yoksa ya da bozuksa
        pass

    try:
        import onnxruntime  # noqa: PLC0415

        if "CUDAExecutionProvider" in onnxruntime.get_available_providers():
            _cuda_available = True
            return True
    except Exception:  # pragma: no cover
        pass

    _cuda_available = False
    return False


def reset_cuda_probe() -> None:
    """Ölçüm önbelleğini sıfırla (testler için)."""
    global _cuda_available
    _cuda_available = None


def resolve(config: Any, *, provider: str = "") -> Device:
    """Yapılandırmadan gerçek cihazı çöz.

    ``config`` bir sağlayıcı yapılandırma sözlüğü (ör. ``tts.piper``).
    Okuma sırası:

    1. ``device: auto|cuda|cpu``  — yeni, birleşik anahtar
    2. ``use_cuda: bool``         — Piper'ın eski anahtarı (uyumluluk)
    3. ``auto``                   — varsayılan

    ``cuda`` istenmiş ama yoksa CPU'ya düşer ve BİR KEZ uyarır: sessizce
    düşmek, kullanıcının "GPU'yu neden kullanmıyor" sorusunu cevapsız bırakır.
    """
    cfg = config if isinstance(config, dict) else {}

    raw = cfg.get("device")
    if isinstance(raw, str) and raw.strip().lower() in VALID:
        want = raw.strip().lower()
    elif isinstance(cfg.get("use_cuda"), bool):
        want = "cuda" if cfg["use_cuda"] else "cpu"
    else:
        want = "auto"

    if want == "cpu":
        return "cpu"

    if want == "cuda":
        if cuda_available():
            return "cuda"
        logger.warning(
            "[TTS%s] device=cuda istendi ama CUDA bulunamadi; CPU'ya dusuluyor. "
            "GPU icin: torch (CUDA yapisi) ya da onnxruntime-gpu kurulu olmali.",
            f"/{provider}" if provider else "",
        )
        return "cpu"

    return "cuda" if cuda_available() else "cpu"


def describe() -> str:
    """Teşhis için tek satırlık durum."""
    return f"CUDA {'var' if cuda_available() else 'yok'}"
