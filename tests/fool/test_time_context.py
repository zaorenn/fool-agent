"""Zaman farkındalığı: saati bilmek yetmiyor, ne anlama geldiğini bilmek gerek.

Sistem promptuna bir zaman damgası koymak modelin "günaydın" demesi gerektiğini
SÖYLEMİYOR -- ondan çıkarım yapmasını bekliyor, ve o çıkarım her turda yeniden,
tutarsız biçimde yapılıyor. Burada karar kodda veriliyor.

Saat dilimi ENJEKTE EDİLİYOR: sabitlenmeden "sabah mı" sorusu makineye göre
değişen bir cevap alır ve sınav gerçekte neyi ölçtüğünü kaybeder.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from fool.time_context import (
    UNFINISHED_GAP_SECONDS,
    build,
    describe_gap,
    part_of_day,
)

#: Sabit bir referans an: 2026-08-29, Cumartesi.
BASE = datetime(2026, 8, 29, 9, 14)


def at(hour: int, minute: int = 0):
    """Belirli bir saati veren sahte yerelleştirici."""
    moment = BASE.replace(hour=hour, minute=minute)

    return lambda _ts: moment


# ---------------------------------------------------------------------------
# Günün saati
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hour,expected",
    [
        (2, "late night"),
        (6, "early morning"),
        (9, "morning"),
        (14, "afternoon"),
        (20, "evening"),
        (23, "night"),
    ],
)
def test_gunun_saati(hour: int, expected: str) -> None:
    assert part_of_day(BASE.replace(hour=hour)) == expected


# ---------------------------------------------------------------------------
# Aradan geçen süre
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (30, "a few minutes ago"),
        (25 * 60, "25 minutes ago"),
        (3600, "an hour ago"),
        (5 * 3600, "5 hours ago"),
        (30 * 3600, "yesterday"),
        (4 * 86400, "4 days ago"),
        (9 * 86400, "a week ago"),
        (20 * 86400, "2 weeks ago"),
        (45 * 86400, "a month ago"),
    ],
)
def test_ara_insan_olceginde(seconds: float, expected: str) -> None:
    assert describe_gap(seconds) == expected


# ---------------------------------------------------------------------------
# İlk karşılaşma
# ---------------------------------------------------------------------------


def test_ILK_kez_konusuluyorsa_soyleniyor() -> None:
    ctx = build(now=BASE.timestamp(), last_seen=None, last_farewell=None, localize=at(9))

    assert ctx.first_ever is True
    assert ctx.since_last == ""
    assert "never spoken" in ctx.render()


def test_ilk_kez_VEDASIZ_ayrilma_sayilmiyor() -> None:
    """Hiç konuşulmamışsa veda edilmemiş olması bir şey ifade etmiyor."""
    ctx = build(now=BASE.timestamp(), last_seen=None, last_farewell=None, localize=at(9))

    assert ctx.left_without_goodbye is False


# ---------------------------------------------------------------------------
# Vedasız ayrılık -- istenen davranışın çekirdeği
# ---------------------------------------------------------------------------


def test_gece_VEDA_ETMEDEN_kapatti_ertesi_sabah_hatirlaniyor() -> None:
    """İstenen davranış birebir buydu.

    Aradan geçen süreden çıkarmak mümkün DEĞİL: sekiz saatlik boşluk, "iyi
    geceler deyip yattı" ile "ortadan kayboldu" arasında hiçbir fark görmüyor.
    Fark vedanın kaydedilmiş olup olmamasında.
    """
    now = BASE.replace(hour=9).timestamp()
    last_seen = (BASE - timedelta(days=1)).replace(hour=23, minute=40).timestamp()

    ctx = build(now=now, last_seen=last_seen, last_farewell=None, localize=at(9))

    assert ctx.left_without_goodbye is True
    assert "without saying goodbye" in ctx.render()


def test_VEDA_EDILDIYSE_sitem_yok() -> None:
    now = BASE.replace(hour=9).timestamp()
    last_seen = (BASE - timedelta(days=1)).replace(hour=23, minute=40).timestamp()
    farewell = last_seen + 30

    ctx = build(now=now, last_seen=last_seen, last_farewell=farewell, localize=at(9))

    assert ctx.left_without_goodbye is False
    assert "without saying goodbye" not in ctx.render()


def test_ESKI_bir_veda_yeni_ayriligi_ORTMUYOR() -> None:
    """Veda damgası görülme damgasının gerisindeyse, aradaki oturum vedasız."""
    now = BASE.replace(hour=9).timestamp()
    last_seen = (BASE - timedelta(days=1)).replace(hour=23, minute=40).timestamp()
    old_farewell = (BASE - timedelta(days=3)).timestamp()

    ctx = build(now=now, last_seen=last_seen, last_farewell=old_farewell, localize=at(9))

    assert ctx.left_without_goodbye is True


def test_KISA_kesinti_veda_gerektirmiyor() -> None:
    """Uygulama yeniden başladı, pencere kapandı -- bunlar ayrılık değil."""
    now = BASE.timestamp()
    last_seen = now - (UNFINISHED_GAP_SECONDS - 60)

    ctx = build(now=now, last_seen=last_seen, last_farewell=None, localize=at(9))

    assert ctx.left_without_goodbye is False


# ---------------------------------------------------------------------------
# Blok
# ---------------------------------------------------------------------------


def test_blok_saati_ve_gunu_tasiyor() -> None:
    ctx = build(now=BASE.timestamp(), last_seen=None, last_farewell=None, localize=at(9, 14))
    text = ctx.render()

    assert "09:14" in text
    assert "Saturday" in text
    assert "morning" in text


def test_blok_son_konusmayi_tasiyor() -> None:
    now = BASE.timestamp()
    ctx = build(now=now, last_seen=now - 4 * 86400, last_farewell=now - 4 * 86400 + 10,
                localize=at(9))

    assert "4 days ago" in ctx.render()
