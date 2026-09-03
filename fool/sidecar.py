"""Ağır ses motorları için izole Python ortamları.

Neden bu var
------------
Üç TTS motorunun üçü de ana ortamı bozuyor. Ölçüldü, tahmin değil:

===============  ==========================================================
Motor            Ana ortamda ne kırıyor
===============  ==========================================================
``qwen-tts``     ``transformers==4.57.3`` üzerinden ``huggingface-hub``ı
                 1.27.0 → **0.36.2**'ye düşürüyor. ``tools/lazy_deps.py``
                 hub'ın ``>=1.5.0`` kalması gerektiğini ve altına inince
                 Hindsight'ın açılışta çöktüğünü (#60783) yazıyor.
``chatterbox``   ``starlette``ı 1.3.1'in altına düşürüyor — o pin bir CVE
                 düzeltmesi (CVE-2026-48710). Yani güvenlik gerilemesi.
``kokoro``       ``tokenizers``ı düşürüyor (görece zararsız ama yine de
                 paylaşılan bir paket).
===============  ==========================================================

Üç ayrı özel durum yerine tek bir çözüm: her motor KENDİ sanal ortamına
kuruluyor. Ana ortam hiç değişmiyor, motorlar birbirinin sürümüyle de
kavga etmiyor. Bedeli disk alanı — bir TTS motoru zaten yüzlerce MB, ayrı
bir ``torch`` kopyası bunu katlıyor. Bu bedel bilerek kabul edildi:
kullanıcının çalışan STT'sini ve bir CVE düzeltmesini bozmak, birkaç GB
diskten çok daha pahalı.

Motor nasıl çağrılıyor
----------------------
İçe aktarma ile değil — ayrı ortamdaki paketi bu süreçte ``import`` etmek
zaten mümkün değil. Sağlayıcı, sidecar'ın kendi ``python``ını bir alt süreç
olarak çalıştırıp WAV dosyasını diskten okuyor. Bu aynı zamanda motorun
çökmesinin ana süreci düşürmemesi demek.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Final, Sequence

#: Sidecar ortamlarının kökü. ``FOOL_HOME`` altında duruyor ki kullanıcının
#: veri dizini tek yerde kalsın ve kaldırma işlemi hepsini birden alsın.
_SIDECAR_DIRNAME: Final = "sidecars"

#: Alt süreç zaman aşımı. Model yükleme + sentez; ilk çağrı ağır olabilir.
SYNTH_TIMEOUT_SECONDS: Final = 300


def _isolated_env() -> dict[str, str]:
    """Sidecar alt sureci icin TEMIZ ortam.

    Neden sart: ana surec ``PYTHONPATH``i alt surece geciriyor. O degisken
    ana ortamin ``site-packages``ini sidecar'in yoluna sokuyor ve sidecar
    KENDI paketleri yerine onlari ice aktariyor -- yani izolasyonun tum amaci
    cokuyor. Gercek belirti:

        ImportError: tokenizers>=0.22.0,<=0.23.0 is required ...
        but found tokenizers==0.23.1
        Try: `pip install transformers -U`

    Kullaniciya "Read aloud failed" olarak gorunuyordu ve onerilen komut
    (transformers'i guncelle) YANLIS yeri gosteriyordu: sidecar'in kendi
    transformers'i zaten dogru surumdeydi, sizan paket tokenizers'ti.
    """
    env = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
        env.pop(name, None)
    return env


def sidecar_root() -> Path:
    # MAKINE koku -- profil evi degil. Bir sidecar ortami gigabaytlarca ve
    # degismez; profil basina kopyalamak, her profilin motorlari bastan
    # indirmesi demekti (bkz. ``fool/machine_assets.py``).
    from fool.machine_assets import machine_home

    return machine_home() / _SIDECAR_DIRNAME


def sidecar_dir(name: str) -> Path:
    return sidecar_root() / name


def sidecar_python(name: str) -> Path:
    """Sidecar ortamının yorumlayıcısı."""
    base = sidecar_dir(name)
    return base / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


#: ``(ad, sonda)`` -> yorumlayıcı imzası. Yalnızca OLUMLU sonuçlar.
_READY_CACHE: dict[tuple[str, str], tuple[float, int]] = {}
_READY_LOCK = threading.Lock()


def _python_signature(python: Path) -> tuple[float, int] | None:
    """Yorumlayıcının kimliği: değişirse önbellek geçersiz."""
    try:
        stat = python.stat()
    except OSError:
        return None
    return (stat.st_mtime, stat.st_size)


def is_ready(name: str, probe_module: str | None = None) -> bool:
    """Ortam var ve motor içinde kurulu mu?

    Yalnızca dizin varlığına bakmak yetmez: yarıda kesilmiş bir kurulum
    ortamı bırakır ama motoru bırakmaz, ve "kurulu" demek kullanıcıyı
    çalışma anında anlaşılmaz bir hataya götürürdü.

    OLUMLU cevap ÖNBELLEKLENİYOR
    ----------------------------
    Sonda izole bir yorumlayıcı SÜRECİ başlatıyor ve bu makinede ölçülen
    maliyeti 50-61 ms. Sorun maliyetin kendisi değil, NEREDE ödendiği:
    seslendirme eklentileri bunu ``synthesize()`` içinden, yani HER CÜMLE
    için çağırıyor. Kokoro'nun sıcak bir cümlesi 140-200 ms sürüyor -- yani
    ilk sese kadar geçen sürenin dörtte biri, oturum boyunca değişmesi
    mümkün olmayan bir bilgiyi yeniden öğrenmeye gidiyordu.

    Önbellek yorumlayıcının mtime+boyutuna bağlı: yeniden kurulum onu
    değiştiriyor ve sonda tekrar çalışıyor.

    OLUMSUZ cevap önbelleklenMİYOR. Kullanıcı motoru oturum ortasında
    kurabiliyor; "kurulu değil"i saklamak, kurulumdan sonra motorun
    görünmemesi olurdu -- ve o, düzeltilenden daha kötü bir hata.
    """
    python = sidecar_python(name)
    if not python.exists():
        return False
    if not probe_module:
        return True

    signature = _python_signature(python)
    cache_key = (name, probe_module)

    if signature is not None:
        with _READY_LOCK:
            if _READY_CACHE.get(cache_key) == signature:
                return True

    try:
        completed = subprocess.run(
            [str(python), "-c", f"import importlib.util as u; raise SystemExit(0 if u.find_spec({probe_module!r}) else 1)"],
            capture_output=True,
            env=_isolated_env(),
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    if completed.returncode != 0:
        return False

    if signature is not None:
        with _READY_LOCK:
            _READY_CACHE[cache_key] = signature

    return True


def _torch_build_is_cuda(name: str) -> bool | None:
    """``torch/version.py``ye bakarak cevapla; ``None`` = okunamadi.

    Neden alt surec YERINE dosya
    ----------------------------
    Eski yol her motor icin izole yorumlayicida ``import torch`` yapiyordu.
    Bir sorgu 4-5 saniye ve -- asil sorun -- her biri bir CUDA baglami
    ayirip yuzlerce MB VRAM ve bir o kadar RAM tutuyor. Katalog dokuz ogeyi
    PARALEL sorunca makine tek seferde bes torch sureci aciyordu; kullanici
    bunu "bilgisayarim bok gibi kasiyor" diye bildirdi ve haklıydi.

    Cevap zaten diskte duruyor. Wheel ``torch/version.py``ye yaziyor:

        __version__ = '2.13.0+cu126'
        cuda: Optional[str] = '12.6'      <- CUDA derlemesi
        cuda: Optional[str] = None        <- CPU derlemesi

    Yani sorunun tamami bir dosya okumasi: surec yok, ithal yok, VRAM yok.

    Bu, "kart calisiyor mu"yu DEGIL "derleme CUDA'li mi"yi olcuyor -- ama
    eski sondanin gercekte ayirt ettigi sey de buydu (PyPI'nin Windows
    tekerlegi CPU-only). Kartin varligi ayri bir soru ve ayri yerde
    sorulyor (``voice_models._cuda_available``).
    """
    base = sidecar_dir(name)
    candidates = [
        base / "Lib" / "site-packages" / "torch" / "version.py",
        base / "lib" / "site-packages" / "torch" / "version.py",
        *sorted(base.glob("lib/python*/site-packages/torch/version.py")),
    ]

    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("cuda"):
                continue
            _, _, value = stripped.partition("=")
            value = value.strip()
            # ``None`` = CPU derlemesi; tirnak icinde bir surum = CUDA.
            return value not in ("None", "")

        # Dosya var ama ``cuda`` satiri yok: bicim degismis olabilir, karar
        # verme -- cagiran taraf pahali sondaya dussun.
        return None

    return None


def has_cuda_torch(name: str) -> bool:
    """Sidecar'daki ``torch`` GERCEKTEN CUDA derlemesi mi?

    Paketin varligina bakmak yetmez: PyPI'nin Windows tekerlegi CPU-only'dir
    ve ayni ada sahiptir.

    Once ``torch/version.py`` okunuyor (bkz. ``_torch_build_is_cuda``); ancak
    o dosya okunamazsa ya da bicimi taninmazsa alt surecli sondaya
    dusuluyor. Yedegi silmedim: bilinmeyen bir kurulum bicimi karsisinda
    "CUDA yok" demek, kullanicinin CUDA dugmesini kaybetmesi olurdu.
    """
    from_file = _torch_build_is_cuda(name)
    if from_file is not None:
        return from_file

    python = sidecar_python(name)
    if not python.exists():
        return False
    try:
        completed = subprocess.run(
            [str(python), "-c", "import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)"],
            capture_output=True,
            env=_isolated_env(),
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    if completed.returncode != 0:
        return False

    if signature is not None:
        with _READY_LOCK:
            _READY_CACHE[cache_key] = signature

    return True


def installed_version(name: str, package: str) -> str:
    """Sidecar icindeki bir paketin surumu ("" = kurulu degil)."""
    python = sidecar_python(name)
    if not python.exists():
        return ""

    code = (
        "import importlib.metadata as m;"
        f"print(m.version({package!r}))"
    )
    try:
        done = subprocess.run(
            [str(python), "-c", code],
            capture_output=True,
            text=True,
            env=_isolated_env(),
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def pip_install(
    name: str,
    specs: Sequence[str],
    *,
    index_url: str = "",
    timeout: int = 1800,
    on_output: Callable[[str], None] | None = None,
) -> None:
    """Kurulu bir sidecar'a paket kur/degistir."""
    python = sidecar_python(name)
    if not python.exists():
        raise RuntimeError(f"{name} sidecar ortami kurulu degil")

    argv = [_uv(), "pip", "install", "--python", str(python)]
    if index_url:
        argv += ["--index-url", index_url]
    argv += list(specs)

    process = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        env=_isolated_env(),
        errors="replace",
    )
    tail: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        line = line.rstrip()
        if not line:
            continue
        tail.append(line)
        del tail[:-40]
        if on_output:
            on_output(line)

    if process.wait(timeout=timeout) != 0:
        last = tail[-1] if tail else "bilinmeyen hata"
        raise RuntimeError(f"{name}: kurulum basarisiz: {last}")


