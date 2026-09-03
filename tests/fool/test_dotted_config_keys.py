"""Model kimlikleri NOKTA taşır — anahtar bölme onları parçalamamalı.

Ölçülen hata
------------
``set_config_value`` her noktadan bölüyordu:

    fool config set agent.reasoning_overrides.qwen/qwen3.5-9b none

    -> agent:
         reasoning_overrides:
           "qwen/qwen3":
             "5-9b": none          <- YANLIŞ yapı

Komut "✓ Set" diyor, yazdığı şey yanlış ve ayar hiçbir zaman okunmuyor.
Sessiz sınıftan: hata yok, yalnızca yaptığın şey hiçbir işe yaramıyor.

Nokta taşımak model kimliklerinde kuraldır, istisna değil: ``qwen3.5``,
``gpt-4.1``, ``claude-4.6``.

Kural neden DAR
---------------
"Gerisi tek anahtar" yalnızca değeri SKALER olan, adla anahtarlanmış kaplarda
geçerli. ``mcp_servers.<ad>.<alan>`` giremez -- orada ad tek segment ve altında
alanlar var, yani aynı kural ``mcp_servers.my.server.command``i tek bir ada
çevirirdi.
"""

from __future__ import annotations

import pytest

from fool_cli.config import _split_config_key, _validate_config_key


# ---------------------------------------------------------------------------
# Bölme
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "model",
    ["qwen/qwen3.5-9b", "gpt-4.1", "claude-4.6", "google/gemma-4-e4b", "a.b.c.d"],
)
def test_NOKTALI_model_kimligi_TEK_anahtar(model: str) -> None:
    parts = _split_config_key(f"agent.reasoning_overrides.{model}")

    assert parts == ["agent", "reasoning_overrides", model]


def test_SIRADAN_yollar_eskisi_gibi_bolunuyor() -> None:
    assert _split_config_key("tts.kokoro.voice") == ["tts", "kokoro", "voice"]
    assert _split_config_key("agent.max_turns") == ["agent", "max_turns"]
    assert _split_config_key("model.default") == ["model", "default"]


def test_ALAN_TASIYAN_kaplar_KURALIN_DISINDA() -> None:
    """``mcp_servers.<ad>.<alan>``: ad tek segment, altında alanlar var."""
    assert _split_config_key("mcp_servers.my.server.command") == [
        "mcp_servers",
        "my",
        "server",
        "command",
    ]


def test_kabin_KENDISI_bolunmuyor() -> None:
    assert _split_config_key("agent.reasoning_overrides") == ["agent", "reasoning_overrides"]


# ---------------------------------------------------------------------------
# Gerçek yazma
# ---------------------------------------------------------------------------

def test_NOKTALI_kimlik_dogru_yere_yaziliyor() -> None:
    """Bölmenin sonucu: iç içe bir sözlük değil, TEK anahtar."""
    from fool_cli.config import _set_nested

    config: dict = {}
    _set_nested(config, "agent.reasoning_overrides.qwen/qwen3.5-9b", "none")

    overrides = config["agent"]["reasoning_overrides"]

    assert overrides == {"qwen/qwen3.5-9b": "none"}
    # Parcalanmis hali GERI GELMEMELI.
    assert "qwen/qwen3" not in overrides


def test_ayni_kapta_IKI_model_yan_yana_duruyor() -> None:
    from fool_cli.config import _set_nested

    config: dict = {}
    _set_nested(config, "agent.reasoning_overrides.qwen/qwen3.5-9b", "none")
    _set_nested(config, "agent.reasoning_overrides.google/gemma-4-e4b", "low")

    assert config["agent"]["reasoning_overrides"] == {
        "google/gemma-4-e4b": "low",
        "qwen/qwen3.5-9b": "none",
    }


# ---------------------------------------------------------------------------
# Şema: yanlış uyarı
# ---------------------------------------------------------------------------

def test_YANLIS_uyari_cikmiyor() -> None:
    """Komut "kaydedildi ama okunmayabilir" diyordu; oysa
    ``agent/agent_init.py`` bu haritayı gerçekten okuyor."""
    known, _ = _validate_config_key("agent.reasoning_overrides.qwen/qwen3.5-9b")

    assert known is True


def test_YAZIM_HATASI_hala_yakalaniyor() -> None:
    """Kapıyı açmak şemayı kapatmak değil."""
    assert _validate_config_key("agent.bilinmeyen")[0] is False
    assert _validate_config_key("tts.providr") == (False, "tts.provider")
