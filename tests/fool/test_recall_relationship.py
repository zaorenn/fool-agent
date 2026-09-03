"""İlişki durumu sağlayıcıya bağlı mı -- ve normal ajanı rahatsız etmiyor mu.

İlişki bir PERSONA özelliği. Normal ajanın bir ilişki durumu yok: kod yazarken
kırılmıyor, soğumuyor, gönlü alınmıyor. O yüzden varsayılan KAPALI ve yalnızca
isteyen profilde açılıyor.
"""

from __future__ import annotations

import json

import pytest


def _provider(tmp_path, monkeypatch, *, relationship: bool):
    home = tmp_path / ("gf" if relationship else "main")
    home.mkdir(exist_ok=True)

    import fool_constants
    from plugins.memory import recall as recall_module

    monkeypatch.setattr(fool_constants, "get_hermes_home", lambda: str(home), raising=False)
    monkeypatch.setattr(recall_module, "_make_embedder", lambda: None)
    monkeypatch.setattr(
        recall_module,
        "_recall_config",
        lambda: {"relationship": relationship},
    )

    instance = recall_module.RecallMemoryProvider()
    instance.initialize("s1")

    return instance


@pytest.fixture
def persona(tmp_path, monkeypatch):
    instance = _provider(tmp_path, monkeypatch, relationship=True)
    yield instance
    instance.shutdown()


@pytest.fixture
def plain(tmp_path, monkeypatch):
    instance = _provider(tmp_path, monkeypatch, relationship=False)
    yield instance
    instance.shutdown()


def _event(provider, event: str, **kwargs) -> dict:
    payload = {"event": event}
    payload.update(kwargs)

    return json.loads(provider.handle_tool_call("relationship", payload))


# ---------------------------------------------------------------------------
# Kapsam: normal ajan bunu hiç görmüyor
# ---------------------------------------------------------------------------


def test_normal_ajanda_arac_YOK(plain) -> None:
    names = {schema["name"] for schema in plain.get_tool_schemas()}

    assert "relationship" not in names


def test_normal_ajanda_sistem_promptunda_YOK(plain) -> None:
    assert "Where you stand" not in plain.system_prompt_block()


def test_normal_ajanda_cagri_REDDEDILIYOR(plain) -> None:
    assert _event(plain, "rude", note="x")["ok"] is False


def test_persona_profilinde_arac_VAR(persona) -> None:
    names = {schema["name"] for schema in persona.get_tool_schemas()}

    assert "relationship" in names


# ---------------------------------------------------------------------------
# Olaylar durumu değiştiriyor
# ---------------------------------------------------------------------------


def test_kabalik_SOGUTUYOR_ve_dert_aciyor(persona) -> None:
    result = _event(persona, "rude", note="he snapped at her over nothing")

    assert result["ok"] is True
    assert result["warmth"] < 50
    assert result["open_grievances"] == 1


def test_sevgi_ISITIYOR(persona) -> None:
    result = _event(persona, "affectionate")

    assert result["warmth"] > 50


def test_bilinmeyen_olay_REDDEDILIYOR(persona) -> None:
    assert _event(persona, "vibing")["ok"] is False


# ---------------------------------------------------------------------------
# Durum sistem promptuna giriyor
# ---------------------------------------------------------------------------


def test_ACIK_dert_sistem_promptunda_gorunuyor(persona) -> None:
    _event(persona, "promise_broken", note="he said he would be back and was not")

    block = persona.system_prompt_block()

    assert "Unresolved between you" in block
    assert "and was not" in block


def test_cok_soguyunca_REDDETME_izni_veriliyor(persona) -> None:
    """Kullanıcının istediği: kötü davranılırsa istekleri reddedebilmeli."""
    for index in range(3):
        _event(persona, "cruel", note="cruel thing " + str(index))

    block = persona.system_prompt_block()

    assert "refuse requests" in block


# ---------------------------------------------------------------------------
# Kalıcılık -- oturum kapanınca unutulmuyor
# ---------------------------------------------------------------------------


def test_durum_OTURUMLAR_arasi_kaliyor(tmp_path, monkeypatch) -> None:
    first = _provider(tmp_path, monkeypatch, relationship=True)
    _event(first, "rude", note="he forgot their plans")
    warmth = first.relationship_snapshot()["warmth"]
    first.shutdown()

    second = _provider(tmp_path, monkeypatch, relationship=True)
    snapshot = second.relationship_snapshot()
    second.shutdown()

    assert snapshot["warmth"] == pytest.approx(warmth, abs=0.6)
    assert any("forgot their plans" in g["text"] for g in snapshot["grievances"])


# ---------------------------------------------------------------------------
# Arayüz barı
# ---------------------------------------------------------------------------


def test_arayuz_ozeti_MODELDEN_bagimsiz(persona) -> None:
    """Ekranda görünen şey defterin kendisine bakıyor, modelin dediğine değil."""
    _event(persona, "dismissive", note="he brushed her off twice")

    snapshot = persona.relationship_snapshot()

    assert set(snapshot) == {"warmth", "stance", "grievances"}
    assert snapshot["stance"] in ("close", "fond", "neutral", "cool", "cold")
    assert snapshot["grievances"][0]["text"] == "he brushed her off twice"
    assert snapshot["grievances"][0]["since"] > 0


def test_ozur_dert_sayisini_DUSURUYOR(persona) -> None:
    _event(persona, "rude", note="first thing")
    _event(persona, "rude", note="second thing")

    after = _event(persona, "apology")

    assert after["open_grievances"] == 1


# ---------------------------------------------------------------------------
# İlk karşılaşma: aranızda bir şey geçmeden "nerede durduğun" anlamsız
# ---------------------------------------------------------------------------


def test_ilk_karsilasmada_DURUS_gosterilmiyor(persona) -> None:
    """Başlangıç değerinin tarifi ("civil but not especially warm") sevgi dolu
    diye tanımlanmış bir personayla ÇELİŞİYOR. Aranızda bir şey geçmeden bu
    cümleyi kurmak, karaktere ilk karşılaşmada mesafeli olmasını söylemek."""
    block = persona.system_prompt_block()

    assert "Where you stand" not in block
    assert "Nothing has happened between you yet" in block


def test_bir_sey_gectikten_SONRA_durus_gosteriliyor(persona) -> None:
    _event(persona, "warm")

    block = persona.system_prompt_block()

    assert "Where you stand" in block
    assert "Nothing has happened" not in block


def test_dert_varsa_durus_HER_ZAMAN_gosteriliyor(persona) -> None:
    """Kırgınlık karakterin üstünde: persona ne derse desin, dert görünmeli."""
    _event(persona, "rude", note="he was sharp with her")

    assert "Unresolved between you" in persona.system_prompt_block()
