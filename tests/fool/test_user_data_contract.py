"""Hiçbir kurulum/güncelleme kullanıcının verisine dokunamaz.

İstenen (kullanıcının kendi ifadesi): "hiçbir update asla ama asla kullanıcının
bilgilerini değiştirip silmemeli."

Bu kural iki kez ölçülebilir biçimde çiğnendi ve ikisi de sessizdi:

1. ``install.ps1`` ``FOOL_HOME``u kullanıcı kapsamına yazdı; masaüstünün
   fresh-install sınavı ``%TEMP%`` altındaki bir evle koşunca uygulama kalıcı
   olarak boş bir dizine yönlendi. Kullanıcı "her şeyim silindi" dedi -- hiçbir
   şey silinmemişti, ama onun için farkı yoktu.
2. Kaldırıcı veri dizinini sessizce bıraktı ve sonraki kurulumları bozdu.

Örtük kural, kimsenin sınamadığı kuraldır. Buradaki testler kuralı tutuyor.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fool import user_data


# ---------------------------------------------------------------------------
# Sözleşmenin kendisi
# ---------------------------------------------------------------------------


def test_iki_kume_CAKISMIYOR() -> None:
    """Çakışsalardı kullanıcı verisi silinebilir sayılırdı."""
    user_data.sanity_check()


def test_BILINMEYEN_ad_kullanici_verisi_sayiliyor() -> None:
    """Yanlış tarafa düşmenin bedeli asimetrik: gereksiz saklamak disk,
    yanlış silmek kullanıcının hafızası."""
    assert user_data.is_owned("hic-gorulmemis-yeni-dizin") is True


def test_en_kritik_yollar_KORUMADA() -> None:
    # Bu oturumda kullanıcının "gitti" dediği şeylerin hepsi.
    for name in ("state.db", "memories", "profiles", "voices", "sessions", "config.yaml"):
        assert user_data.is_owned(name) is True, name


def test_depo_klonu_ve_motor_ortamlari_SILINEBILIR() -> None:
    """Bunlar yeniden üretiliyor; korumaya almak güncellemeyi imkânsız yapardı."""
    # ``fool-agent`` YENI ad, ``hermes-agent`` göç edememiş kurulumlarda kalan
    # eski ad. İkisi de yeniden üretilebilir; biri listeden düşerse o kurulumda
    # gigabaytlarca klon "kullanıcı verisi" sayılır.
    for name in ("fool-agent", "hermes-agent", "sidecars", "cache", "logs"):
        assert user_data.is_owned(name) is False, name


# ---------------------------------------------------------------------------
# Kurulum/güncelleme kodu sözleşmeye uyuyor mu
# ---------------------------------------------------------------------------

INSTALL_PS1 = Path("scripts/install.ps1").read_text(encoding="utf-8")


def test_kurulum_gecici_bir_evi_KALICI_yazmiyor() -> None:
    """Ölçülen 1 numaralı ihlal. Kapı kalkarsa hata sessiz olur ve kullanıcıya
    veri kaybı gibi görünür."""
    assert "$isSandboxHome" in INSTALL_PS1

    gate = INSTALL_PS1.index("$isSandboxHome = $false")
    persist = INSTALL_PS1.index(
        '[Environment]::SetEnvironmentVariable("FOOL_HOME", $FoolHome, "User")'
    )

    assert gate < persist


@pytest.mark.parametrize(
    "owned",
    ["state.db", "memories", "profiles", "voices", "sessions"],
)
def test_kurulum_betigi_kullanici_verisini_SILMIYOR(owned: str) -> None:
    """``install.ps1`` içinde kullanıcı verisine yönelen bir silme olmamalı.

    Aranan şey ad DEĞİL, adın bir silme komutuyla aynı satırda geçmesi:
    ``Remove-Item ... voices`` gibi.
    """
    destructive = re.compile(
        r"^(?!\s*#).*(Remove-Item|rm\s+-|del\s|rmdir).*" + re.escape(owned),
        re.IGNORECASE | re.MULTILINE,
    )

    hits = destructive.findall(INSTALL_PS1)

    assert not hits, f"install.ps1 {owned!r} icin silme iceriyor: {hits}"


def test_yedekleme_depo_klonunu_DISLIYOR_kullanici_verisini_dislamiyor() -> None:
    """Yedek, geri getirilemeyecek şeyleri kapsamalı.

    ``hermes-agent`` dışlanıyor (yeniden klonlanır); ``voices`` ya da
    ``memories`` dışlansaydı yedek kullanıcının kaybettiği şeyi içermezdi --
    yani hiçbir işe yaramazdı.
    """
    from fool_cli import backup

    excluded = backup._EXCLUDED_DIRS

    # Göç ETTİKTEN sonra klon ``fool-agent`` adını taşıyor: yalnızca eski adı
    # dışlamak, her yedeğe gigabaytlarca yeniden klonlanabilir dosya koyardı.
    assert "fool-agent" in excluded
    assert "hermes-agent" in excluded

    for owned in ("memories", "voices", "profiles", "sessions"):
        assert owned not in excluded, f"{owned} yedekten dislanmis"


# ---------------------------------------------------------------------------
# İndirilen model ağırlıkları
# ---------------------------------------------------------------------------


def test_model_agirliklari_FOOL_HOME_DISINDA_duruyor() -> None:
    """İstenen: "indirdiği modeller silinemez."

    Ağırlıklar HuggingFace'in kendi önbelleğinde (``~/.cache/huggingface/hub``)
    duruyor -- yani ``FOOL_HOME``un tamamen dışında. Hiçbir kurulum/güncelleme
    yolu oraya dokunmuyor, ve dokunamaz: ``install.ps1``in sildiği tek dizin
    ``$InstallDir`` (depo klonu), masaüstününki de geçici dosyalar.

    Bu test o ayrımın KAZARA olmadığını tutuyor. Önbellek bir gün ``FOOL_HOME``
    altına taşınırsa buradan geçmez ve taşıyan kişi onu ``OWNED`` olarak
    sınıflandırmak zorunda kalır -- gigabaytlarca indirmeyi "yeniden üretilir"
    saymak, kullanıcı için silmekle aynı şey.
    """
    import inspect

    from fool import voice_models

    source = inspect.getsource(voice_models._weights_present)

    assert '".cache"' in source and '"huggingface"' in source, (
        "agirlik onbellegi artik baska bir yerde -- FOOL_HOME altina mi tasindi?"
    )
    assert "get_hermes_home" not in source, (
        "agirliklar FOOL_HOME altina tasinmis: user_data.py'de OWNED olarak "
        "siniflandirilmadan bu gecmemeli"
    )


def test_sidecar_ORTAMLARI_agirlik_TASIMIYOR() -> None:
    """``sidecars`` REPLACEABLE -- ama yalnızca pip ortamı olduğu için.

    Motor ortamı silinirse ``pip install`` ile geri gelir. Ağırlıklar orada
    OLSAYDI aynı silme gigabaytlarca indirmeyi de götürürdü ve sınıflandırma
    yanlış olurdu.
    """
    from fool import sidecar, user_data

    assert user_data.is_owned(sidecar._SIDECAR_DIRNAME) is False
    assert sidecar._SIDECAR_DIRNAME == "sidecars"
