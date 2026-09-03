"""Uzak platformların araç yüzeyi.

İki ayrı hatayı birden tutuyor:

1. **Yeniden adlandırma kopması.** ``fool_cli/platforms.py`` her platformun
   ``default_toolset`` değerini ``hermes-*`` -> ``fool-*`` diye markaladı ama
   ``toolsets.py`` bileşik takımları hâlâ ``hermes-*`` adıyla tanımlıyor.
   ``resolve_toolset("fool-discord")`` boş liste döndürüyordu; yani
   ``config.yaml`` içinde açık kaydı olmayan HER platform SIFIR araçla
   koşuyordu. Sessiz hata: hata mesajı yok, model sadece "yapamıyorum" diyor.

2. **Uzak platformlar varsayılan olarak kısıtsız.** (1) düzeltilince her
   platform 59 araçlık bileşiğe düşerdi -- ``computer_use``, ``execute_code``,
   ``terminal_run``, 13 ``browser_*``. WhatsApp/Telegram/Discord'a yazabilen
   herkes makineyi sürerdi. Düzeltmenin bu iki yarısı BİRLİKTE inmek zorunda.
"""

from __future__ import annotations

import pytest

from fool import platform_toolsets as policy
from fool_cli.platforms import PLATFORMS
from fool_cli.tools_config import _get_platform_tools
from toolsets import TOOLSETS, resolve_toolset

# Uzak bir kullanıcının ELİNE GEÇMEMESİ gereken araçlar: makineyi süren,
# diskten okuyan ya da sahibinin geçmişini sızdıran her şey.
FORBIDDEN_ON_REMOTE = {
    "computer_use",
    "cronjob",
    "delegate_task",
    "execute_code",
    "patch",
    "read_file",
    "search_files",
    "terminal_run",
    "write_file",
}


def _tools_for(config: dict, platform: str) -> set[str]:
    tools: set[str] = set()
    for name in _get_platform_tools(config, platform):
        tools |= set(resolve_toolset(name))
    return tools


# ---------------------------------------------------------------------------
# 1. Yeniden adlandırma kopması
# ---------------------------------------------------------------------------

def test_platform_default_toolset_cozulebiliyor() -> None:
    """Her platformun varsayılan bileşiği GERÇEK araçlara çözülmeli.

    Boş dönerse o platform sessizce araçsız kalır.
    """
    bos = [
        p for p in sorted(PLATFORMS)
        if not resolve_toolset(PLATFORMS[p].default_toolset)
    ]
    assert not bos, (
        f"su platformlarin varsayilan bilesigi hicbir araca cozulmuyor: {bos} "
        "-- marka yeniden adlandirmasi toolsets.py ile uyumsuz"
    )


def test_eski_fool_takim_adlari_hala_cozuluyor() -> None:
    """Geriye donuk uyum: ``fool-x`` yazan bir yapilandirma calismaya devam etmeli.

    Marka donusumu bir donem ``default_toolset`` degerlerini ``fool-*`` yapti.
    Tanimlayicilar upstream adina geri alindi, ama o donemde ``fool tools``
    ile kaydedilmis ya da elle yazilmis ``config.yaml`` dosyalarinda hala
    ``fool-cli`` gibi adlar olabilir. ``toolsets.py``deki uyum dikisi onlari
    sessizce bos birakmak yerine gercek bilesige cevirir.
    """
    checked = 0
    for twin in sorted(k for k in TOOLSETS if k.startswith("hermes-")):
        legacy = "fool-" + twin[len("hermes-"):]
        assert policy.upstream_toolset_alias(legacy) == twin
        checked += 1
        assert set(resolve_toolset(legacy)) == set(resolve_toolset(twin)), (
            f"eski ad {legacy} artik {twin} ile ayni degil"
        )
    assert checked, "hicbir bilesik denetlenmedi"


def test_platform_tanimlayicilari_markalanmamis() -> None:
    """``default_toolset`` bir cagri sozlesmesi; marka donusumu ona dokunmaz.

    Bu testin varlik nedeni: ``fool-*`` yapan yama sessizce her platformu
    araciz birakmisti ve hicbir sey hata vermemisti.
    """
    markali = {
        p: PLATFORMS[p].default_toolset
        for p in sorted(PLATFORMS)
        if PLATFORMS[p].default_toolset.startswith("fool-")
    }
    assert not markali, (
        f"platform tanimlayicilari markalanmis: {markali} -- "
        "yalnizca 'label' markalanir, 'default_toolset' upstream adini korur"
    )


