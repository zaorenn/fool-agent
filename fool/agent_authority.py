"""Yetki kazanılır, varsayılan olarak verilmez.

Sorun ölçülebilir. 9B'lik yerel bir model ``computer_use``, ``execute_code``,
``terminal_run``, ``delegate_task`` gibi araçları güvenilir biçimde
çağıramıyor: şema uydurma, eksik zorunlu alan, düz metin içinde JSON. Upstream
bunu zaten biliyor -- ``agent/agent_init.py`` bazı modeller için "NOT agentic"
uyarısı basıyor -- ama o uyarı bir DİZE eşleşmesi ve yalnızca uyarı: araçlar
yine de veriliyor.

Sonuç sessiz sınıftan: model aracı yanlış çağırıyor, tur boşa gidiyor,
kullanıcı modeli aptal sanıyor. Kötü ihtimalde yanlış argümanla gerçekten bir
şey yapıyor -- ``terminal_run`` ile.

Burada yetki ÖLÇÜME bağlanıyor (bkz. ``fool/model_readiness.py``): makineyi
süren takımlar ancak model tool-calling sınavını geçtiyse veriliyor.

Kapı varsayılan olarak KAPALI
-----------------------------
Ölçüm her zaman yapılıp raporlanıyor, kısıtlama ise açık tercihle
başlıyor (``agent.require_benchmark``). Çalışan bir kurulumu bir ölçümün
kararıyla kırmak, çözdüğünden çok sorun üretirdi -- özellikle ölçümün
kendisi modelin o anki durumuna bağlıyken.
"""

from __future__ import annotations

from typing import Any, Iterable

#: Yanlış çağrıldığında MAKİNEYE ya da kullanıcının verisine dokunan takımlar.
#:
#: Ölçüt "tehlikeli mi" değil, "yanlış çağrılırsa bedeli boşa giden bir turdan
#: büyük mü". ``web_search`` yanlış çağrılırsa yalnızca boş sonuç döner;
#: ``terminal_run`` yanlış çağrılırsa dosya siler.
EARNED_TOOLSETS = frozenset({
    "browser",
    "code_execution",
    "computer_use",
    "cronjob",
    "delegation",
    "file",
    "homeassistant",
    "memory",
    "session_search",
    "skills",
    "terminal",
})

_TRUE = frozenset({"1", "on", "true", "yes", "y"})


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in _TRUE
    return False


def enforcement_enabled(config: Any) -> bool:
    """Kısıtlama açık mı? Varsayılan ``False``."""
    if not isinstance(config, dict):
        return False
    agent = config.get("agent")
    if not isinstance(agent, dict):
        return False
    return _truthy(agent.get("require_benchmark"))


def granted_toolsets(
    base: Iterable[str], *, passed: bool, enforce: bool = True
) -> set:
    """Modelin GERÇEKTEN alacağı takımlar.

    Girdi kümesi değiştirilmiyor: çağıran taraf çoğu zaman paylaşılan bir
    yapılandırma nesnesi veriyor ve onu yerinde budamak başka yüzeyleri
    sessizce etkilerdi.
    """
    result = set(base)
    if passed or not enforce:
        return result
    return result - EARNED_TOOLSETS


def blocked_message(model: str, score: int, total: int) -> str:
    """Kullanıcıya ne olduğunu VE ne yapacağını söyle.

    Yalnızca "araçlar kısıtlandı" demek kullanıcıyı günlüklerde dolaştırırdı.
    """
    return (
        f"Tool-calling benchmark: {model} scored {score}/{total}. "
        "Machine-touching toolsets (terminal, files, code execution, browser, "
        "delegation) are withheld until it passes. "
        "Re-run with `python -m fool.model_readiness`, pick a stronger model "
        "with `fool model`, or turn the gate off with "
        "`fool config set agent.require_benchmark false`."
    )