def _uv() -> str:
    """Depoya ait uv ikilisi.

    Sistem ``uv``sine güvenilmiyor: sürümü bilinmiyor ve kullanıcının
    makinesinde hiç olmayabilir. Kurulum zaten kendi uv'sini getiriyor.
    """
    try:
        from fool_cli.managed_uv import managed_uv_path

        path = managed_uv_path()
        if path.exists():
            return str(path)
    except Exception:
        pass

    from shutil import which

    found = which("uv")
    if not found:
        raise RuntimeError("uv bulunamadi; sidecar ortami olusturulamaz")
    return found


@dataclass(frozen=True)
class SidecarSpec:
    """Bir sidecar ortamının tanımı."""

    name: str
    #: Kurulacak paketler — TAM sabitlenmiş. Aralık yok: bu depo sürüm
    #: aralıklarını güvenlik gerekçesiyle reddediyor.
    specs: tuple[str, ...]
    probe_module: str
    #: Motorun ihtiyaç duyduğu en düşük Python. Ana yorumlayıcı daha yeni
    #: olabilir; sidecar kendi sürümünü seçer.
    python_version: str = "3.11"
    #: CUDA için ana kurulumdan SONRA uygulanan paketler.
    #:
    #: Neden ayrı bir adım: PyPI'nin Windows ``torch`` tekerleği CPU-only
    #: derlemedir ve ``torch.cuda.is_available()`` False döner — kart varken
    #: bile. Gerçek CUDA derlemesi yalnızca PyTorch'un kendi indeksinde.
    #: Önce normal kurulum yapılıp sonra torch ÜZERİNE yazılıyor, çünkü tersi
    #: sırada çözümleyici CUDA tekerleğini PyPI'ninkiyle değiştiriyor.
    cuda_specs: tuple[str, ...] = ()
    cuda_index_url: str = ""
    #: PyPI'da OLMAYAN ama resmî bir URL'den gelen ek tekerlekler.
    #:
    #: Neden gerekli: Kokoro spaCy'nin ``en_core_web_sm`` modelini istiyor ve
    #: o model PyPI'da yok. Bu adım olmadan motor kuruluyor, içe aktarılıyor,
    #: ama ilk sentezde ``E050`` ile patlıyor.
    #:
    #: Neden ``python -m spacy download`` DEĞİL: ``uv venv`` içinde ``pip``
    #: yok ve spaCy'nin indiricisi bu durumda "Download and installation
    #: successful" yazıp HİÇBİR ŞEY kurmuyor — denendi, doğrulandı. Sessiz
    #: başarı en kötü hata biçimi; tekerlek doğrudan uv ile kuruluyor.
    extra_wheels: tuple[str, ...] = ()


