"""CUDA sondasının sonucunu önbelleğe al — panel saniyelerce beklemesin.

Ölçülen hata
------------
``voice_models.catalog_status()`` her öğe için ``cuda_ready(entry)``
çağırıyor ve sidecar motorlarında bu, İZOLE bir yorumlayıcıda
``import torch`` demek. Tek ölçüm:

    kokoro      3,9 sn      chatterbox  4,4 sn
    styletts2   4,1 sn      qwen3-tts   5,2 sn

Katalog bunları SIRAYLA yapıyordu, yani ayarların ses bölümü her açılışta
15-20 saniye boş duruyordu. Kullanıcı bunu böyle bildirdi: "ayarlardaki ses
kısmı geç yükleniyor".

Neden sadece bellekte tutmak yetmiyor
-------------------------------------
Ağ geçidi bir süreç, panel başka bir pencere ve kullanıcı ayarları kapatıp
açıyor. Süreç ömrüne bağlı bir önbellek, yeniden başlatmadan sonra ilk
açılışta aynı beklemeyi geri getirirdi.

Ne zaman geçersiz oluyor
------------------------
Anahtar, sidecar'ın ``torch`` dizininin parmak izi (varlık + mtime + boyut).
Bir sürüm değişince, CUDA derlemesi CPU derlemesinin üstüne kurulunca ya da
ortam silinince parmak izi değişiyor ve sonda YENİDEN koşuyor. Bu bir
dosya sistemi ``stat``i -- alt süreç yok, ölçülemeyecek kadar ucuz.

Sürüm numarasına bakmak YETMEZDİ: ``torch`` 2.6.0 hem CPU hem CUDA
derlemesi olabiliyor ve ikisi aynı sürümü bildiriyor. ``install_cuda_runtime``
tam da bunu yapıyor -- aynı sürümün CUDA derlemesini kuruyor.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable

#: Süreçler arası önbellek tek dosyada; okuma/yazma kilit altında.
_LOCK = threading.Lock()

_MEMO: dict[str, tuple[str, bool]] = {}


def _cache_path() -> Path:
    from fool_constants import get_hermes_home

    return Path(get_hermes_home()) / "cache" / "cuda-probe.json"


def fingerprint(name: str) -> str:
    """Sidecar'ın torch kurulumunun parmak izi.

    Boş dize = ortam yok. O durumda önbelleğe hiç girilmiyor: sonda zaten
    anında ``False`` dönüyor ve saklanacak bir şey yok.
    """
    from fool import sidecar

    python = sidecar.sidecar_python(name)
    if not python.exists():
        return ""

    # ``site-packages/torch`` DIZINI: pip bir derlemeyi digeriyle degistirince
    # dizin yeniden yaziliyor ve mtime degisiyor. dist-info yerine paketin
    # kendisi bilerek -- CUDA derlemesi orada ~2 GB fark yaratiyor.
    base = sidecar.sidecar_dir(name)
    candidates = [
        base / "Lib" / "site-packages" / "torch",
        base / "lib" / "site-packages" / "torch",
    ]
    for lib in sorted(base.glob("lib/python*/site-packages/torch")):
        candidates.append(lib)

    for torch_dir in candidates:
        try:
            info = torch_dir.stat()
        except OSError:
            continue
        return f"{torch_dir}:{int(info.st_mtime)}:{info.st_size}"

    # torch yok ama ortam var: yorumlayicinin kendisi parmak izi olsun.
    try:
        info = python.stat()
    except OSError:
        return ""
    return f"{python}:{int(info.st_mtime)}"


def _load() -> dict[str, Any]:
    try:
        raw = json.loads(_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _store(data: dict[str, Any]) -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        # Onbellek yazilamadi: dogruluk etkilenmiyor, yalnizca yavaslik geri
        # geliyor. Kullaniciya hata gostermek burada oransiz olurdu.
        pass


def cached(name: str, probe: Callable[[], bool]) -> bool:
    """Parmak izi aynıysa saklanan cevabı ver, değilse sondayı koştur."""
    mark = fingerprint(name)
    if not mark:
        return probe()

    with _LOCK:
        hit = _MEMO.get(name)
        if hit is not None and hit[0] == mark:
            return hit[1]

        data = _load()
        row = data.get(name)
        if isinstance(row, dict) and row.get("mark") == mark:
            answer = bool(row.get("cuda"))
            _MEMO[name] = (mark, answer)
            return answer

    # Sonda KILIT DISINDA kosuyor: dakikalarca surebilen bir alt sureci
    # kilit altinda tutmak, ayni anda gelen her istegi de bloklardi.
    answer = probe()

    with _LOCK:
        _MEMO[name] = (mark, answer)
        data = _load()
        data[name] = {"cuda": answer, "mark": mark}
        _store(data)

    return answer


def invalidate(name: str = "") -> None:
    """Bir motorun (ya da tümünün) saklanan cevabını unut.

    Kurulum ve aygıt değişimi sonrası çağrılıyor: parmak izi zaten değişmiş
    OLMALI ama dosya sistemi zaman damgası çözünürlüğü düşük olabilir ve
    kurulumdan hemen sonra sorulan bir soru eski cevabı görebilirdi.
    """
    with _LOCK:
        if name:
            _MEMO.pop(name, None)
            data = _load()
            if data.pop(name, None) is not None:
                _store(data)
        else:
            _MEMO.clear()
            _store({})
