"""Chat ↔ Cowork kipi bir OTURUM özelliği ve kalıcı olmalı.

Kip, oturumun ``source`` alanında yaşıyor. Yeni bir tesisat değil: ağ geçidi
zaten ``_session_source(session)`` -> ``platform_override`` ->
``fool.session_scope.scope_toolsets`` zincirini koşuyor, yani ``source``ü
``chat`` olan bir oturum kendiliğinden okuyan araç kümesini alıyor.

Kullanıcının kararı: kip açık bir sohbette de DEĞİŞTİRİLEBİLSİN, ama arayüz
önce sorsun -- çünkü değişimin bir bedeli var (aşağıya bak).
"""

from __future__ import annotations

import pytest

from fool import session_scope as ss


@pytest.fixture
def db(tmp_path):
    from fool_state import SessionDB

    return SessionDB(db_path=tmp_path / "state.db")


def test_kaynak_DEGISTIRILEBILIYOR(db) -> None:
    db.create_session("s1", source="desktop")

    assert db.update_session_source("s1", "chat") is True
    assert (db.get_session("s1") or {})["source"] == "chat"


def test_geri_donus_de_calisiyor(db) -> None:
    """Chat'e geçmek tek yönlü bir kapı olmamalı."""
    db.create_session("s1", source="chat")
    db.update_session_source("s1", "desktop")

    assert (db.get_session("s1") or {})["source"] == "desktop"


def test_OLMAYAN_satir_False_donuyor(db) -> None:
    """Henüz kaydedilmemiş taslak için doğru davranış.

    Canlı oturum çağıran tarafta zaten güncelleniyor; satır ilk yazıldığında
    kipi devralıyor. Burada patlamak, kullanıcının daha tek mesaj yazmadığı
    bir sohbette kip değiştirmesini hata haline getirirdi.
    """
    assert db.update_session_source("yok", "chat") is False


def test_BOS_deger_yazilmiyor(db) -> None:
    """Boş bir ``source`` kapsam çözümlemesini bozar: ağ geçidi onu okuyup
    hangi araç kümesini vereceğine karar veriyor."""
    db.create_session("s1", source="desktop")

    assert db.update_session_source("s1", "") is False
    assert (db.get_session("s1") or {})["source"] == "desktop"


def test_kaynak_ARAC_KUMESINI_belirliyor() -> None:
    """Zincirin kendisi. ``source`` yalnızca bir etiket değil."""
    from tui_gateway.server import _load_enabled_toolsets

    assert _load_enabled_toolsets("chat") == list(ss.CHAT_TOOLSETS)
    # ``cowork`` ADI ``source``a yazılmıyor -- ``desktop`` yazılıyor, çünkü
    # ``scope_toolsets`` onu tanımadığında olağan platform çözümlemesi geçerli
    # kalmalı. Tanınmayan bir ad da aynı sonucu verirdi, ama kasıtlı olan bu.
    assert ss.scope_toolsets("cowork") is None
    assert ss.scope_toolsets("desktop") is None


def test_kip_komutu_TANIMLI() -> None:
    """Ağ geçidi komutu kayıtlı mı?"""
    from tui_gateway import methods_session  # noqa: F401
    from tui_gateway.server import _methods

    assert "session.mode" in _methods


def test_kip_komutu_BILINMEYEN_kipi_reddediyor() -> None:
    """Serbest metin ``source``a yazılsaydı, kapsam çözümlemesi sessizce
    değişirdi -- kullanıcının hiç istemediği bir araç kümesine düşerdi."""
    from tui_gateway import methods_session  # noqa: F401
    from tui_gateway.server import _methods

    result = _methods["session.mode"](1, {"session_key": "s1", "mode": "her-sey"})

    assert "error" in result


def test_kip_komutu_ANAHTAR_istiyor() -> None:
    from tui_gateway import methods_session  # noqa: F401
    from tui_gateway.server import _methods

    result = _methods["session.mode"](1, {"mode": "chat"})

    assert "error" in result


def test_degisim_AJANI_dusuruyor() -> None:
    """Bedelin kaynağı, ve neden arayüz soruyor.

    Araç şemaları donmuş sistem promptunun parçası ve prompt önbelleği onun
    üzerine kurulu. Kümeyi değiştirip aynı ajanı sürdürmek, modele o turda
    sahip OLMADIĞI araçları göstermek olurdu -- daha kötüsü, çağırabileceğini
    sanması. Canlı ajan bırakılıyor; sonraki tur yeni kümeyle kuruluyor.
    """
    from pathlib import Path

    from tui_gateway import methods_session

    source = Path(methods_session.__file__).read_text(encoding="utf-8")
    handler = source[source.index('@method("session.mode")') :]
    handler = handler[: handler.index("@method(", 10)]

    assert 'sess["agent"] = None' in handler
    assert 'sess["source"] = source' in handler
