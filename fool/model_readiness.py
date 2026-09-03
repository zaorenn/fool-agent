"""Modelin tool-calling sınavı — ad değil DAVRANIŞ ölçülür.

Neden ad yetmiyor
-----------------
Upstream'in "bu model agentic değil" kararı bir dize eşleşmesi: model adında
belirli parçalar aranıyor. Bu iki yönden de yanlış cevap veriyor -- adı
tanınmayan yetenekli bir model kısıtlanmıyor, adı tanınan ama ince ayarlanmış
bir model haksız yere işaretleniyor. Yerel modellerde ad zaten kullanıcının
koyduğu bir etiket.

Burada modele gerçek araç şemaları verilip birkaç somut istek yapılıyor ve
doğru aracı doğru argümanlarla çağırıp çağırmadığına bakılıyor. Ölçüm yetkiyi
belirliyor (bkz. ``fool/agent_authority.py``).

Sınavın kısa olması bilinçli: amaç bir sıralama tablosu üretmek değil, "bu
model bir aracı doğru çağırabiliyor mu" sorusuna cevap vermek. Uzun bir sınav
ilk açılışı dakikalarca bekletirdi.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: Kaçını doğru yapması gerekiyor. Tek bir kusur modeli sınıfta bırakmamalı
#: (örnekleme gürültüsü), yarısı da yetmemeli.
PASS_RATIO = 0.8


@dataclass(frozen=True)
class Probe:
    """Tek bir sınav sorusu."""

    name: str
    prompt: str
    expect_tool: str
    #: Cevapta MUTLAKA bulunması gereken argümanlar (değeriyle birlikte).
    expect_args: dict = field(default_factory=dict)


#: Sınav sırasında modele verilen araçlar. Gerçek araçların kopyası DEĞİL:
#: sınav hiçbir şey çalıştırmıyor, yalnızca çağrıyı okuyor. Gerçek araçları
#: kullanmak, sınavın yan etkisi olması demekti.
PROBE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "City name"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_numbers",
            "description": "Add two integers.",
            "parameters": {
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                "required": ["a", "b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Start a countdown timer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {"type": "integer"},
                    "label": {"type": "string"},
                },
                "required": ["seconds"],
            },
        },
    },
]

PROBES = (
    Probe(
        name="tek-arguman",
        prompt="What is the weather in Istanbul right now?",
        expect_tool="get_weather",
        expect_args={"city": "Istanbul"},
    ),
    Probe(
        name="iki-arguman",
        prompt="Add 17 and 25 for me.",
        expect_tool="add_numbers",
        expect_args={"a": 17, "b": 25},
    ),
    Probe(
        name="birim-cevirme",
        prompt="Set a timer for two minutes.",
        expect_tool="set_timer",
        expect_args={"seconds": 120},
    ),
    Probe(
        name="dolayli-istek",
        prompt="I am heading out to Ankara -- should I take a coat?",
        expect_tool="get_weather",
        expect_args={"city": "Ankara"},
    ),
    Probe(
        name="etiketli-zamanlayici",
        prompt="Remind me in 30 seconds, and label it tea.",
        expect_tool="set_timer",
        expect_args={"seconds": 30, "label": "tea"},
    ),
)


def _arguments(call: Any) -> dict | None:
    """Çağrının argümanlarını sözlük olarak oku.

    Çoğu sağlayıcı ``arguments``ı JSON DİZESİ döndürüyor. Bunu okumamak,
    doğru çalışan bir modeli haksız yere sınıfta bırakırdı.
    """
    if not isinstance(call, dict):
        return None
    raw = call.get("arguments")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _matches(expected: Any, actual: Any) -> bool:
    """Beklenen değerle gelen değer aynı şeyi mi söylüyor?

    Sayılar metin olarak gelebiliyor (``"120"``), metinler farklı büyük-küçük
    harfle. Ölçtüğümüz şey biçim değil, modelin doğru bilgiyi taşıyıp
    taşımadığı.
    """
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, (int, float)):
        try:
            return float(expected) == float(actual)
        except (TypeError, ValueError):
            return False
    return str(expected).strip().lower() == str(actual).strip().lower()


def grade(probe: Probe, call: Any) -> bool:
    """Bu çağrı soruyu doğru cevaplıyor mu?"""
    args = _arguments(call)
    if args is None:
        return False
    if call.get("name") != probe.expect_tool:
        return False

    # Fazladan argüman geçmeyi engellemiyor: ölçtüğümüz şey doğru aracı doğru
    # bilgiyle çağırmak, birebir eşitlik değil.
    return all(
        key in args and _matches(value, args[key])
        for key, value in probe.expect_args.items()
    )


def summarize(model: str, results: list) -> dict:
    """Sonuçları puana ve geçti/kaldı kararına çevir.

    Boş sonuç ``passed=False``: hiç ölçüm yapılamadıysa "geçti" demek,
    ölçmemekle aynı şey olurdu.
    """
    total = len(results)
    score = sum(1 for ok in results if ok)
    passed = bool(total) and (score / total) >= PASS_RATIO

    return {"model": model, "score": score, "total": total, "passed": passed}


# ---------------------------------------------------------------------------
# Sınavı gerçekten çalıştırma
# ---------------------------------------------------------------------------

def _first_tool_call(response: Any) -> dict | None:
    """OpenAI uyumlu bir cevaptan ilk araç çağrısını çıkar.

    Sağlayıcılar arasında kabuk farkları var (``tool_calls`` vs eski
    ``function_call``); ikisi de okunuyor. Hiçbiri yoksa ``None`` -- o da bir
    cevap: model araç çağırmadı.
    """
    try:
        message = response.choices[0].message
    except Exception:
        return None

    calls = getattr(message, "tool_calls", None)
    if calls:
        fn = getattr(calls[0], "function", None)
        if fn is not None:
            return {"name": getattr(fn, "name", ""), "arguments": getattr(fn, "arguments", "")}

    legacy = getattr(message, "function_call", None)
    if legacy is not None:
        return {
            "name": getattr(legacy, "name", ""),
            "arguments": getattr(legacy, "arguments", ""),
        }
    return None


def run_benchmark(client: Any, model: str) -> dict:
    """Sınavı çalıştır ve sonucu döndür.

    *client* OpenAI uyumlu bir istemci (LM Studio, Ollama, herhangi biri).
    Ağ hatası tek bir soruyu düşürür, sınavı değil: bir zaman aşımı yüzünden
    modeli sınıfta bırakmak yanlış olurdu -- ama sessizce geçirmek daha
    yanlış, o yüzden düşen soru YANLIŞ sayılıyor ve raporda görünüyor.
    """
    results: list[bool] = []
    detail: list[dict] = []

    for probe in PROBES:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": probe.prompt}],
                tools=PROBE_TOOLS,
                temperature=0,
            )
            call = _first_tool_call(response)
            ok = grade(probe, call)
            note = "" if ok else f"cagri: {call!r}"
        except Exception as exc:
            ok = False
            note = f"hata: {exc}"

        results.append(ok)
        detail.append({"probe": probe.name, "ok": ok, "note": note})

    summary = summarize(model, results)
    summary["detail"] = detail
    return summary


def _main() -> int:
    """``python -m fool.model_readiness`` -- yapılandırılmış modeli sına."""
    try:
        from fool_cli.config import load_config

        config = load_config() or {}
        model_cfg = config.get("model") or {}
        model = str(model_cfg.get("default") or model_cfg.get("model") or "").strip()
        base_url = str(model_cfg.get("base_url") or "http://localhost:1234/v1").strip()
    except Exception as exc:
        print(f"yapilandirma okunamadi: {exc}")
        return 2

    if not model:
        print("model yapilandirilmamis: `fool model` ile sec")
        return 2

    try:
        from openai import OpenAI

        client = OpenAI(base_url=base_url, api_key="local")
    except Exception as exc:
        print(f"istemci kurulamadi: {exc}")
        return 2

    result = run_benchmark(client, model)
    # Karar SAKLANIYOR: yetki kapisi her oturumda sinav calistiramaz --
    # bes model cagrisi acilisi saniyelerce bekletirdi.
    save_verdict(result)

    print(f"model : {result['model']}")
    print(f"puan  : {result['score']}/{result['total']}")
    for row in result["detail"]:
        mark = "gecti " if row["ok"] else "KALDI "
        print(f"  {mark} {row['probe']:22} {row['note']}")
    print()
    print("SONUC: gecti" if result["passed"] else "SONUC: kaldi")

    if not result["passed"]:
        from fool.agent_authority import blocked_message

        print()
        print(blocked_message(result["model"], result["score"], result["total"]))

    return 0 if result["passed"] else 1




# ---------------------------------------------------------------------------
# Kararın saklanması
# ---------------------------------------------------------------------------

def verdict_path():
    """Sınav sonuçlarının tutulduğu dosya."""
    from pathlib import Path

    from fool_cli.config import get_hermes_home

    return Path(get_hermes_home()) / "model-readiness.json"


def _load_all() -> dict:
    path = verdict_path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        # Okunamayan bir karar dosyasi "karar yok" demek. Cokmek, yalnizca
        # bir gecmis kaydi yuzunden uygulamayi acilmaz yapardi.
        return {}
    return data if isinstance(data, dict) else {}


def save_verdict(result: dict) -> None:
    """Sonucu MODEL ADINA göre sakla.

    Karar modele bağlı: bir modelin geçmesi diğerini geçirmez. Model
    değiştirmek yetkinin de değişmesi demek; eski kararı taşımak, kullanıcının
    hiç sınamadığı bir modele yetki vermekti.
    """
    model = str(result.get("model") or "").strip()
    if not model:
        return

    data = _load_all()
    data[model] = {
        "score": int(result.get("score") or 0),
        "total": int(result.get("total") or 0),
        "passed": bool(result.get("passed")),
        "model": model,
    }

    path = verdict_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def load_verdict(model: str) -> dict | None:
    entry = _load_all().get(str(model or "").strip())
    return entry if isinstance(entry, dict) else None


def has_passed(model: str) -> bool:
    """Bu model sınavı geçti mi?

    Hiç sınanmamış model ``False``. Kapıyı açan kullanıcı ölçüm istiyor;
    ölçmeden geçirmek kapıyı hiç açmamakla aynı şey olurdu.
    """
    verdict = load_verdict(model)
    return bool(verdict and verdict.get("passed"))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
