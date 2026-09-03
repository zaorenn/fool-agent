"""Yetki kazanılır, varsayılan olarak verilmez.

Sorun ölçülebilir: 9B'lik yerel bir model ``computer_use``, ``execute_code``,
``terminal_run`` ve ``delegate_task`` gibi araçları güvenilir biçimde
çağıramıyor. Upstream'in kendi kodu bunu zaten biliyor --
``agent/agent_init.py`` bazı modeller için "NOT agentic" uyarısı basıyor --
ama uyarı bir DİZE eşleşmesi ve yalnızca uyarı: araçlar yine de veriliyor.

Sonuç sessiz sınıftan: model aracı yanlış çağırıyor, tur boşa gidiyor,
kullanıcı "aptal" sanıyor. Kötü ihtimalde yanlış argümanla gerçekten bir şey
yapıyor.

Bu modül yetkiyi ÖLÇÜME bağlıyor: tehlikeli takımlar ancak model tool-calling
sınavını geçtiyse veriliyor.
"""

from __future__ import annotations

import pytest

from fool import agent_authority as aa


# ---------------------------------------------------------------------------
# Hangi takımlar yetki istiyor
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("toolset", [
    "code_execution", "computer_use", "cronjob", "delegation", "file", "terminal",
])
def test_makineyi_suren_takimlar_yetki_istiyor(toolset: str) -> None:
    assert toolset in aa.EARNED_TOOLSETS


@pytest.mark.parametrize("toolset", ["clarify", "image_gen", "tts", "vision", "web"])
def test_zararsiz_takimlar_yetki_istemiyor(toolset: str) -> None:
    """Yanlış çağrılan bir ``web_search`` yalnızca boşa giden bir tur."""
    assert toolset not in aa.EARNED_TOOLSETS


# ---------------------------------------------------------------------------
# Yetki kararı
# ---------------------------------------------------------------------------

BASE = {"clarify", "computer_use", "file", "terminal", "web"}


def test_sinav_gecilmemisse_tehlikeli_takimlar_dusuyor() -> None:
    granted = aa.granted_toolsets(BASE, passed=False)

    assert granted == {"clarify", "web"}


def test_sinav_gecilmisse_hicbir_sey_dusmuyor() -> None:
    assert aa.granted_toolsets(BASE, passed=True) == BASE


def test_kapi_kapaliyken_hicbir_sey_dusmuyor() -> None:
    """Varsayılan olarak kapı KAPALI: ölçüm var, kısıtlama opsiyonel.

    Çalışan bir kurulumu ölçüm yüzünden kırmak, çözdüğünden çok sorun
    üretirdi. Kullanıcı açık şekilde açıyor.
    """
    assert aa.granted_toolsets(BASE, passed=False, enforce=False) == BASE


def test_bos_kume_cokmuyor() -> None:
    assert aa.granted_toolsets(set(), passed=False) == set()


def test_sonuc_yeni_kume_giren_degismiyor() -> None:
    base = set(BASE)
    aa.granted_toolsets(base, passed=False)

    assert base == BASE


# ---------------------------------------------------------------------------
# Yapılandırma
# ---------------------------------------------------------------------------

def test_kapi_varsayilan_olarak_kapali() -> None:
    assert aa.enforcement_enabled({}) is False


@pytest.mark.parametrize("raw", [True, "true", "yes", "1", "on"])
def test_kapi_acik_tercihle_aciliyor(raw) -> None:
    assert aa.enforcement_enabled({"agent": {"require_benchmark": raw}}) is True


@pytest.mark.parametrize("raw", [False, "false", "no", "0", "", None])
def test_yanlis_degerler_kapiyi_acmiyor(raw) -> None:
    assert aa.enforcement_enabled({"agent": {"require_benchmark": raw}}) is False


def test_bozuk_yapilandirmada_kapi_kapali() -> None:
    for bad in (None, [], "nonsense", {"agent": 7}):
        assert aa.enforcement_enabled(bad) is False


# ---------------------------------------------------------------------------
# Kullanıcıya söylenen
# ---------------------------------------------------------------------------

