r"""Motor DİSKTE kurulu ile motor ÇALIŞIYOR ayrı şeyler.

Ölçülen hata
------------
``voice_models.status()`` bir motoru "kurulu" sayarken
``sidecar.is_ready()``ye soruyor, o da ``importlib.util.find_spec`` kullanıyor
-- yani modülün diskte VAR OLUP OLMADIĞINA bakıyor, içe aktarılıp
aktarılamadığına değil. F5-TTS bu makinede tam olarak o boşluğa düşüyordu:

    find_spec("f5_tts")   -> True     <- panelin gördüğü
    import torchcodec     -> OSError  <- sentezin gördüğü

    FileNotFoundError: Could not find module
    ...	orchcodec\libtorchcodec_core8.dll (or one of its dependencies)

torchcodec 0.15.0 beş sürüm için DLL taşıyor (core4..core8) ve her biri
PAYLAŞILAN FFmpeg kütüphanelerini (avcodec/avformat/avutil) yüklüyor. Bu
makinede statik bir FFmpeg 9 var ve hiç DLL taşımıyor, yani beşi de düşüyor.

Sonucu kullanıcı için şuydu: panel F5-TTS'i "installed" ve "klonlanabilir"
gösteriyor, kullanıcı bir ses kaydı yükleyip klon seçiyor ve HİÇBİR ŞEY
duymuyor. Sessiz başarısızlığın en pahalı hâli -- kullanıcı yaptığı işin
boşa gittiğini bile bilmiyor.

Neden ayrı bir sonda
--------------------
``find_spec``i gerçek bir ``import``la değiştirmek doğru cevabı verirdi ama
maliyeti ödenemez: sidecar'da ``import f5_tts.api`` demek torch yüklemek
demek ve ölçüldü, motor başına 4-5 saniye (bkz. ``fool/cuda_probe_cache.py``).
Katalog soğuk 1,25 sn / sıcak 0,14 sn; buna dokuz kez 4 saniye eklemek paneli
kullanılamaz hâle getirirdi.

Bunun yerine motor, gerçekten içe aktarılması gereken AYIRT EDİCİ modülü
kendisi bildiriyor (``VoiceEntry.runtime_imports``). F5-TTS için bu
``torchcodec``: ölçüldü, 0,9 sn -- çünkü DLL yüklemede zaten düşüyor, torch
grafiğini hiç kurmuyor. Sonuç ``cuda-probe`` ile aynı parmak izi mantığıyla
diske yazılıyor, yani bedel motor kurulumu başına bir kez ödeniyor.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

#: Sonda alt sürecine verilen süre. Ölçüldü: f5-tts'in ``import torchcodec``ı
#: 0,9 sn'de DÜŞÜYOR, sağlıklı bir motorda ise saniyeler sürebiliyor. 60 sn
#: fazlasıyla geniş; asılı kalan bir sondanın paneli süresiz bekletmemesi için
#: var, normal yolu kısıtlamak için değil.
_TIMEOUT_SECONDS = 60

_LOCK = threading.Lock()

#: Süreç içi bellek: aynı parmak izi için diske bile gitmeyelim.
_MEMO: dict[str, tuple[str, str]] = {}


def _cache_path() -> Path:
    from fool_constants import get_hermes_home

    return Path(get_hermes_home()) / "cache" / "engine-health.json"


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
        # Önbellek yazılamadı: doğruluk etkilenmiyor, yalnızca yavaşlık geri
        # geliyor. Bir önbellek uğruna panele hata göstermek oransız olurdu.
        pass


def _probe_source(modules: tuple[str, ...]) -> str:
    """Alt süreçte koşan parça: modülleri GERÇEKTEN içe aktar.

    Hata metni ``stderr``e değil ``stdout``a yazılıyor ve tek satıra
    indirgeniyor: çağıran taraf onu doğrudan panele koyuyor.
    """
    return (
        "import sys\n"
        f"for name in {list(modules)!r}:\n"
        "    try:\n"
        "        __import__(name)\n"
        "    except BaseException as exc:\n"
        "        first = str(exc).strip().splitlines()\n"
        "        detail = first[0] if first else type(exc).__name__\n"
        "        sys.stdout.write(name + ': ' + detail)\n"
        "        raise SystemExit(1)\n"
        "raise SystemExit(0)\n"
    )


def _interpreter(entry: Any) -> Path | None:
    """Motorun gerçekten koştuğu yorumlayıcı.

    Sidecar'lı motorda ANA ortam yanlış cevap verir: paket orada hiç yok.
    """
    from fool import sidecar

    if getattr(entry, "sidecar_specs", ()):
        python = sidecar.sidecar_python(entry.id)
        return python if python.exists() else None

    import sys

    return Path(sys.executable)


def _run_probe(entry: Any, modules: tuple[str, ...]) -> str:
    """``""`` = sağlıklı. Aksi hâlde kullanıcıya gösterilecek tek satır."""
    python = _interpreter(entry)
    if python is None:
        return ""

    env = dict(os.environ)
    if os.name == "nt":
        import glob
        for c in glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*FFmpeg*Shared*\*\bin")):
            if os.path.isdir(c) and c not in env.get("PATH", ""):
                env["PATH"] = c + ";" + env.get("PATH", "")
    # Konsol cp1254 IPA/UTF-8 karakterlerinde patlıyor ve sondanın kendisi
    # sahte bir hata üretiyordu.
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        completed = subprocess.run(
            [str(python), "-c", _probe_source(modules)],
            capture_output=True,
            text=True,
            # ``stdin`` AÇIKÇA veriliyor: verilmezse alt süreç Windows'ta
            # devralınan bir tanıtıcıyla asılı kalabiliyor.
            stdin=subprocess.DEVNULL,
            env=env,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "engine probe timed out"
    except (OSError, subprocess.SubprocessError) as exc:
        # Sondanın kendisi koşamadıysa motoru SAĞLIKSIZ ilan etmiyoruz:
        # bilmiyoruz, ve çalışan bir motoru bozuk göstermek daha kötü.
        del exc
        return ""

    if completed.returncode == 0:
        return ""
    return (completed.stdout or "").strip() or "engine failed to load"


def error_for(entry: Any) -> str:
    """Bu motor çalışmayacaksa NE YAPILACAĞINI söyleyen cümle, yoksa ``""``.

    Ham istisna metni bilerek KULLANILMIYOR. Ölçüldü: torchcodec'in ilk
    satırı ``Could not load libtorchcodec. Likely causes:`` -- panelde tek
    başına hiçbir işe yaramıyor, asıl bilgi 30 satır aşağıda. Motor kendi
    çaresini ``runtime_help`` ile söylüyor; o yoksa ham satıra düşülüyor,
    çünkü belirsiz bir hata bile sessizlikten iyidir.

    Sonuç parmak iziyle önbelleklenir (bkz. ``fool/cuda_probe_cache.py``):
    motor yeniden kurulunca ya da torch derlemesi değişince sonda yeniden
    koşar.
    """
    modules = tuple(getattr(entry, "runtime_imports", ()) or ())
    if not modules:
        return ""

    from fool import cuda_probe_cache

    mark = cuda_probe_cache.fingerprint(entry.id)
    if not mark:
        # Ortam yok: "kurulu değil" zaten ayrı bir durum, sağlık sorusu
        # anlamsız.
        return ""

    with _LOCK:
        hit = _MEMO.get(entry.id)
        if hit is not None and hit[0] == mark:
            return hit[1]

        row = _load().get(entry.id)
        if isinstance(row, dict) and row.get("mark") == mark:
            answer = str(row.get("error") or "")
            _MEMO[entry.id] = (mark, answer)
            return answer

    # Sonda KİLİT DIŞINDA: alt süreç beklemesini kilit altında tutmak aynı
    # anda gelen her katalog isteğini de bloklardı.
    raw = _run_probe(entry, modules)
    answer = (str(getattr(entry, "runtime_help", "") or "").strip() or raw) if raw else ""

    with _LOCK:
        _MEMO[entry.id] = (mark, answer)
        data = _load()
        data[entry.id] = {"error": answer, "mark": mark}
        _store(data)

    return answer


def invalidate(entry_id: str = "") -> None:
    """Saklanan cevabı unut. Kurulum sonrası çağrılıyor."""
    with _LOCK:
        if entry_id:
            _MEMO.pop(entry_id, None)
            data = _load()
            if data.pop(entry_id, None) is not None:
                _store(data)
        else:
            _MEMO.clear()
            _store({})
