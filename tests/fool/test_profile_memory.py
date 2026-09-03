"""Kullanıcı hakkındaki bilgiler izinle yazılır ve iz bırakır.

Bugün ``memory(action=add, target=user, ...)`` ``USER.md``ye doğrudan
yazıyor: ne sorulan bir izin var ne de sonradan bakılabilecek bir kayıt.
Kullanıcının kurulu dosyasında bu şekilde birikmiş satırlar var (favori
şarkısı, indirilenler klasörünün yolu) ve hiçbiri için sorulmadı.

Sorun "gizli" olması değil -- dosya kullanıcının kendi makinesinde. Sorun
GÖRÜNMEZ olması: kullanıcı ne bilindiğini bilmiyor.
"""

from __future__ import annotations

import pytest

from fool import profile_memory as pm


# ---------------------------------------------------------------------------
# Kip çözümlemesi
# ---------------------------------------------------------------------------

def test_varsayilan_kip_soruyor() -> None:
    assert pm.consent_mode({}) == "ask"


@pytest.mark.parametrize("mode", ["always", "ask", "never"])
def test_tanimli_kipler_okunuyor(mode: str) -> None:
    assert pm.consent_mode({"memory": {"profile_consent": mode}}) == mode


def test_buyuk_harf_ve_bosluk_sorun_degil() -> None:
    assert pm.consent_mode({"memory": {"profile_consent": "  NEVER "}}) == "never"


def test_taninmayan_kip_varsayilana_dusuyor() -> None:
    """Yazım tipoyla serbest kalmamalı."""
    assert pm.consent_mode({"memory": {"profile_consent": "alwyas"}}) == "ask"


def test_bozuk_yapilandirmada_cokmuyor() -> None:
    for bad in (None, [], "nonsense", {"memory": 7}, {"memory": {"profile_consent": None}}):
        assert pm.consent_mode(bad) == "ask"


# ---------------------------------------------------------------------------
# Yazım kararı
# ---------------------------------------------------------------------------

def test_ask_kipinde_izinsiz_yazim_reddediliyor() -> None:
    reason = pm.check_profile_write("ask", None)

    assert reason is not None
    assert "consent=granted" in reason


def test_red_mesaji_NE_YAPACAGINI_soyluyor() -> None:
    """Yalnızca "reddedildi" demek modeli aynı çağrıyı tekrar etmeye iterdi."""
    reason = pm.check_profile_write("ask", None)

    assert "Ask them first" in reason


@pytest.mark.parametrize("consent", ["granted", "GRANTED", " yes ", "true", True])
def test_ask_kipinde_izinle_yazim_geciyor(consent) -> None:
    assert pm.check_profile_write("ask", consent) is None


@pytest.mark.parametrize("consent", ["", "maybe", "no", False, 0, None])
def test_belirsiz_onay_izin_sayilmiyor(consent) -> None:
    """"Belki" izin değildir; kapalı taraf güvenli taraf."""
    assert pm.check_profile_write("ask", consent) is not None


def test_always_kipinde_izin_aranmiyor() -> None:
    """Eski davranışı isteyen kullanıcı onu alabilmeli."""
    assert pm.check_profile_write("always", None) is None


def test_never_kipinde_izin_bile_yetmiyor() -> None:
    """Sert kapatma sert olmalı; yoksa kapatma değil öneri olurdu."""
    reason = pm.check_profile_write("never", "granted")

    assert reason is not None
    assert "never" in reason


def test_never_mesaji_nasil_acilacagini_soyluyor() -> None:
    assert "fool config set" in pm.check_profile_write("never", None)


# ---------------------------------------------------------------------------
# Günlük
# ---------------------------------------------------------------------------

def test_kayit_yazilip_okunuyor(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pm, "journal_path", lambda: tmp_path / "j.jsonl")

    pm.record("Favori rengi mavi", mode="ask", consent="granted")
    entries = pm.read_journal()

    assert len(entries) == 1
    assert entries[0]["content"] == "Favori rengi mavi"
    assert entries[0]["consent"] == "granted"
    assert entries[0]["at"]


def test_kayitlar_birikiyor(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pm, "journal_path", lambda: tmp_path / "j.jsonl")

    for i in range(3):
        pm.record(f"bilgi {i}", mode="ask", consent="granted")

    assert len(pm.read_journal()) == 3


def test_gunluk_yazimi_ENGELLEMIYOR(tmp_path, monkeypatch) -> None:
    """Bir kayıt hatası, kullanıcının isteyerek verdiği bilgiyi kaybettirmemeli."""
    def _boom():
        raise OSError("disk full")

    monkeypatch.setattr(pm, "journal_path", _boom)

    pm.record("bir sey", mode="ask")  # istisna FIRLATMAMALI


