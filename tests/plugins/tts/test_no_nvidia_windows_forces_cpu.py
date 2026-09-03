"""TTS eklentileri: NVIDIA GPU yoksa Windows'ta "auto"/"cuda" CPU'ya sabitlenmeli.

Olculen cokme: fool-chatterbox'ta (ve AYNI DESENI tasiyan bes kardes
eklentide) "auto"/"cuda" HAM olarak sidecar'a gonderiliyordu. Sidecar'in
kendi torch.cuda.is_available() cagrisi, AMD/Intel entegre GPU'lu bir
Windows makinesinde (NVIDIA yok) STATUS_STACK_BUFFER_OVERRUN ile TUM
backend surecini cokertti -- SYSTRAN/faster-whisper#1293'un bildirdigi
AYNI sinif, whisper icin tools/transcription_tools.py'de duzeltilen
cokme. Sadece masaustu uygulamasi uzerinden yeniden uretildi: cikla
`fool serve` hicbir TTS istegi olmadan bu kod yoluna hic girmiyordu.

Guvenligin dayandigi temel: shutil.which("nvidia-smi") bir PATH aramasi,
torch/CUDA cagrisi degil -- cokme riskini TASIMIYOR, ve gercek bir NVIDIA
makinesinde device "auto"/"cuda" olarak DEGISMEDEN kaliyor (sidecar'in
kendi CUDA torch'u karar vermeye devam ediyor).
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

_PLUGINS = (
    "fool-chatterbox",
    "fool-kokoro",
    "fool-f5tts",
    "fool-kyutai",
    "fool-styletts2",
    "fool-qwen3",
)


def _source(name: str) -> str:
    return (REPO_ROOT / "plugins" / "tts" / name / "__init__.py").read_text(encoding="utf-8")


def test_hepsi_shutil_which_nvidia_smi_KONTROLU_taniyor():
    for name in _PLUGINS:
        src = _source(name)
        assert "shutil.which(" + chr(34) + "nvidia-smi" + chr(34) + ")" in src, name


def test_hepsi_platform_system_windows_ile_SINIRLI():
    # Linux/macOS'ta bu koruma HIC devreye girmemeli -- oralarda ayni
    # native crash sinifi olculmedi, ve gereksiz bir CPU zorlamasi
    # GPU'su olan bir Linux/macOS kullanicisini bosuna yavaslatirdi.
    for name in _PLUGINS:
        src = _source(name)
        i = src.index('shutil.which("nvidia-smi")')
        blok = src[max(0, i - 200) : i]
        assert 'platform.system() == "Windows"' in blok, name


def test_hepsi_gercek_NVIDIA_makinesinde_DEGISTIRMIYOR():
    # Koruma yalnizca "device cpu'ya sabitleniyor" satirini icermeli;
    # "auto"/"cuda" durumunu BASKA bir sekilde degistirmemeli.
    for name in _PLUGINS:
        src = _source(name)
        i = src.index('shutil.which("nvidia-smi")')
        blok = src[i : i + 300]
        assert 'device = "cpu"' in blok, name


def test_import_platform_ve_shutil_EKLENDI():
    for name in _PLUGINS:
        src = _source(name)
        assert "import platform" in src, name
        assert "import shutil" in src, name
