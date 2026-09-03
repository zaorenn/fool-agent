"""Ajan olmayan komutları deniyordu.

Ölçüldü:

    fool telegram        -> YOK
    fool gateway logs    -> YOK   (dogru olan: fool logs)
    fool voice           -> YOK
    fool tools/model/desktop/update/doctor -> VAR

Ajan bunları kendiliğinden uyduruyor: upstream'in belgelerinde ve genel
alışkanlıkta böyle komutlar var, gerçek yüzeyde yok. Kullanıcı "telegram'ı
kur" diyor, ajan ``fool telegram`` deniyor, kabuk hata veriyor, ajan başka
bir varyant deniyor. Tur boşa gidiyor ve kullanıcı ajanı beceriksiz sanıyor.

Bu testlerin asıl işi DRIFT'i yakalamak: rehberde adı geçen her komutun
gerçekten var olması gerekiyor. Bir komut yeniden adlandırılırsa rehber
sessizce yalan söylemeye başlar -- tam da düzeltmeye çalıştığımız hata.
"""

from __future__ import annotations

import re

import pytest

from fool import guidance


def _cited_commands(text: str) -> set[str]:
    """Rehberde ``fool <komut>`` diye anılan tüm ilk seviye komutlar."""
    return {m.group(1) for m in re.finditer(r"`fool ([a-z][a-z-]*)", text)}


@pytest.fixture(scope="module")
def real_commands() -> set[str]:
    """GERÇEK komut listesi -- ``fool --help`` çıktısından.

    Parser ``main()`` içinde satır satır kuruluyor ve ithal edilebilir bir
    kurucusu yok. Alt süreç çağırmak pahalı ama DOĞRU: iç yapı değişse bile
    bu test kullanıcının gördüğü yüzeyi ölçmeye devam eder.
    """
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-m", "fool_cli.main", "--help"],
        capture_output=True,
        text=True,
        timeout=180,
        # Depo kurali: Windows'ta stdin belirtilmeyen bir alt surec ebeveynin
        # konsol tutamacini miras alip blokluyor.
        stdin=subprocess.DEVNULL,
    ).stdout

    match = re.search(r"\{([a-z0-9,\-]+)\}", out)
    if not match:
        pytest.skip("komut listesi --help ciktisinda bulunamadi")

    return set(match.group(1).split(","))


def test_rehber_bos_degil() -> None:
    assert guidance.CLI_COMMAND_GUIDANCE.strip()


def test_rehberdeki_her_komut_GERCEKTEN_var(real_commands: set[str]) -> None:
    """Drift koruması: bir komut yeniden adlandırılırsa burası kırılır."""
    cited = _cited_commands(guidance.CLI_COMMAND_GUIDANCE)
    assert cited, "rehberde hic komut anilmamis"

    hayalet = sorted(cited - real_commands)
    assert not hayalet, f"rehber olmayan komutlari aniyor: {hayalet}"


@pytest.mark.parametrize("ghost", ["telegram", "voice"])
def test_uydurulan_komutlar_rehberde_gecmiyor(ghost: str) -> None:
    assert f"`fool {ghost}`" not in guidance.CLI_COMMAND_GUIDANCE


def test_rehber_yanlis_log_komutunu_duzeltiyor() -> None:
    """``fool gateway logs`` yok; doğrusu ``fool logs``."""
    assert "`fool logs`" in guidance.CLI_COMMAND_GUIDANCE


def test_rehber_sistem_promptuna_giriyor() -> None:
    """Yazılıp bağlanmayan bir rehber hiçbir şey düzeltmez."""
    blocks = guidance.all_guidance()
    assert any(guidance.CLI_COMMAND_GUIDANCE in block for block in blocks)


def test_rehber_kisa_kaliyor() -> None:
    """Sistem promptu bedava değil; her satırın karşılığı olmalı."""
    assert len(guidance.CLI_COMMAND_GUIDANCE) < 2_000


# ---------------------------------------------------------------------------
# Arkadaş tarzı sohbet
# ---------------------------------------------------------------------------

def test_sohbet_rehberi_sistem_promptuna_giriyor() -> None:
    assert any(guidance.COMPANION_GUIDANCE in block for block in guidance.blocks())


def test_sohbet_rehberi_dolgu_acilislari_yasakliyor() -> None:
    """Ölçülebilir kural: "Great question" ile başlayan bir cevap yanlıştır."""
    flat = " ".join(guidance.COMPANION_GUIDANCE.split())

    assert "Great question" in flat
    assert "No filler openers" in flat


def test_sohbet_rehberi_SESLI_okunacagini_soyluyor() -> None:
    """Markdown başlıkları ve kod bloğu, seslendirildiğinde saçma duyuluyor."""
    flat = " ".join(guidance.COMPANION_GUIDANCE.split())

    assert "read out loud" in flat
    assert "no markdown headings" in flat


def test_sohbet_rehberi_bilmiyorum_demeyi_soyluyor() -> None:
    assert "I don't know" in guidance.COMPANION_GUIDANCE


def test_sohbet_rehberi_kisa_kaliyor() -> None:
    """Sistem promptu bedava değil."""
    assert len(guidance.COMPANION_GUIDANCE) < 1_600


def test_sohbet_rehberi_SESLI_oldugunu_KESIN_soyluyor() -> None:
    """Yumuşak ifade küçük modelde TERS sonuç verdi.

    "much of this is spoken aloud" ile ``gemma-4-e4b`` kendi kendine şu
    sonuca vardı ve kullanıcıya söyledi:

        "my audio output capability is outside of my current textual
         communication medium (the chat interface)"

    Yani konuşamadığını söylüyordu -- söylerken sözleri sesle çalınıyorken.
    Bir dil modeli için "çoğu" ile "hepsi" arasındaki fark burada belirleyici.
    """
    from fool import guidance

    flat = guidance.COMPANION_GUIDANCE.replace("\n", " ")

    # Kosulsuz ifade: "cogu" degil "her kelime".
    assert "Every word you write is turned into speech" in flat
    # Ve inkari ACIKCA yasakliyor.
    assert "never say you cannot speak" in flat
    assert "never call yourself text-only" in flat
