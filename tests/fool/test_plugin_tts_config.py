"""Motor başına ayarlar eklentiye GERÇEKTEN ulaşıyor mu?

Ölçülen hata
------------
Yerel seslendirme eklentilerinin HEPSİ ayarlarını ``extra["config"]``
içinden okuyor:

    config = extra.get("config") or {}
    cfg = config.get("chatterbox")      -> device, voice_sample

``tools/tts_tool.py`` bu argümanı HİÇ geçmiyordu. Yani ``cfg`` her zaman boş
bir sözlüktü ve motor ad alanındaki ne varsa sessizce yok sayılıyordu:

* **Ses klonu.** Kullanıcı bir kayıt yüklüyor, seçiyor, panel "seçili"
  gösteriyor ve motor kendi yerleşik sesiyle konuşmaya devam ediyor.
  Kullanıcının bildirdiği "chatterbox'taki ses Ultron değil kadın sesiydi"
  tam olarak buydu -- klon hiç uygulanmıyordu.
* **``device``.** Her zaman "auto" gidiyordu; panelde CUDA seçili olsa bile.

Sessiz sınıftan: hata yok, yalnızca yaptığın seçim hiçbir şey yapmıyor.

Neden bayt karşılaştırması KANIT DEĞİL
--------------------------------------
İlk denememde aynı cümleyi klon açık/kapalı sentezleyip dosya boyutlarının
farklı olmasına bakmıştım. Bu yanlış bir muhakemeydi: Chatterbox örnekleyici
bir model ve AYNI girdiyle her çağrıda farklı ses üretiyor. Boyut farkı
hiçbir şey göstermiyor. Burada motora GİDEN argüman sınanıyor.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins" / "tts"


def _local_plugins() -> list[Path]:
    return sorted(p / "__init__.py" for p in PLUGINS.iterdir() if (p / "__init__.py").is_file())


def test_eklentiler_config_BEKLIYOR() -> None:
    """Sözleşmenin bir ucu: eklentiler bu argümanı okuyor."""
    readers = [
        path
        for path in _local_plugins()
        if 'extra.get("config")' in path.read_text(encoding="utf-8")
    ]

    assert readers, "hicbir eklenti config okumuyor -- sinav anlamsizlasti"


def test_dagitim_config_GECIYOR() -> None:
    """Sözleşmenin diğer ucu. Kopan yer burasıydı."""
    source = (REPO / "tools" / "tts_tool.py").read_text(encoding="utf-8")

    assert "FOOL-SEAM: plugin-tts-config" in source
    assert "config=tts_config" in source


def test_config_okuyan_her_eklenti_KARSILIGINI_aliyor() -> None:
    """Yeni bir eklenti ``config`` okur ama dağıtım geçmezse burada kırılır."""
    dispatch = (REPO / "tools" / "tts_tool.py").read_text(encoding="utf-8")

    for path in _local_plugins():
        if 'extra.get("config")' in path.read_text(encoding="utf-8"):
            assert "config=tts_config" in dispatch, (
                f"{path.parent.name} config okuyor ama dagitim gecirmiyor"
            )


# ---------------------------------------------------------------------------
# Gerçek çağrı: motora GİDEN argüman
# ---------------------------------------------------------------------------

def test_KLON_gercekten_motora_ulasiyor(monkeypatch, tmp_path) -> None:
    """Sahte bir eklenti DEĞİL: gerçek dağıtım işlevi çağrılıyor ve
    eklentinin aldığı ``config`` okunuyor."""
    import tools.tts_tool as tts_tool

    seen: dict = {}

    class _Spy:
        def synthesize(self, text, output_path, **extra):
            seen.update(extra)
            Path(output_path).write_bytes(b"RIFF")
            return output_path

    import agent.tts_registry as registry
    import fool_cli.plugins as plugins

    monkeypatch.setattr(registry, "get_provider", lambda key: _Spy())
    monkeypatch.setattr(plugins, "_ensure_plugins_discovered", lambda force=False: None)

    config = {
        "chatterbox": {"device": "cuda", "voice_sample": "C:/klon.wav"},
        "provider": "chatterbox",
    }

    out = tts_tool._dispatch_to_plugin_provider("merhaba", str(tmp_path / "o.wav"), "chatterbox", config)

    assert out, "dagitim hicbir sey dondurmedi"
    assert seen.get("config") == config, "eklentiye config ULASMADI"
    assert seen["config"]["chatterbox"]["voice_sample"] == "C:/klon.wav"
    assert seen["config"]["chatterbox"]["device"] == "cuda"


def test_dagitim_imzasi_config_kabul_ediyor() -> None:
    """ABC ``**extra`` taşıyor; imza değişirse burada görünür."""
    from agent.tts_provider import TTSProvider

    params = inspect.signature(TTSProvider.synthesize).parameters

    assert any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()), (
        "TTSProvider.synthesize artik **extra almiyor -- config gecirilemez"
    )


# ---------------------------------------------------------------------------
# Motor başına SES seçimi
# ---------------------------------------------------------------------------

def test_MOTOR_BASINA_ses_secimi_ulasiyor(monkeypatch, tmp_path) -> None:
    """Panel ``tts.<motor>.voice``a yazıyor; dağıtım yalnızca üst seviye
    ``tts.voice``i okuyordu.

    Sonucu: panelden bir konuşmacı seçmek (Kokoro'nun kadın/erkek sesleri)
    HİÇBİR ŞEY yapmıyordu -- kullanıcının bildirdiği "seçsem bile değişen bir
    şey olmuyor".
    """
    import agent.tts_registry as registry
    import fool_cli.plugins as plugins
    import tools.tts_tool as tts_tool

    seen: dict = {}

    class _Spy:
        def synthesize(self, text, output_path, **extra):
            seen.update(extra)
            Path(output_path).write_bytes(b"RIFF")
            return output_path

    monkeypatch.setattr(registry, "get_provider", lambda key: _Spy())
    monkeypatch.setattr(plugins, "_ensure_plugins_discovered", lambda force=False: None)

    config = {"kokoro": {"voice": "am_michael"}, "provider": "kokoro", "voice": "af_heart"}

    tts_tool._dispatch_to_plugin_provider("merhaba", str(tmp_path / "o.wav"), "kokoro", config)

    # Motor ad alani UST SEVIYEYI eziyor.
    assert seen.get("voice") == "am_michael"


def test_motor_ad_alani_YOKSA_ust_seviyeye_dusuyor(monkeypatch, tmp_path) -> None:
    """Motor ad alanı olmayan bulut sağlayıcıları üst seviyeyi kullanıyor."""
    import agent.tts_registry as registry
    import fool_cli.plugins as plugins
    import tools.tts_tool as tts_tool

    seen: dict = {}

    class _Spy:
        def synthesize(self, text, output_path, **extra):
            seen.update(extra)
            Path(output_path).write_bytes(b"RIFF")
            return output_path

    monkeypatch.setattr(registry, "get_provider", lambda key: _Spy())
    monkeypatch.setattr(plugins, "_ensure_plugins_discovered", lambda force=False: None)

    tts_tool._dispatch_to_plugin_provider(
        "merhaba", str(tmp_path / "o.wav"), "kokoro", {"provider": "kokoro", "voice": "af_heart"}
    )

    assert seen.get("voice") == "af_heart"