def test_uyari_olcumu_ve_cozumu_birlikte_veriyor() -> None:
    message = aa.blocked_message("qwen/qwen3.5-9b", score=2, total=5)

    assert "qwen/qwen3.5-9b" in message
    assert "2/5" in message
    assert "fool" in message  # ne yapacagi yaziyor


# ---------------------------------------------------------------------------
# Kapının GERÇEKTEN kapattığı: Jarvis oturumu, uçtan uca
# ---------------------------------------------------------------------------
#
# Yukarıdaki sınavlar ``granted_toolsets``i doğruluyor. §6.4'ün sorduğu soru
# bir katman yukarıda: kapı AÇIKKEN gerçek bir Jarvis oturumu ne alıyor?
# İkisi ayrışabilirdi -- ``tui_gateway.server._load_enabled_toolsets`` kendi
# erken dönüşlerine sahip ve kapıyı hiç görmeyen bir yol bırakmak mümkündü.
#
# Ölçüldü (FOOL_DESKTOP=1, gerçek çözümleme):
#
#     kapı kapalı            -> 21 takım, 10'u kazanılması gereken
#     kapı açık + sınav yok  -> 11 takım, 0'ı kazanılması gereken
#
# Bu makinede model (google/gemma-4-e4b) sınavı 5/5 geçti, yani kapıyı açmak
# burada hiçbir şeyi kırmıyor -- ama sınanan şey o değil, kapının kapatması.


def _resolve_with(monkeypatch, *, require_benchmark, passed):
    """Gerçek çözümlemeyi verilen kapı durumuyla koştur."""
    import copy
    import os

    import fool_cli.config as cfgmod
    import fool_cli.tools_config as tools_config
    from fool.model_readiness import has_passed as _real_has_passed

    os.environ.setdefault("FOOL_DESKTOP", "1")

    config = copy.deepcopy(cfgmod.load_config() or {})
    config.setdefault("agent", {})["require_benchmark"] = require_benchmark

    monkeypatch.setattr(cfgmod, "load_config", lambda *a, **k: copy.deepcopy(config))
    if hasattr(tools_config, "load_config"):
        monkeypatch.setattr(tools_config, "load_config", lambda *a, **k: copy.deepcopy(config))

    import fool.model_readiness as readiness

    monkeypatch.setattr(readiness, "has_passed", lambda model: passed)
    del _real_has_passed

    from tui_gateway import server as srv

    return set(srv._load_enabled_toolsets("desktop") or [])


def test_kapi_ACIK_ve_sinav_GECILMEMISSE_Jarvis_MAKINEYE_DOKUNAMIYOR(monkeypatch) -> None:
    """Sesle "şunu sil" demek ile modelin ``terminal_run``ı doğru üretmesi ayrı."""
    granted = _resolve_with(monkeypatch, require_benchmark=True, passed=False)

    leaked = aa.EARNED_TOOLSETS & granted
    assert not leaked, f"kapi acikken kazanilmasi gereken takimlar sizdi: {sorted(leaked)}"


def test_kapi_ACIK_ama_sinav_GECILDIYSE_Jarvis_TAM_yuzeyini_aliyor(monkeypatch) -> None:
    """Kapı ölçüme bağlı; geçen modeli cezalandırmıyor."""
    granted = _resolve_with(monkeypatch, require_benchmark=True, passed=True)

    assert "terminal" in granted
    assert "file" in granted
    assert "code_execution" in granted


def test_kapi_KAPALIYKEN_olcum_yetkiyi_ETKILEMIYOR(monkeypatch) -> None:
    """Varsayılan kapalı: çalışan bir kurulumu bir ölçümün kararıyla kırmıyoruz."""
    granted = _resolve_with(monkeypatch, require_benchmark=False, passed=False)

    assert "terminal" in granted
    assert aa.EARNED_TOOLSETS & granted


def test_kisitlama_sohbet_araclarini_ELINDEN_ALMIYOR(monkeypatch) -> None:
    """Engellemek susturmak değil: model hâlâ cevap verebiliyor."""
    granted = _resolve_with(monkeypatch, require_benchmark=True, passed=False)

    assert granted, "kapi acikken model HICBIR arac almiyor"
    assert "web" in granted or "clarify" in granted
