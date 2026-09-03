"""Recall sağlayıcısı: hafıza ajana BAĞLI mı.

Depo tek başına çalışıyor olabilir ve ajan yine hiçbir şey hatırlamayabilir --
aradaki bağ ``MemoryProvider`` dikişi. Bu sınav o bağı tutuyor: geri getirme
tur başına enjekte ediliyor mu, yazma aracı gerçekten yazıyor mu, zaman bağlamı
sistem promptuna giriyor mu.

FOOL_HOME İZOLE: sınav kullanıcının gerçek hafızasına dokunmamalı.
"""

from __future__ import annotations

import json
import time

import pytest


@pytest.fixture
def provider(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()

    import fool_constants

    monkeypatch.setenv("FOOL_HOME", str(home))
    monkeypatch.setattr(fool_constants, "get_hermes_home", lambda: str(home), raising=False)

    # Gomme ucu YOK: sinav agi degil sozlesmeyi olcmeli.
    from plugins.memory import recall as recall_module

    monkeypatch.setattr(recall_module, "_make_embedder", lambda: None)

    instance = recall_module.RecallMemoryProvider()
    instance.initialize("session-1")

    yield instance

    instance.shutdown()


def _remember(provider, text: str, **kwargs) -> dict:
    payload = {"text": text}
    payload.update(kwargs)

    return json.loads(provider.handle_tool_call("remember", payload))


# ---------------------------------------------------------------------------
# Kimlik ve keşif
# ---------------------------------------------------------------------------


def test_yerel_saglayici_HER_ZAMAN_kullanilabilir(provider) -> None:
    """Bulut anahtarı yok, kurulum yok -- sqlite her zaman var."""
    assert provider.name == "recall"
    assert provider.is_available() is True
    assert provider.unavailable_reason() == ""


def test_uc_arac_sunuluyor(provider) -> None:
    names = {schema["name"] for schema in provider.get_tool_schemas()}

    assert names == {"remember", "recall", "forget"}


# ---------------------------------------------------------------------------
# Yazma
# ---------------------------------------------------------------------------


def test_remember_gercekten_yaziyor(provider) -> None:
    result = _remember(provider, "User's cat is named Pamuk", importance=0.7)

    assert result["ok"] is True
    assert result["stored"] is True
    assert result["id"]


def test_bos_metin_REDDEDILIYOR(provider) -> None:
    assert json.loads(provider.handle_tool_call("remember", {"text": "   "}))["ok"] is False


def test_TEKRAR_sessizce_basarili_demiyor(provider) -> None:
    """Sessizce "tamam" demek modeli aynı şeyi tekrar tekrar yazmaya iter."""
    _remember(provider, "User's cat is named Pamuk")
    second = _remember(provider, "User's cat is named Pamuk")

    assert second["ok"] is True
    assert second["stored"] is False
    assert second["reason"] == "already known"


# ---------------------------------------------------------------------------
# Okuma
# ---------------------------------------------------------------------------


def test_recall_yazilani_buluyor(provider) -> None:
    _remember(provider, "User's cat is named Pamuk")

    found = json.loads(provider.handle_tool_call("recall", {"query": "Pamuk"}))

    assert found["ok"] is True
    assert any("Pamuk" in m["text"] for m in found["memories"])


def test_recall_KAC_GUN_once_oldugunu_soyluyor(provider) -> None:
    _remember(provider, "User adopted a cat")

    found = json.loads(provider.handle_tool_call("recall", {"query": "cat"}))

    assert "days_ago" in found["memories"][0]


def test_forget_siliyor(provider) -> None:
    stored = _remember(provider, "A detail that turned out to be wrong")

    assert json.loads(provider.handle_tool_call("forget", {"id": stored["id"]}))["ok"] is True

    found = json.loads(provider.handle_tool_call("recall", {"query": "wrong"}))

    assert not any(m["id"] == stored["id"] for m in found["memories"])


def test_bilinmeyen_arac_HATA_donuyor(provider) -> None:
    assert json.loads(provider.handle_tool_call("nonsense", {}))["ok"] is False


# ---------------------------------------------------------------------------
# Tur başına geri getirme -- asıl bağ
# ---------------------------------------------------------------------------


def test_prefetch_ILGILI_aniyi_enjekte_ediyor(provider) -> None:
    _remember(provider, "User's cat is named Pamuk")

    block = provider.prefetch("how is the cat doing")

    assert "Pamuk" in block


def test_bos_depoda_prefetch_BOS(provider) -> None:
    assert provider.prefetch("anything at all") == ""


def test_bos_sorgu_geri_getirme_TETIKLEMIYOR(provider) -> None:
    _remember(provider, "User's cat is named Pamuk")

    assert provider.prefetch("   ") == ""


def test_geri_getirme_ARAYUZE_bildiriliyor(provider) -> None:
    """Kullanıcı hafızanın kullanıldığını modelin söylemesine bakmadan görmeli."""
    _remember(provider, "User's cat is named Pamuk")
    provider.prefetch("how is the cat")

    status = provider.recall_status()

    assert status is not None
    assert status.count >= 1


def test_hicbir_sey_enjekte_edilmediyse_gosterge_YOK(provider) -> None:
    provider.prefetch("how is the cat")

    assert provider.recall_status() is None


# ---------------------------------------------------------------------------
# Zaman farkındalığı
# ---------------------------------------------------------------------------


def test_sistem_promptu_ZAMANI_tasiyor(provider) -> None:
    block = provider.system_prompt_block()

    assert "It is " in block


def test_ILK_karsilasma_soyleniyor(provider) -> None:
    assert "never spoken" in provider.system_prompt_block()


def test_ikinci_oturum_ilk_karsilasma_DEMIYOR(provider) -> None:
    provider.system_prompt_block()

    assert "never spoken" not in provider.system_prompt_block()


def test_VEDA_kaydediliyor(provider) -> None:
    provider.sync_turn("good night, talk tomorrow", "sleep well")

    assert provider._store.last_farewell() is not None


def test_siradan_mesaj_VEDA_sayilmiyor(provider) -> None:
    """Yanlış pozitif bir veda, ertesi sabah hak edilmiş bir sitemi yutardı."""
    provider.sync_turn("last night the build failed", "let me look")

    assert provider._store.last_farewell() is None


def test_turkce_veda_da_taniniyor(provider) -> None:
    provider.sync_turn("iyi geceler", "iyi geceler")

    assert provider._store.last_farewell() is not None


# ---------------------------------------------------------------------------
# Dayanıklılık
# ---------------------------------------------------------------------------


def test_depo_YOKSA_hicbir_sey_patlamiyor(monkeypatch) -> None:
    """Hafıza bir iyileştirme; kurulamazsa ajan çalışmaya devam etmeli."""
    from plugins.memory import recall as recall_module

    instance = recall_module.RecallMemoryProvider()
    instance._store = None

    assert instance.prefetch("anything") == ""
    assert instance.system_prompt_block() == ""
    assert json.loads(instance.handle_tool_call("remember", {"text": "x"}))["ok"] is False

    instance.sync_turn("good night", "night")
    instance.on_session_end([])
    instance.shutdown()


def test_iki_PROFIL_ayri_dosya_kullaniyor(tmp_path, monkeypatch) -> None:
    """Kullanıcının istediği ayrım: normal ajan ve persona ayrı hafızalar."""
    import fool_constants
    from plugins.memory import recall as recall_module

    monkeypatch.setattr(recall_module, "_make_embedder", lambda: None)
    paths = []

    for profile in ("main", "persona"):
        home = tmp_path / profile
        home.mkdir()
        monkeypatch.setattr(fool_constants, "get_hermes_home", lambda h=str(home): h, raising=False)

        instance = recall_module.RecallMemoryProvider()
        instance.initialize("s")
        paths.append(str(instance._store.path))
        instance.shutdown()

    assert paths[0] != paths[1]


# ---------------------------------------------------------------------------
# Tanışma soruları ve düzeltmeler
# ---------------------------------------------------------------------------


def test_sistem_promptunda_TEK_konu_soruluyor(provider) -> None:
    block = provider.system_prompt_block()

    assert "You still do not know" in block
    assert block.count("You still do not know") == 1


def test_konu_IKINCI_oturumda_tekrarlanmiyor(provider) -> None:
    """Aynı soruyu her açılışta sormak, dinlemediğini göstermenin en hızlı
    yolu. Sorulma kaydı deftere yazılıyor."""
    first = provider.system_prompt_block()
    second = provider.system_prompt_block()

    asked = [line for line in first.split("\n") if "You still do not know" in line]
    again = [line for line in second.split("\n") if "You still do not know" in line]

    assert asked and again
    assert asked[0] != again[0]


def test_curiosity_KAPATILABILIYOR(tmp_path, monkeypatch) -> None:
    import fool_constants
    from plugins.memory import recall as recall_module

    monkeypatch.setattr(fool_constants, "get_hermes_home", lambda: str(tmp_path), raising=False)
    monkeypatch.setattr(recall_module, "_make_embedder", lambda: None)
    monkeypatch.setattr(recall_module, "_recall_config", lambda: {"curiosity": False})

    instance = recall_module.RecallMemoryProvider()
    instance.initialize("s1")

    try:
        assert "You still do not know" not in instance.system_prompt_block()
    finally:
        instance.shutdown()


def test_duzeltme_YANLIS_olani_bastiriyor(provider) -> None:
    """Unutulmuş bir tercih küçük bir kayıp; unutulmuş bir düzeltme AYNI
    HATANIN TEKRARI.

    Düzeltme önce sıralanıyor (``CORRECTION_BONUS``), ve düzelttiği cümleyle
    fazla benzeştiği için eskisi aynı bloğa girmiyor -- yani model yanlış
    olanı hiç görmüyor."""
    provider.handle_tool_call("remember", {"text": "he prefers coffee in the morning"})
    provider.handle_tool_call(
        "remember",
        {"text": "he prefers coffee at night, not in the morning", "kind": "correction"},
    )

    block = provider.prefetch("coffee morning prefers")

    assert "not in the morning" in block
    assert "- (just now) he prefers coffee in the morning" not in block


def test_duzeltme_AYRI_bir_anidan_once_geliyor(provider) -> None:
    """Bonusun kendisi: eşit ilgideki bir yarışı düzeltme kazanıyor."""
    provider.handle_tool_call("remember", {"text": "the deploy script lives in scripts"})
    provider.handle_tool_call(
        "remember",
        {"text": "deploy runs from the makefile, not the script", "kind": "correction"},
    )

    block = provider.prefetch("deploy script")

    assert block.index("not the script") < block.index("lives in scripts")
