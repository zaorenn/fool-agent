"""Bilmediğini fark etmek -- ve sormayı bilmek.

İstenen: "bazen tanımak için sorular sorabilen ve gerçekten kullanıcıyı
tanımaya çalışıp ... kişiselleşen bir şey."

``remember()`` zaten vardı, yani SÖYLENEN bir şey saklanabiliyordu. Ama hiçbir
şey söylenmezse hiçbir şey öğrenilmiyordu: model kendi bilgi boşluğunu hiç
görmüyor, ona yalnızca BULUNAN anılar gösteriliyordu.
"""

from __future__ import annotations

import pytest

from fool import curiosity


# ---------------------------------------------------------------------------
# Kapsam
# ---------------------------------------------------------------------------


def test_bos_hafizada_ILK_konu_geliyor() -> None:
    topic = curiosity.next_topic([], companion=True)

    assert topic is not None
    assert topic.id == "name"


def test_kapsanmis_konu_ATLANIYOR() -> None:
    topic = curiosity.next_topic(["his name is Arda"], companion=True)

    assert topic is not None
    assert topic.id != "name"


def test_hepsi_kapsanmissa_SUSUYOR() -> None:
    """Kapsandığında modül tamamen susmalı: bitmeyen bir anket olmamalı."""
    covered = [
        "his name is Arda",
        "he works as an engineer",
        "he lives in Istanbul",
        "he plays games to relax",
        "he hates being interrupted",
        "he sleeps late, a night owl",
        "his closest friend is Kerem",
        "he wants to ship the app",
    ]

    assert curiosity.next_topic(covered, companion=True) is None


def test_SORULMUS_konu_bir_daha_gelmiyor() -> None:
    """Cevap vermemek de bir cevap; aynı soruyu üçüncü kez sormak
    dinlemediğini göstermenin en hızlı yolu."""
    first = curiosity.next_topic([], companion=True)
    second = curiosity.next_topic([], companion=True, asked={first.id})

    assert second is not None
    assert second.id != first.id


def test_TURKCE_anida_da_kapsam_goruluyor() -> None:
    # Kullanıcı Türkçe konuşuyor; anılar da Türkçe yazılıyor olabilir.
    topic = curiosity.next_topic(["kullanıcının adı Arda"], companion=True)

    assert topic is not None
    assert topic.id != "name"


def test_kismi_sozcuk_kapsam_SAYILMIYOR() -> None:
    """``name`` ile ``username`` aynı şey değil: sınır eşlemesi gerekiyor."""
    topic = curiosity.next_topic(["his username is zaorenn"], companion=True)

    assert topic is not None
    assert topic.id == "name"


# ---------------------------------------------------------------------------
# İki ayrı küme
# ---------------------------------------------------------------------------


def test_siradan_ajan_KISISEL_sey_sormuyor() -> None:
    """Kod yazarken "boş vakitlerinde ne yaparsın" yanlış soru."""
    ids = {topic.id for topic in curiosity.topics_for(companion=False)}

    assert "rest" not in ids
    assert "people" not in ids


def test_siradan_ajanin_konulari_bir_sonraki_TURU_degistiriyor() -> None:
    ids = {topic.id for topic in curiosity.topics_for(companion=False)}

    assert {"stack", "answer_shape", "conventions", "checks"} <= ids


def test_iki_kume_AYRI() -> None:
    companion = {t.id for t in curiosity.topics_for(companion=True)}
    working = {t.id for t in curiosity.topics_for(companion=False)}

    assert companion != working


@pytest.mark.parametrize("companion", [True, False])
def test_konu_kimlikleri_BENZERSIZ(companion: bool) -> None:
    ids = [topic.id for topic in curiosity.topics_for(companion=companion)]

    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Modele söylenen
# ---------------------------------------------------------------------------


def test_satir_EMIR_degil_davet() -> None:
    """"Şunu sor" diyen bir satır, model tam da kullanıcının bir işi
    yaptırmaya çalıştığı turda sorar."""
    line = curiosity.prompt_line(curiosity.COMPANION_TOPICS[0])

    assert "natural opening" in line
    assert "Never interrupt" in line


def test_satir_BIR_KEZ_diyor() -> None:
    line = curiosity.prompt_line(curiosity.COMPANION_TOPICS[1])

    assert "once" in line
    assert "let it go" in line
