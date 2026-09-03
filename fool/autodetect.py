"""İlk açılışta yerel model sunucusunu bul ve kendiliğinden bağlan.

Neden
-----
Yerel-önce bir uygulamanın ilk açılışta kullanıcıya "sağlayıcı seç, base URL
yaz, model kimliğini kopyala" demesi kabul edilemez — özellikle uygulamayı
denemesi için birine gönderiyorsan. Çoğu kişide zaten çalışan bir yerel sunucu
var; iş onu **bulmak**, sormak değil.

Bu modül bilinen yerel çalıştırıcıları yoklar ve cevap veren ilkini
yapılandırır. Hepsi OpenAI-uyumlu ``/v1/models`` konuşuyor, dolayısıyla tek bir
yoklama hepsini kapsıyor.

Tasarım kararları
-----------------
**Sıra bir tercihtir.** LM Studio önce geliyor çünkü Hermes'te birinci sınıf
sağlayıcı desteği var (``provider: "lmstudio"``); diğerleri ``custom`` uç
olarak bağlanıyor.

**Model seçimi rastgele değil.** Bir sunucuda birden çok model olabilir;
gömme (embedding) modelleri sohbet edemez, bu yüzden elenir. Kalanlar arasında
**araç çağırma (tool calling)** yapabilme ihtimali yüksek olanlar öne alınır —
The Fool ajan bir uygulama: dosya düzenliyor, komut çalıştırıyor. Tool calling
desteklemeyen bir model yalnızca sohbet eder ve kullanıcı "neden hiçbir şey
yapmıyor" diye sorar.

**Yoklama kısa tutulur.** Kapalı bir port anında reddeder; asılı kalan bir
sunucu için zaman aşımı düşük. Toplam maliyet ilk açılışta ~1 saniye.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Final

logger = logging.getLogger(__name__)

#: Tek uç için zaman aşımı. Kapalı port zaten anında döner; bu sayı yalnızca
#: asılı kalan bir sunucunun ilk açılışı kilitlemesini engelliyor.
PROBE_TIMEOUT_SECONDS: Final[float] = 1.5


@dataclass(frozen=True)
class Runner:
    """Bilinen bir yerel model çalıştırıcısı."""

    key: str
    label: str
    base_url: str
    #: Hermes sağlayıcı adı. ``custom`` = genel OpenAI-uyumlu uç.
    provider: str


#: Sıra = tercih. Birinci sınıf desteği olanlar önce.
RUNNERS: Final[tuple[Runner, ...]] = (
    Runner("lmstudio", "LM Studio", "http://127.0.0.1:1234/v1", "lmstudio"),
    Runner("ollama", "Ollama", "http://127.0.0.1:11434/v1", "custom"),
    Runner("jan", "Jan", "http://127.0.0.1:1337/v1", "custom"),
    Runner("llamacpp", "llama.cpp", "http://127.0.0.1:8080/v1", "custom"),
    Runner("vllm", "vLLM", "http://127.0.0.1:8000/v1", "custom"),
    Runner("textgen", "text-generation-webui", "http://127.0.0.1:5000/v1", "custom"),
    # Bionic: OpenAI-uyumlu uc, varsayilan 3000. Listenin SONUNDA cunku o
    # port cok yaygin (her Node dev sunucusu orada); once gercek model
    # sunuculari denensin ki yanlis bir servise baglanmayalim.
    Runner("bionic", "Bionic", "http://127.0.0.1:3000/v1", "custom"),
)

#: Sohbet edemeyen model kimlikleri — gömme/yeniden sıralama modelleri.
_NON_CHAT = ("embed", "embedding", "rerank", "bge-", "e5-", "gte-")

#: Araç çağırmayı güvenilir yapan aileler. Kapsayıcı olmak zorunda değil;
#: yalnızca eşit adaylar arasında sıralama ipucu.
_TOOL_CAPABLE_HINTS = (
    "qwen", "llama", "mistral", "fool", "command-r", "firefunction",
    "granite", "gemma", "phi", "devstral", "gpt-oss",
)


@dataclass(frozen=True)
class Detection:
    runner: Runner
    models: list[str]
    chosen_model: str | None


def _fetch_models(base_url: str) -> list[str]:
    """``/v1/models`` çağır ve model kimliklerini döndür. Hata = boş liste."""
    url = base_url.rstrip("/") + "/models"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return []
    except Exception:  # pragma: no cover — savunmacı
        return []

    entries = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return []

    out: list[str] = []
    for item in entries:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            out.append(item["id"])
    return out


def _is_chat_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return not any(marker in lowered for marker in _NON_CHAT)


def choose_model(models: list[str]) -> str | None:
    """Sohbet + araç çağırma için en olası modeli seç.

    Gömme modelleri elenir. Kalanlar arasında bilinen araç-yetenekli aileler
    öne alınır; hiçbiri eşleşmezse ilk sohbet modeli döner.
    """
    chat = [m for m in models if _is_chat_model(m)]
    if not chat:
        return None

    for hint in _TOOL_CAPABLE_HINTS:
        for model in chat:
            if hint in model.lower():
                return model
    return chat[0]


def detect() -> Detection | None:
    """Çalışan ilk yerel sunucuyu bul. Hiçbiri yoksa ``None``."""
    for runner in RUNNERS:
        models = _fetch_models(runner.base_url)
        if not models:
            continue
        chosen = choose_model(models)
        logger.info(
            "[autodetect] %s bulundu (%d model), secilen: %s",
            runner.label, len(models), chosen or "-",
        )
        return Detection(runner=runner, models=models, chosen_model=chosen)
    return None


def config_patch(detection: Detection) -> dict[str, Any]:
    """Tespitten ``config.yaml``'a yazılacak parçayı üret."""
    model: dict[str, Any] = {"provider": detection.runner.provider}
    if detection.chosen_model:
        model["default"] = detection.chosen_model
    # LM Studio birinci sınıf: varsayılan ucu zaten biliyor, base_url yazmaya
    # gerek yok. Diğerleri genel `custom` uç olarak bağlanıyor.
    if detection.runner.provider == "custom":
        model["base_url"] = detection.runner.base_url
    return {"model": model}
