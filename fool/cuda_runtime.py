"""CTranslate2/faster-whisper için CUDA kütüphanelerini bulunur kılar.

Neden bu var
------------
Whisper CPU'da çalışıyordu ve kimse söylemiyordu. Ölçüldü: 2,80 saniyelik bir
kaydı yazıya dökmek **15,16 saniye** sürüyordu — gerçek zamanın beş katı yavaş.
Kullanıcının RTX 4070 Ti'ı bu sırada boştaydı.

Sebep tek bir DLL: CTranslate2 ``cublas64_12.dll``i yükleyemiyor ve
``device="cuda"`` isteğini şu hatayla reddediyor::

    RuntimeError: Library cublas64_12.dll is not found or cannot be loaded

Kütüphaneler aslında ``nvidia-cublas-cu12`` / ``nvidia-cudnn-cu12`` paketleriyle
``site-packages/nvidia/*/bin`` altına kuruluyor, ama Windows oraya bakmıyor:
DLL arama yolu ``PATH``e ya da ``os.add_dll_directory``ye bağlı ve pip hiçbirini
ayarlamıyor. Yani paketler kurulu olsa bile CUDA çalışmıyor.

Ölçülen fark (2,80 sn'lik kayıt, large-v3-turbo)::

    CPU  / int8      15,16 sn   (0,2x gerçek zaman)
    CUDA / float16    0,23 sn   (12x gerçek zaman)

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import logging
import os
import site
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_APPLIED = False


def _candidate_dirs() -> list[Path]:
    """``site-packages/nvidia/*/bin`` dizinleri.

    ``sys.prefix`` de taranıyor: sanal ortamlarda ``getsitepackages()`` bazı
    kurulumlarda ortamın kendi dizinini atlıyor.
    """
    roots: list[str] = []
    try:
        roots.extend(site.getsitepackages())
    except AttributeError:
        # Bazı gömülü dağıtımlarda yok.
        pass
    roots.append(os.path.join(sys.prefix, "Lib", "site-packages"))

    found: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        nvidia = Path(root) / "nvidia"
        if not nvidia.is_dir():
            continue
        for bin_dir in nvidia.glob("*/bin"):
            key = str(bin_dir).lower()
            if bin_dir.is_dir() and key not in seen:
                seen.add(key)
                found.append(bin_dir)
    return found


def enable() -> bool:
    """CUDA kütüphanelerini bulunur kıl. En fazla bir kez iş yapar.

    ASLA yükselmez: bu bir hızlandırma, bir gereklilik değil. Başarısız olursa
    motor CPU'da çalışmaya devam eder — yavaş ama çalışır.
    """
    global _APPLIED

    if _APPLIED or os.name != "nt":
        return _APPLIED

    # Govde komple sarmalanmis: bu bir HIZLANDIRMA, gereklilik degil. Disk
    # hatasi, bozuk bir site-packages, okunamayan bir dizin -- hicbiri
    # uygulamayi dusurmemeli. Basarisiz olursa motor CPU'da calisir: yavas
    # ama calisir.
    try:
        dirs = _candidate_dirs()
    except Exception:
        return False

    if not dirs:
        return False

    # HER İKİSİ de gerekiyor: ``add_dll_directory`` bu sürecin doğrudan
    # yüklemeleri için, ``PATH`` ise CTranslate2'nin kendi alt yükleyicisi için.
    # Yalnızca birini yapmak bazı sürümlerde çalışıp bazılarında çalışmıyor.
    for bin_dir in dirs:
        try:
            os.add_dll_directory(str(bin_dir))
        except (AttributeError, OSError):
            pass

    try:
        current = os.environ.get("PATH", "")
        parts = current.split(os.pathsep)
        missing = [str(d) for d in dirs if str(d) not in parts]
        if missing:
            os.environ["PATH"] = (
                os.pathsep.join([*missing, current]) if current else os.pathsep.join(missing)
            )
    except Exception:
        return False

    _APPLIED = True
    logger.debug("CUDA kutuphaneleri bulunur kilindi: %s", ", ".join(str(d) for d in dirs))

    return True
