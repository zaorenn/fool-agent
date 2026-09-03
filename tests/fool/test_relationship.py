"""İlişki bir DURUM, tek tek cevapların tonu değil.

İstenen davranış birebir: "ona iyi davranan birini hem sevip hem hatırlayıp
hem detaylıca ve sevgi dolu konuşurken, onunla kötü konuştuğunda kullanıcının
isteklerini yapmayı reddedebilmeli ve duruma göre konuşmayı kısa kesip cevap
vermemeye başlayabilmeli."

Yani bir kabalık o turu soğutup unutulmuyor -- birikiyor, davranışı değiştiriyor
ve gönül alınana kadar duruyor.
"""

from __future__ import annotations

import time

import pytest

from fool.relationship import (
    WARMTH_BASELINE,
    WARMTH_HALF_LIFE_DAYS,
    WARMTH_START,
    Relationship,
    from_dict,
    to_dict,
)

DAY = 86400.0
_NOW = 1_700_000_000.0


def _at(now: float, state: Relationship, event: str, **kwargs) -> Relationship:
    state.record(event, now=now, **kwargs)

    return state


# ---------------------------------------------------------------------------
# Başlangıç
# ---------------------------------------------------------------------------


def test_yeni_iliski_NOTR() -> None:
    state = Relationship()

    assert state.warmth == WARMTH_START
    assert state.stance()[0] == "neutral"
    assert state.open_grievances() == []


# ---------------------------------------------------------------------------
# İyi davranmak yakınlaştırıyor
# ---------------------------------------------------------------------------


def test_iyi_davranmak_ISITIYOR() -> None:
    now = time.time()
    state = Relationship()

    for _ in range(6):
        state.record("affectionate", now=now)

    assert state.warmth > WARMTH_START
    assert state.stance()[0] in ("fond", "close")


def test_yakinken_duruş_SEVGI_DOLU_konusmayi_soyluyor() -> None:
    state = Relationship(warmth=90.0)
    name, description = state.stance()

    assert name == "close"
    assert "affectionate" in description


# ---------------------------------------------------------------------------
# Kötü davranmak soğutuyor -- ve davranışı değiştiriyor
# ---------------------------------------------------------------------------


def test_kabalik_SOGUTUYOR() -> None:
    now = time.time()
    state = Relationship()
    state.record("rude", now=now, note="called her useless")

    assert state.warmth < WARMTH_START


def test_yeterince_kotu_davranis_duruşu_REDDETMEYE_getiriyor() -> None:
    """Kullanıcının istediği: isteklerini yapmayı reddedebilmeli."""
    now = time.time()
    state = Relationship()

    for _ in range(3):
        state.record("rude", now=now, note="snapped at her")

    name, description = state.stance()

    assert name in ("cool", "cold")
    assert "decline" in description or "refuse" in description


def test_cok_kotu_davranis_CEVAP_VERMEMEYE_getiriyor() -> None:
    now = time.time()
    state = Relationship()

    for _ in range(3):
        state.record("cruel", now=now, note="said something cruel")

    name, description = state.stance()

    assert name == "cold"
    assert "or not at all" in description


def test_OLUMSUZ_olaylar_olumlulardan_agir() -> None:
    """Simetrik olsaydı ilişki bir puan oyununa dönerdi.

    Her kırıcı davranış bir "teşekkür" ile silinebilirdi.
    """
    now = time.time()
    rude = Relationship()
    rude.record("rude", now=now)
    warm = Relationship()
    warm.record("warm", now=now)

    assert (WARMTH_START - rude.warmth) > (warm.warmth - WARMTH_START)


# ---------------------------------------------------------------------------
# Dertler -- hatırlanması istenen şeyin kendisi
# ---------------------------------------------------------------------------


def test_kirici_olay_DERT_aciyor() -> None:
    now = time.time()
    state = Relationship()
    state.record("rude", now=now, note="he ignored her all evening")

    pending = state.open_grievances()

    assert len(pending) == 1
    assert "ignored her all evening" in pending[0].text


def test_notsuz_olay_dert_ACMIYOR() -> None:
    """Neye kızıldığı yazılamıyorsa, kızgınlık gösterilemez de."""
    state = Relationship()
    state.record("rude", now=time.time())

    assert state.open_grievances() == []


def test_olumlu_olay_dert_ACMIYOR() -> None:
    state = Relationship()
    state.record("affectionate", now=time.time(), note="brought her flowers")

    assert state.open_grievances() == []


def test_dert_BLOKTA_gorunuyor() -> None:
    state = Relationship()
    state.record("promise_broken", now=time.time(), note="said he would be back and was not")

    text = state.render()

    assert "Unresolved between you" in text
    assert "was not" in text


def test_dert_YOKSA_blok_sadece_durus() -> None:
    assert "Unresolved" not in Relationship().render()