def create(
    spec: SidecarSpec,
    *,
    on_output: Callable[[str], None] | None = None,
    timeout: int = 1800,
    cuda: bool = False,
) -> None:
    """Ortamı kur. Zaten hazırsa hiçbir şey yapma.

    ``on_output`` verilirse uv'nin çıktısı satır satır aktarılır — kurulum
    dakikalarca sürebiliyor ve kullanıcıya ne olduğunu göstermek gerekiyor.
    """
    already = is_ready(spec.name, spec.probe_module)
    post_pending = bool(spec.extra_wheels) and not (
        sidecar_dir(spec.name) / ".fool-postinstall-done"
    ).exists()
    cuda_pending = cuda and bool(spec.cuda_specs) and not has_cuda_torch(spec.name)
    if already and not post_pending and not cuda_pending:
        return

    base = sidecar_dir(spec.name)
    base.parent.mkdir(parents=True, exist_ok=True)
    uv = _uv()

    def _run(argv: Sequence[str], stage: str) -> None:
        if on_output:
            on_output(stage)
        process = subprocess.Popen(
            list(argv),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            env=_isolated_env(),
            errors="replace",
        )
        tail: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip()
            if not line:
                continue
            tail.append(line)
            del tail[:-40]
            if on_output:
                on_output(line)
        code = process.wait(timeout=timeout)
        if code != 0:
            last = tail[-1] if tail else "bilinmeyen hata"
            raise RuntimeError(f"{stage} basarisiz: {last}")

    if not already:
        _run([uv, "venv", "--python", spec.python_version, str(base)], "creating environment")
        _run(
            [uv, "pip", "install", "--python", str(sidecar_python(spec.name)), *spec.specs],
            "installing engine",
        )

    if cuda and spec.cuda_specs:
        _run(
            [
                uv, "pip", "install",
                "--python", str(sidecar_python(spec.name)),
                "--index-url", spec.cuda_index_url,
                *spec.cuda_specs,
            ],
            "installing CUDA build",
        )

    # Kurulum sonrasi adimlar. Isaretci dosya idempotanlik icin: ortam hazir
    # olsa bile bu adim kosmamissa eksik kalir ve hata calisma anina ertelenir.
    marker = base / ".fool-postinstall-done"
    if spec.extra_wheels and not marker.exists():
        _run(
            [uv, "pip", "install", "--python", str(sidecar_python(spec.name)), *spec.extra_wheels],
            "downloading model data",
        )
        marker.write_text("ok", encoding="utf-8")

    if not is_ready(spec.name, spec.probe_module):
        raise RuntimeError(
            f"{spec.name}: kurulum bitti ama {spec.probe_module!r} ice aktarilamiyor"
        )


def run_script(name: str, script: str, args: Sequence[str], *, timeout: int | None = None) -> str:
    """Sidecar'ın yorumlayıcısında bir betik çalıştır ve stdout'unu döndür.

    Hata durumunda ``RuntimeError`` — stderr'in son satırıyla, çünkü sessiz
    başarısızlık kullanıcının neden ses çıkmadığını anlamasını imkânsız
    kılardı.
    """
    python = sidecar_python(name)
    if not python.exists():
        raise RuntimeError(f"{name} sidecar ortami kurulu degil")

    completed = subprocess.run(
        [str(python), "-c", script, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_isolated_env(),
        errors="replace",
        timeout=timeout or SYNTH_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        last = detail.splitlines()[-1] if detail else "bilinmeyen hata"
        raise RuntimeError(f"{name} sentezi basarisiz: {last}")
    return completed.stdout
