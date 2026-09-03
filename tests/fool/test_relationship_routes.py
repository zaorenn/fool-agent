"""İlişki barının okuduğu uç.

İstenen: "arayüzde görünen ilişki durumu neye kızgın, ne moralini bozuyor,
neye trip atıyor görülsün."

İki kural burada sınanıyor ve ikisi de kolayca sessizce bozulabilir:
sıradan ajanda barın HİÇ görünmemesi, ve barın yoklanmasının zaman
farkındalığını BOZMAMASI.
"""

from __future__ import annotations

import json
import time

import pytest

from fool import relationship_routes


@pytest.fixture
def home(tmp_path, monkeypatch):
    import fool_constants

    monkeypatch.setattr(fool_constants, "get_hermes_home", lambda: str(tmp_path), raising=False)

    return tmp_path


def _enable(monkeypatch, value: bool) -> None:
    monkeypatch.setattr(relationship_routes, "_enabled", lambda: value)


def _store(home):
    from fool.recall_store import RecallStore

    path = home / "memories" / "recall.db"
    path.parent.mkdir(parents=True, exist_ok=True)

    return RecallStore(path, embedder=None)


# ---------------------------------------------------------------------------
# Kapsam
# ---------------------------------------------------------------------------


def test_persona_DEGILSE_bar_kapali(home, monkeypatch) -> None:
    """Sıradan ajanın ilişki durumu yok; bar orada hiç görünmemeli."""
    _enable(monkeypatch, False)

    assert relationship_routes.snapshot() == {"enabled": False}


def test_ayar_okunuyor(home, monkeypatch) -> None:
    from fool_cli import config as config_module

    monkeypatch.setattr(
        config_module,
        "load_config_readonly",
        lambda: {"memory": {"recall": {"relationship": True}}},
    )

    assert relationship_routes._enabled() is True


def test_ayar_YOKSA_kapali(home, monkeypatch) -> None:
    from fool_cli import config as config_module

    monkeypatch.setattr(config_module, "load_config_readonly", lambda: {})

    assert relationship_routes._enabled() is False


# ---------------------------------------------------------------------------
# Defter yokken
# ---------------------------------------------------------------------------


def test_defter_YOKKEN_baslangic_hali(home, monkeypatch) -> None:
    _enable(monkeypatch, True)

    payload = relationship_routes.snapshot()

    assert payload["enabled"] is True
    assert payload["started"] is False
    assert payload["grievances"] == []
    assert payload["stance"] == "neutral"


def test_bozuk_defter_PATLAMIYOR(home, monkeypatch) -> None:
    _enable(monkeypatch, True)
    path = home / "memories" / "recall.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a database")

    assert relationship_routes.snapshot()["enabled"] is True


# ---------------------------------------------------------------------------
# Gerçek durum
# ---------------------------------------------------------------------------


def test_dertler_ve_durus_gorunuyor(home, monkeypatch) -> None:
    _enable(monkeypatch, True)

    from fool import relationship as relationship_module

    state = relationship_module.Relationship()
    state.record("cruel", note="he told her she was worthless")
    state.record("dismissive", note="he brushed her off")

    store = _store(home)
    store.save_relationship(relationship_module.to_dict(state))
    store.close()

    payload = relationship_routes.snapshot()

    assert payload["started"] is True
    assert payload["warmth"] < 50
    assert payload["stance"] in ("cool", "cold")
    assert payload["label"]
    assert payload["summary"]
    assert [g["text"] for g in payload["grievances"]] == [
        "he told her she was worthless",
        "he brushed her off",
    ]


def test_dertler_AGIRLIGA_gore_siralaniyor(home, monkeypatch) -> None:
    """Ekranda ilk görünen şey, onu en çok üzen şey olmalı."""
    _enable(monkeypatch, True)

    from fool import relationship as relationship_module

    state = relationship_module.Relationship()
    state.record("ignored", note="small thing")
    state.record("cruel", note="big thing")

    store = _store(home)
    store.save_relationship(relationship_module.to_dict(state))
    store.close()

    grievances = relationship_routes.snapshot()["grievances"]

    assert grievances[0]["text"] == "big thing"
    assert grievances[0]["weight"] > grievances[1]["weight"]


def test_KAPANAN_dert_ekrandan_dusuyor(home, monkeypatch) -> None:
    _enable(monkeypatch, True)

    from fool import relationship as relationship_module

    state = relationship_module.Relationship()
    state.record("rude", note="the one thing")
    state.record("apology")

    store = _store(home)
    store.save_relationship(relationship_module.to_dict(state))
    store.close()

    assert relationship_routes.snapshot()["grievances"] == []


def test_arada_gecen_zaman_CURUTULMUS_geliyor(home, monkeypatch) -> None:
    """Bar ile promptun gördüğü sıcaklık aynı olmalı: ikisi de çürütüyor."""
    _enable(monkeypatch, True)

    from fool import relationship as relationship_module

    long_ago = time.time() - 40 * 86400.0
    state = relationship_module.Relationship()
    state.record("cruel", note="x", now=long_ago)
    raw = relationship_module.to_dict(state)

    store = _store(home)
    store.save_relationship(raw)
    store.close()

    assert relationship_routes.snapshot()["warmth"] > raw["warmth"]


# ---------------------------------------------------------------------------
# Yoklama zaman farkındalığını BOZMUYOR
# ---------------------------------------------------------------------------


def test_yoklama_GORULDU_damgasi_atmiyor(home, monkeypatch) -> None:
    """Bar saniyede bir yoklanıyor.

    Damga atsaydı ``last_seen`` sürekli tazelenir ve "dün gece iyi geceler
    demeden gittin" HİÇBİR ZAMAN gerçekleşmezdi -- kullanıcının açıkça
    istediği davranış.
    """
    _enable(monkeypatch, True)

    store = _store(home)
    store.touch_seen(now=1000.0)
    store.close()

    for _ in range(3):
        relationship_routes.snapshot()

    store = _store(home)
    seen = store.last_seen()
    store.close()

    assert seen == 1000.0


def test_yoklama_deftere_YAZMIYOR(home, monkeypatch) -> None:
    _enable(monkeypatch, True)

    from fool import relationship as relationship_module

    state = relationship_module.Relationship()
    state.record("rude", note="x")
    raw = json.dumps(relationship_module.to_dict(state), ensure_ascii=False)

    store = _store(home)
    store.save_relationship(json.loads(raw))
    store.close()

    relationship_routes.snapshot()

    store = _store(home)
    after = json.dumps(store.load_relationship(), ensure_ascii=False)
    store.close()

    assert after == raw


# ---------------------------------------------------------------------------
# Tanışma selamının kapısı
# ---------------------------------------------------------------------------


def test_hic_konusulmamissa_met_YANLIS(home, monkeypatch) -> None:
    _enable(monkeypatch, True)

    assert relationship_routes.snapshot()["met"] is False


def test_defter_varken_ama_hic_gorulmemisken_met_YANLIS(home, monkeypatch) -> None:
    _enable(monkeypatch, True)
    _store(home).close()

    assert relationship_routes.snapshot()["met"] is False


def test_bir_kez_gorulduyse_met_DOGRU(home, monkeypatch) -> None:
    """Sağlayıcı ilk turun sistem promptunu kurarken damgayı atıyor; yani
    selamın kendi turu bile kapıyı kapatıyor."""
    _enable(monkeypatch, True)
    store = _store(home)
    store.touch_seen(now=1000.0)
    store.close()

    assert relationship_routes.snapshot()["met"] is True