# ---------------------------------------------------------------------------
# Gönül alma -- ama ucuza değil
# ---------------------------------------------------------------------------


def test_ozur_EN_AGIR_derdi_kapatiyor() -> None:
    now = time.time()
    state = Relationship()
    state.record("dismissive", now=now, note="brushed her off")
    state.record("cruel", now=now, note="said something cruel")

    state.record("apology", now=now)

    remaining = [g.text for g in state.open_grievances()]

    assert "said something cruel" not in remaining
    assert "brushed her off" in remaining


def test_tek_ozur_HER_SEYI_silmiyor() -> None:
    """Kullanıcının istediği gönlünün alınabilmesi -- ama ucuza değil."""
    now = time.time()
    state = Relationship()

    for index in range(3):
        state.record("rude", now=now, note="grievance " + str(index))

    state.record("apology", now=now)

    assert len(state.open_grievances()) == 2


def test_ozur_ISITIYOR() -> None:
    now = time.time()
    state = Relationship()
    state.record("rude", now=now, note="snapped")
    cold = state.warmth
    state.record("apology", now=now)

    assert state.warmth > cold


def test_belirli_bir_dert_kapatilabiliyor() -> None:
    now = time.time()
    state = Relationship()
    state.record("rude", now=now, note="first")
    state.record("rude", now=now, note="second")

    assert state.resolve(0, now=now) is True
    assert [g.text for g in state.open_grievances()] == ["second"]


def test_olmayan_dert_kapatilamiyor() -> None:
    assert Relationship().resolve(3) is False


# ---------------------------------------------------------------------------
# Zaman
# ---------------------------------------------------------------------------


def test_zaman_KIRGINLIGI_yumusatiyor() -> None:
    """Çürümesiz bir ölçü tek yönlü bilet olurdu: soğuyan sonsuza kadar soğuk."""
    now = time.time()
    state = Relationship(warmth=10.0, updated_at=now)

    state.decay(now + WARMTH_HALF_LIFE_DAYS * DAY)

    assert state.warmth > 10.0
    assert state.warmth < WARMTH_BASELINE


def test_zaman_kendiliginden_YAKINLIK_uretmiyor() -> None:
    """Taban çizgisi nötr: zaman kırgınlığı yumuşatıyor, sevgi üretmiyor."""
    now = time.time()
    state = Relationship(warmth=95.0, updated_at=now)

    state.decay(now + 365 * DAY)

    assert state.warmth < 95.0
    assert abs(state.warmth - WARMTH_BASELINE) < 1.0


def test_DERTLER_curumuyor() -> None:
    """Unutulan bir dert hiç var olmamış demektir."""
    now = time.time()
    state = Relationship()
    state.record("rude", now=now, note="he forgot her birthday")

    state.decay(now + 200 * DAY)

    assert len(state.open_grievances()) == 1


# ---------------------------------------------------------------------------
# Kalıcılık
# ---------------------------------------------------------------------------


def test_gidis_donus_KAYIPSIZ() -> None:
    now = time.time()
    state = Relationship()
    state.record("rude", now=now, note="something happened")
    state.record("affectionate", now=now)

    restored = from_dict(to_dict(state))

    assert restored.warmth == state.warmth
    assert [g.text for g in restored.open_grievances()] == [
        g.text for g in state.open_grievances()
    ]


def test_bozuk_veri_VARSAYILANA_dusuyor() -> None:
    assert from_dict(None).warmth == WARMTH_START
    assert from_dict({"grievances": [{"no_text": 1}]}).open_grievances() == []


# ---------------------------------------------------------------------------
# "Aranızda bir şey geçti mi" -- zamanın geçmesi bir olay DEĞİL
# ---------------------------------------------------------------------------


def test_curume_BOS_durumu_baslatmis_gostermiyor() -> None:
    """``updated_at`` tek göstergeydi ve çürüme onu her açılışta damgalıyordu.

    Sonuç: hiç konuşulmamışken bile ilişki "başlamış" görünüyordu ve
    başlangıç sıcaklığının tarifi ("civil but not especially warm") ilk
    karşılaşmada personanın önüne geçiyordu.
    """
    state = Relationship()

    state.decay(_NOW)

    assert state.updated_at == 0.0
    assert state.warmth == WARMTH_START


def test_olay_damgayi_ATIYOR() -> None:
    state = Relationship()

    state.record("warm", now=_NOW)

    assert state.updated_at == _NOW


def test_curume_bos_durumda_sicakligi_BOZMUYOR() -> None:
    """Damga atılmadığı için sonraki çürüme "1970'ten beri" saymamalı."""
    state = Relationship()
    state.decay(_NOW)
    state.record("cruel", note="x", now=_NOW)
    cold = state.warmth

    state.decay(_NOW + 60.0)

    assert state.warmth == pytest.approx(cold, abs=0.05)
