"""Yerel-önce kalması gereken şeyler.

Neden ayrı bir politika
-----------------------
The Fool yerel bir üründür: model, konuşma tanıma ve seslendirme kullanıcının
kendi makinesinde koşar. Upstream ise bulut sağlayıcılarını birinci sınıf
kabul ediyor ve yerel yol tökezlediğinde sessizce onlara düşüyor. İki ürünün
varsayılanı burada çelişiyor ve çelişkinin bedelini kullanıcı ödüyor.

Somut olarak ölçülen yol (``tools/transcription_tools.py::_get_provider``):
``stt.provider`` yazılmamışsa otomatik algılama merdiveni

    local > groq > openai > mistral > xai > elevenlabs > deepinfra

şeklinde iniyor. ``faster_whisper`` yüklenemezse -- CUDA kütüphanesi eksik,
tekerlek bozuk, sürüm çakışması -- MİKROFON KAYDI üçüncü bir tarafa
yükleniyor. Ortada yalnızca bir ``logger.info`` var; kullanıcıya görünen
hiçbir şey yok. Sesli sohbet çalışmaya devam ettiği için fark edilmesi de
mümkün değil.

Bu, sohbet için zaten bir OpenAI anahtarı olan herkesi vuruyor: anahtar
orada, kod onu bulup kullanıyor.

Kural: bulut, kullanıcının AÇIK tercihi olmadan seçilemez. Açık tercihin iki
biçimi var ve ikisi de saygı görüyor:

  1. ``stt.provider: groq`` -- kullanıcı sağlayıcıyı adıyla yazmış.
  2. ``stt.allow_cloud_fallback: true`` -- "yerel çalışmazsa buluta düş" demiş.

İkisi de yoksa yerel yol çalışmıyor demektir ve doğru davranış bunu
SÖYLEMEK, sessizce ses yüklemek değil.
"""

from __future__ import annotations

from typing import Any

_TRUE = frozenset({"1", "on", "true", "yes", "y"})


