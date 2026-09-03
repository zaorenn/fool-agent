"""Sesin duygusu tur başına değişsin.

İstenen: "bir espri yaptığımızda gülebilsin, sesindeki duygu duruma göre
değişebilsin."

Motorun kolları (``exaggeration`` / ``cfg_weight``) yapılandırmada duruyordu,
yani oturum boyunca sabitti: model ne söylerse söylesin ses aynı tondaydı.
Motorun kendisi ikisini de istek başına ZATEN kabul ediyor; eksik olan modelin
niyetini oraya taşıyan yoldu.
"""

from __future__ import annotations

import pytest

from fool.voice_emotion import (
    DELIVERIES,
    Delivery,
    prompt_hint,
    split_delivery,
    strip_tags,
    tag_vocabulary,
)


# ---------------------------------------------------------------------------
# Ayrıştırma
# ---------------------------------------------------------------------------


def test_etiket_AYIKLANIYOR_ve_teslimat_donuyor() -> None:
    text, delivery = split_delivery("[warm] Hey, you're back.")

    assert text == "Hey, you're back."
    assert delivery == DELIVERIES["warm"]


def test_etiket_YOKSA_metin_dokunulmamis() -> None:
    text, delivery = split_delivery("Hey, you're back.")

    assert text == "Hey, you're back."
    assert delivery is None


def test_TANINMAYAN_etiket_duz_metin() -> None:
    """Ayıklamak, modelin yazdığı gerçek bir köşeli parantezi yutmak olurdu."""
    text, delivery = split_delivery("[shrug] whatever")

    assert text == "[shrug] whatever"
    assert delivery is None


def test_etiket_yalnizca_BASTA_gecerli() -> None:
    text, delivery = split_delivery("Look at this [warm] thing")

    assert text == "Look at this [warm] thing"
    assert delivery is None


def test_buyuk_kucuk_harf_onemsiz() -> None:
    _text, delivery = split_delivery("[LAUGHING] hah")

    assert delivery == DELIVERIES["laughing"]


def test_etiketten_sonraki_bosluk_yutuluyor() -> None:
    text, _delivery = split_delivery("[warm]    Hey.")

    assert text == "Hey."


def test_bos_metin_patlamiyor() -> None:
    assert split_delivery("") == ("", None)


def test_strip_tags_sadece_metni_veriyor() -> None:
    assert strip_tags("[cold] Fine.") == "Fine."
    assert strip_tags("Fine.") == "Fine."


# ---------------------------------------------------------------------------
# Haritalama -- sayılar kolların ne yaptığından türüyor
# ---------------------------------------------------------------------------


def test_gulme_ENERJIK() -> None:
    """Yoğunluk yüksek VE tempo yüksek -- gülmek yavaş bir şey değil."""
    laughing = DELIVERIES["laughing"]

    assert laughing.exaggeration > DELIVERIES["neutral"].exaggeration
    assert laughing.cfg_weight > DELIVERIES["neutral"].cfg_weight


def test_soguk_DUZ_ve_agir() -> None:
    """Düşük yoğunluk + düşük cfg = düz ve yavaş."""
    cold = DELIVERIES["cold"]

    assert cold.exaggeration < DELIVERIES["neutral"].exaggeration
    assert cold.cfg_weight < DELIVERIES["neutral"].cfg_weight


def test_sicak_daha_ifadeli_ve_daha_YAVAS() -> None:
    warm = DELIVERIES["warm"]

    assert warm.exaggeration > DELIVERIES["neutral"].exaggeration
    assert warm.cfg_weight < DELIVERIES["neutral"].cfg_weight


@pytest.mark.parametrize("name", sorted(DELIVERIES))
def test_butun_degerler_motorun_ARALIGINDA(name: str) -> None:
    delivery = DELIVERIES[name]

    # Chatterbox: exaggeration 0.25-2.0, cfg_weight 0-1.
    assert 0.25 <= delivery.exaggeration <= 2.0
    assert 0.0 < delivery.cfg_weight <= 1.0


def test_teslimat_motorun_bekledigi_ANAHTARLARI_veriyor() -> None:
    config = Delivery(0.7, 0.3).as_config()

    assert config == {"exaggeration": 0.7, "cfg_weight": 0.3}


def test_etiketin_ADI_da_tasiniyor() -> None:
    """Motorlar duyguyu aynı dilde konuşmuyor: kimi iki kol istiyor, kimi
    adlandırılmış bir duygu. Adı da taşımak, her motorun anladığını almasını
    ve anlamadığını sessizce yok saymasını sağlıyor."""
    config = DELIVERIES["laughing"].as_config()

    assert config["emotion"] == "laughing"


@pytest.mark.parametrize("name", sorted(DELIVERIES))
def test_her_teslimat_KENDI_adini_biliyor(name: str) -> None:
    assert DELIVERIES[name].name == name


# ---------------------------------------------------------------------------
# Modele söylenen
# ---------------------------------------------------------------------------


def test_ipucu_BUTUN_etiketleri_sayiyor() -> None:
    hint = prompt_hint()

    for name in tag_vocabulary():
        assert "[" + name + "]" in hint


def test_ipucu_TEK_etiket_ve_BASTA_diyor() -> None:
    hint = prompt_hint()

    assert "One tag" in hint
    assert "very start" in hint


def test_ipucu_etiketin_OKUNMAYACAGINI_soyluyor() -> None:
    """Model bunu bilmezse etiketi cümlenin parçası sanıp yazmaktan kaçınır."""
    assert "without being read out" in prompt_hint()


# ---------------------------------------------------------------------------
# Normalize yolu -- etiket HİÇBİR yoldan seslendirilmemeli
# ---------------------------------------------------------------------------


def test_etiket_normalize_yolunda_da_ayiklaniyor() -> None:
    """Akış dışındaki yollar etiketi anlamıyor; oradan geçerse SESLİ okunurdu."""
    from tools.tts_text_normalize import prepare_spoken_text

    assert prepare_spoken_text("[laughing] That was funny.") == "That was funny."


def test_tanninmayan_etiket_normalize_yolunda_KALIYOR() -> None:
    from tools.tts_text_normalize import prepare_spoken_text

    assert "[shrug]" in prepare_spoken_text("[shrug] fine")