def test_gunluk_yoksa_bos_liste(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pm, "journal_path", lambda: tmp_path / "yok.jsonl")

    assert pm.read_journal() == []


def test_bozuk_satir_digerlerini_dusurmuyor(tmp_path, monkeypatch) -> None:
    path = tmp_path / "j.jsonl"
    path.write_text('{"content": "iyi"}\n{bozuk\n{"content": "de iyi"}\n', encoding="utf-8")
    monkeypatch.setattr(pm, "journal_path", lambda: path)

    assert [e["content"] for e in pm.read_journal()] == ["iyi", "de iyi"]


def test_cok_uzun_icerik_kirpiliyor(tmp_path, monkeypatch) -> None:
    """Günlük bir kopya deposu değil; sınırsız büyümemeli."""
    monkeypatch.setattr(pm, "journal_path", lambda: tmp_path / "j.jsonl")

    pm.record("x" * 5000, mode="always")

    assert len(pm.read_journal()[0]["content"]) <= 2000


# ---------------------------------------------------------------------------
# Rehber
# ---------------------------------------------------------------------------

def test_rehber_kullaniciya_sormayi_soyluyor() -> None:
    text = pm.PROFILE_MEMORY_GUIDANCE

    assert "ASK THEM" in text
    assert "consent=granted" in text


def test_rehber_kullanicinin_kendi_istegini_muaf_tutuyor() -> None:
    """"Şunu unutma" demek zaten izindir; tekrar sormak sinir bozucu olurdu."""
    flat = ' '.join(pm.PROFILE_MEMORY_GUIDANCE.split())

    assert 'remember that I' in flat


def test_rehber_sistem_promptuna_giriyor() -> None:
    from fool import guidance

    assert any(pm.PROFILE_MEMORY_GUIDANCE in block for block in guidance.blocks())


# ---------------------------------------------------------------------------
# Gerçek araç yolu
# ---------------------------------------------------------------------------

class _FakeStore:
    """``memory_tool``un dokunduğu en küçük yüzey."""

    def __init__(self) -> None:
        self.writes: list = []

    def add(self, target, content):  # noqa: D102
        self.writes.append((target, content))
        return {"ok": True}

    def apply_batch(self, target, operations):  # noqa: D102
        self.writes.append((target, operations))
        return {"ok": True}


@pytest.fixture
def tool(monkeypatch, tmp_path):
    from tools import memory_tool as mt

    monkeypatch.setattr(pm, "journal_path", lambda: tmp_path / "j.jsonl")
    return mt


def _cfg(monkeypatch, mode: str) -> None:
    import fool_cli.config as cfg

    monkeypatch.setattr(cfg, "load_config", lambda *a, **k: {"memory": {"profile_consent": mode}})


def test_arac_izinsiz_profil_yazimini_reddediyor(tool, monkeypatch) -> None:
    _cfg(monkeypatch, "ask")
    store = _FakeStore()

    out = tool.memory_tool(action="add", target="user", content="Adi Arda", store=store)

    assert "permission" in out
    assert not store.writes, "reddedilen yazim yine de diske gitti"


def test_arac_izinli_profil_yazimini_geciriyor(tool, monkeypatch) -> None:
    _cfg(monkeypatch, "ask")
    store = _FakeStore()

    tool.memory_tool(
        action="add", target="user", content="Adi Arda", consent="granted", store=store
    )

    assert store.writes, "izinli yazim gecmedi"


def test_arac_kendi_notlarina_karismıyor(tool, monkeypatch) -> None:
    """``target=memory`` ajanın kendi notu; kullanıcı profili değil."""
    _cfg(monkeypatch, "ask")
    store = _FakeStore()

    tool.memory_tool(action="add", target="memory", content="not", store=store)

    assert store.writes


def test_arac_toplu_yazimi_da_kapsiyor(tool, monkeypatch) -> None:
    """Tek-op kapatılıp toplu yol açık kalsaydı kapı işe yaramazdı."""
    _cfg(monkeypatch, "ask")
    store = _FakeStore()

    out = tool.memory_tool(
        target="user",
        operations=[{"action": "add", "content": "Adi Arda"}],
        store=store,
    )

    assert "permission" in out
    assert not store.writes


def test_izinli_yazim_gunluge_dusuyor(tool, monkeypatch) -> None:
    _cfg(monkeypatch, "ask")

    tool.memory_tool(
        action="add", target="user", content="Adi Arda", consent="granted", store=_FakeStore()
    )

    assert [e["content"] for e in pm.read_journal()] == ["Adi Arda"]


def test_never_kipinde_arac_hicbir_sey_yazmiyor(tool, monkeypatch) -> None:
    _cfg(monkeypatch, "never")
    store = _FakeStore()

    out = tool.memory_tool(
        action="add", target="user", content="Adi Arda", consent="granted", store=store
    )

    assert "turned off" in out
    assert not store.writes