def _truthy(value: Any) -> bool:
    """``fool config set`` değerleri metin olarak yazıyor; ikisini de kabul et."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in _TRUE
    return False


def cloud_stt_allowed(stt_config: Any) -> bool:
    """Otomatik algılama bulut sağlayıcısına düşebilir mi?

    Okunamayan bir yapılandırma ``False`` döner: kapalı taraf güvenli taraf.
    """
    if not isinstance(stt_config, dict):
        return False
    return _truthy(stt_config.get("allow_cloud_fallback"))


#: Yerel yol çalışmadığında kullanıcıya söylenecek şey. Ne olduğu VE nasıl
#: düzeltileceği birlikte: yalnızca "STT yok" demek kullanıcıyı günlüklerde
#: dolaştırıyordu.
CLOUD_BLOCKED_MESSAGE = (
    "Local speech-to-text is unavailable and cloud fallback is off, so "
    "nothing was transcribed. Your microphone audio was NOT uploaded. "
    "Fix the local engine from Settings > Speech to text, or opt in "
    "explicitly with `fool config set stt.allow_cloud_fallback true` "
    "(or name a provider with `fool config set stt.provider openai`)."
)


# ---------------------------------------------------------------------------
# Seslendirme
# ---------------------------------------------------------------------------

#: Ana ortamda ya da kendi izole ortamlarında koşan, hiçbir yere bağlanmayan
#: seslendirme motorları. Sıra bilinçli: ölçülen ilk-çağrı sonrası gecikmeye
#: göre (Kokoro 0,08 sn, Piper benzeri, Qwen3-TTS 6,0 sn, Chatterbox 28 sn).
LOCAL_TTS_PROVIDERS = ("kokoro", "piper", "styletts2", "kyutai", "f5tts", "qwen3", "chatterbox")


def cloud_tts_allowed(tts_config: Any) -> bool:
    """Seslendirme buluta gidebilir mi?

    ``tts.provider`` AÇIKÇA yazılmışsa bu işlev hiç sorulmuyor -- kullanıcı
    sağlayıcıyı kendisi seçmiş. Buradaki soru yalnızca "hiç seçim yokken ne
    olacak".
    """
    if not isinstance(tts_config, dict):
        return False
    return _truthy(tts_config.get("allow_cloud_fallback"))


def preferred_local_tts(installed: Any) -> str | None:
    """Kurulu yerel motorlar arasından ilk tercihi seç.

    ``installed`` kurulu sağlayıcı adlarını veren herhangi bir küme/dizi.
    Hiçbiri yoksa ``None``.
    """
    try:
        available = {str(name).lower().strip() for name in installed}
    except TypeError:
        return None

    for provider in LOCAL_TTS_PROVIDERS:
        if provider in available:
            return provider
    return None


#: Yerel motor yokken ve bulut açılmamışken söylenecek şey.
TTS_CLOUD_BLOCKED_MESSAGE = (
    "No local text-to-speech engine is installed and cloud TTS is off, so "
    "nothing was spoken. Your text was NOT sent to Microsoft. Install a local "
    "voice from Settings > Text to speech (Kokoro is the fastest), or opt in "
    "explicitly with `fool config set tts.allow_cloud_fallback true` "
    "(or name a provider with `fool config set tts.provider edge`)."
)


# ---------------------------------------------------------------------------
# Bütün yüzeyleri bir arada göster
# ---------------------------------------------------------------------------

from dataclasses import dataclass  # noqa: E402


@dataclass(frozen=True)
class SurfaceFinding:
    """Tek bir yüzeyin ağ durumu."""

    #: ``model`` | ``stt`` | ``tts`` | ``web`` | ``browser``
    surface: str
    #: Bu yüzey makineden DIŞARI çıkmıyor mu?
    local: bool
    #: Ne bulundu -- kullanıcının okuyacağı tek cümle.
    detail: str
    #: Yerel değilse nasıl yerelleştirilir. Boş bırakılmıyor: yalnızca
    #: "dışarı çıkıyor" demek kullanıcıyı belgelerde dolaştırıyordu.
    remedy: str = ""


#: Kendi makinesinde koşan model sunucuları.
LOCAL_MODEL_PROVIDERS = frozenset(
    {"custom", "llamacpp", "llama_cpp", "lmstudio", "localai", "ollama", "vllm"}
)

#: Hiçbir yere bağlanmayan konuşma tanıma sağlayıcıları.
LOCAL_STT_PROVIDERS = frozenset({"local", "local_command"})


def _section(config: Any, name: str) -> dict:
    if not isinstance(config, dict):
        return {}
    value = config.get(name)
    return value if isinstance(value, dict) else {}


def _provider_of(section: dict) -> str:
    return str(section.get("provider") or "").lower().strip()


def audit_local_only(config: Any) -> list[SurfaceFinding]:
    """Bu yapılandırmayla hangi yüzeyler ağa çıkar?

    Bu denetimin varlık nedeni, ölçülen iki sızıntının ortak yanı: ikisi de
    tek tek bakıldığında görünmüyordu. ``stt.local`` dolu olduğu için STT
    yerel görünüyordu ama ``stt.provider`` yazılmadığından otomatik algılama
    buluta düşebiliyordu; TTS'in varsayılanı zaten Microsoft'tu.

    "Uygulamayı arkadaşıma göndersem ne dışarı çıkar?" sorusunun tek listede
    cevabı. Emin olunamayan her şey YEREL DEĞİL sayılıyor -- denetimin işi
    içini rahatlatmak değil.
    """
    model = _section(config, "model")
    stt = _section(config, "stt")
    tts = _section(config, "tts")
    web = _section(config, "web")
    browser = _section(config, "browser")

    findings: list[SurfaceFinding] = []

    # --- Model -------------------------------------------------------------
    provider = _provider_of(model)
    if not provider:
        findings.append(SurfaceFinding(
            "model", False,
            "no model provider configured - first run picks whatever it detects",
            "Set one explicitly: `fool config set model.provider lmstudio`",
        ))
    elif provider in LOCAL_MODEL_PROVIDERS:
        findings.append(SurfaceFinding("model", True, f"local model server ({provider})"))
    else:
        findings.append(SurfaceFinding(
            "model", False, f"cloud model provider ({provider})",
            "Run a local server (LM Studio / Ollama) and "
            "`fool config set model.provider lmstudio`",
        ))

    # --- Konuşma tanıma ----------------------------------------------------
    provider = _provider_of(stt)
    if cloud_stt_allowed(stt):
        findings.append(SurfaceFinding(
            "stt", False,
            "cloud fallback is enabled - microphone audio may be uploaded",
            "Turn it off: `fool config set stt.allow_cloud_fallback false`",
        ))
    elif not provider:
        findings.append(SurfaceFinding(
            "stt", False,
            "no stt.provider set - the engine is chosen at runtime",
            "Pin it: `fool config set stt.provider local` "
            "(cloud stays off unless stt.allow_cloud_fallback is set)",
        ))
    elif provider in LOCAL_STT_PROVIDERS:
        findings.append(SurfaceFinding("stt", True, f"local speech recognition ({provider})"))
    else:
        findings.append(SurfaceFinding(
            "stt", False, f"cloud speech recognition ({provider}) - microphone audio is uploaded",
            "Switch to local: `fool config set stt.provider local`",
        ))

    # --- Seslendirme -------------------------------------------------------
    provider = _provider_of(tts)
    if cloud_tts_allowed(tts):
        findings.append(SurfaceFinding(
            "tts", False,
            "cloud fallback is enabled - reply text may be sent to a third party",
            "Turn it off: `fool config set tts.allow_cloud_fallback false`",
        ))
    elif not provider:
        findings.append(SurfaceFinding(
            "tts", False,
            "no tts.provider set - the engine is chosen at runtime",
            "Pin it: `fool config set tts.provider kokoro`",
        ))
    elif provider in LOCAL_TTS_PROVIDERS:
        findings.append(SurfaceFinding("tts", True, f"local speech synthesis ({provider})"))
    else:
        findings.append(SurfaceFinding(
            "tts", False, f"cloud speech synthesis ({provider}) - reply text is sent out",
            "Switch to a local voice: `fool config set tts.provider kokoro`",
        ))

    # --- Web araması -------------------------------------------------------
    backend = str(web.get("backend") or "").lower().strip()
    if backend in ("off", "none", "disabled"):
        findings.append(SurfaceFinding("web", True, "web search is off"))
    else:
        findings.append(SurfaceFinding(
            "web", False,
            f"web search is on ({backend or 'default backend'}) - queries leave the machine",
            "Turn it off: `fool config set web.backend off` "
            "(searching the web is inherently a network action)",
        ))

    # --- Tarayıcı ----------------------------------------------------------
    backend = str(browser.get("backend") or "").lower().strip()
    if backend in ("off", "none", "disabled", "builtin", "local"):
        findings.append(SurfaceFinding("browser", True, f"browser backend is {backend or 'off'}"))
    else:
        findings.append(SurfaceFinding(
            "browser", False,
            f"browser backend '{backend}' is a hosted service",
            "Use the built-in stack: `fool config set browser.backend off`",
        ))

    return findings


def render_local_only_report(findings: "list[SurfaceFinding]") -> str:
    """Denetimi terminalde okunur hâle getir."""
    lines: list[str] = []
    leaks = [f for f in findings if not f.local]

    for f in findings:
        mark = "  yerel  " if f.local else "  DISARI "
        lines.append(f"{mark} {f.surface:8} {f.detail}")
        if not f.local and f.remedy:
            lines.append(f"           -> {f.remedy}")

    lines.append("")
    if leaks:
        lines.append(
            f"{len(leaks)} yuzey makineden disari cikiyor: "
            + ", ".join(f.surface for f in leaks)
        )
    else:
        lines.append("Hicbir yuzey makineden disari cikmiyor.")
    return "\n".join(lines)


def _main() -> int:
    """``python -m fool.local_only`` - kurulu yapilandirmayi denetle."""
    try:
        from fool_cli.config import load_config

        config = load_config() or {}
    except Exception as exc:  # pragma: no cover - yapilandirma okunamazsa
        print(f"yapilandirma okunamadi: {exc}")
        return 2

    findings = audit_local_only(config)
    print(render_local_only_report(findings))
    return 1 if any(not f.local for f in findings) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
