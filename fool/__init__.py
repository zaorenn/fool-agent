"""The Fool — upstream'in bilmediği, çakışmasız uzantı katmanı.

Bu paketteki hiçbir dosya ``NousResearch/hermes-agent`` içinde bulunmaz.
``git merge upstream/main`` bu dizine asla dokunamaz.

Alt modüller
------------
``branding``
    Marka kimliğinin tek kaynağı + metin dönüştürücü.
``skins/``
    ``the-fool.yaml`` — CLI, TUI ve masaüstü GUI'yi aynı anda temalayan skin.
``config/``
    Yerel model (LM Studio) varsayılanları.

@see docs/fool/ARCHITECTURE.md
@see docs/fool/SEAMS.md
"""

from fool import branding

__all__ = ["branding"]

# FOOL-SEAM: cuda-dlls
# CTranslate2 (faster-whisper) CUDA kutuphanelerini ``PATH``te ariyor ve
# pip onlari oraya koymuyor. Bu cagri OLMADAN Whisper sessizce CPU'da
# calisiyor: olculdu, 2,80 sn'lik kayit 15,16 sn suruyordu (CUDA'da 0,23).
# faster_whisper ithalinden ONCE kosmali; ``fool`` paketi her yerden
# ithal edildigi icin en erken guvenli nokta burasi.
try:
    from fool.cuda_runtime import enable as _enable_cuda_dlls

    _enable_cuda_dlls()
except Exception:  # pragma: no cover - hizlandirma, gereklilik degil
    pass