# ---------------------------------------------------------------------------
# 2. Temiz kurulumda uzak platformlar
# ---------------------------------------------------------------------------

REMOTE_SAMPLE = [
    p for p in sorted(PLATFORMS) if policy.is_remote_platform(p)
]


def test_temiz_kurulumda_uzak_platform_makineyi_surdurmuyor() -> None:
    """``config.yaml`` YOKKEN bile uzak platform kısıtlı gelmeli.

    Eski kod bu kısıtlamayı yalnızca ilk açılışta çalışan bir yerel model
    sunucusu bulunursa yazıyordu; LM Studio kapalıysa hiç yazılmıyordu.
    Politika artık yapılandırma dosyasına bağlı değil.
    """
    sizinti: dict[str, list[str]] = {}
    for platform in REMOTE_SAMPLE:
        tools = _tools_for({}, platform)
        bad = sorted(FORBIDDEN_ON_REMOTE & tools)
        bad += sorted(
            t for t in tools if t.startswith("browser") or t.startswith("ha_")
        )
        if bad:
            sizinti[platform] = bad
    assert not sizinti, f"uzak platformlara tehlikeli arac siziyor: {sizinti}"


def test_temiz_kurulumda_uzak_platform_araciz_kalmiyor() -> None:
    """Kısıtlamak sıfırlamak demek değil: sohbet edebilecek kadar araç kalmalı."""
    bos = [p for p in REMOTE_SAMPLE if not _get_platform_tools({}, p)]
    assert not bos, f"temiz kurulumda hic arac takimi olmayan platformlar: {bos}"


def test_bilinmeyen_platform_varsayilan_olarak_kisitli() -> None:
    """Yarın eklenecek bir platform eklentisi de kapalı doğmalı.

    Politika 'listelenenler kısıtlı' değil 'listelenmeyen her şey uzak'
    diye yazıldı; aksi hâlde her yeni adaptör sessizce tam yetki alırdı.
    """
    assert policy.is_remote_platform("some_future_chat_app")
    tools = _tools_for({}, "some_future_chat_app")
    assert not (FORBIDDEN_ON_REMOTE & tools)


# ---------------------------------------------------------------------------
# 3. Yerel platformlar ve kullanıcının açık seçimi
# ---------------------------------------------------------------------------

def test_yerel_platform_tam_yetkide_kaliyor() -> None:
    """Sahibinin kendi terminali ve kendi zamanlanmış işleri kısıtlanmaz.

    Bu test aynı zamanda yeniden adlandırma kopmasının asıl bedelini tutuyor:
    düzeltmeden önce temiz kurulumda ``cli`` bile SIFIR araç takımı alıyordu.
    """
    for platform in ("cli", "cron"):
        assert not policy.is_remote_platform(platform)
        enabled = _get_platform_tools({}, platform)
        assert "file" in enabled, f"{platform}: dosya araclari kayboldu"
        assert "terminal" in enabled, f"{platform}: terminal kayboldu"


def test_kullanicinin_acik_secimi_eziliyor_degil() -> None:
    """Kullanıcı bilerek genişletmişse politika araya girmez."""
    cfg = {"platform_toolsets": {"discord": ["file", "web"]}}
    assert _get_platform_tools(cfg, "discord") >= {"file", "web"}


def test_kullanici_daha_da_kisitlayabiliyor() -> None:
    cfg = {"platform_toolsets": {"telegram": ["clarify"]}}
    assert _get_platform_tools(cfg, "telegram") == {"clarify"}


# ---------------------------------------------------------------------------
# 4. Politikanın kendisi
# ---------------------------------------------------------------------------

def test_guvenli_varsayilan_tehlikeli_takim_icermiyor() -> None:
    tools: set[str] = set()
    for name in policy.SAFE_REMOTE_TOOLSETS:
        tools |= set(resolve_toolset(name))
    assert tools, "guvenli varsayilan hicbir araca cozulmuyor"
    assert not (FORBIDDEN_ON_REMOTE & tools)


def test_upstream_alias_yalnizca_fool_onekini_cevirir() -> None:
    assert policy.upstream_toolset_alias("fool-telegram") == "hermes-telegram"
    assert policy.upstream_toolset_alias("hermes-telegram") is None
    assert policy.upstream_toolset_alias("file") is None
    assert policy.upstream_toolset_alias("") is None
