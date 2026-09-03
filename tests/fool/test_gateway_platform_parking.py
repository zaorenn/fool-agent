"""Eşleşmemiş bir WhatsApp bütün ürünü kapatıyordu.

Ölçüldü (bu makine, tek oturum, ``gateway.log``):

    "Starting Hermes Gateway" -> 37 kez
    sebep -> whatsapp: enabled but not paired;
             telegram: token was rejected by the server

Gateway çıkış kodu 78 ile çıkıyor -- "bu bir yapılandırma hatası, beni
yeniden başlatma" sözleşmesi. systemd (``RestartPreventExitStatus``) ve s6
bunu onurlandırıyor. Windows başlatıcısı ONURLANDIRMIYOR: süreci koşulsuz
yeniden açıyor, aynı yapılandırma aynı hatayı veriyor, döngü.

Bedeli yalnızca günlük gürültüsü değil. Her yeniden başlatma çalışan bütün
ses motoru süreçlerini öldürüyor ve bir sonraki cümle modeli SIFIRDAN
yüklüyor (ölçüldü: styletts2 67,21 sn, kokoro 24,17 sn). Kullanıcının
"model dakikalarca uyanıyor ve bilgisayar kasıyor" dediği şeyin bir parçası
buydu -- ve sebebi eşleşmemiş bir WhatsApp'tı.
"""

from __future__ import annotations

import pytest

from gateway.restart import GATEWAY_FATAL_CONFIG_EXIT_CODE, _fatal_platform_exit_honored
from tests.conftest import pretend_os_name


@pytest.fixture(autouse=True)
def _no_override(monkeypatch):
    monkeypatch.delenv("FOOL_GATEWAY_FATAL_CONFIG_EXIT", raising=False)
    yield


# ---------------------------------------------------------------------------
# Sözleşme nerede geçerli
# ---------------------------------------------------------------------------

def test_windows_sozlesmeyi_UYGULAMIYOR(monkeypatch) -> None:
    """Ölümcül çıkışın tek anlamı denetleyicinin durması. Durmuyorsa o çıkış
    ürünü kapatıp yerine bir yeniden başlatma döngüsü koyuyor."""
    with pretend_os_name("nt"):

        assert _fatal_platform_exit_honored() is False


def test_posix_sozlesmeyi_UYGULUYOR(monkeypatch) -> None:
    """Tasarım niyeti korunuyor: systemd/s6 altında eski davranış aynen
    geçerli -- operatör yapılandırmayı düzeltene kadar gateway kalkmıyor."""
    with pretend_os_name("posix"):

        assert _fatal_platform_exit_honored() is True


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_dagitim_eski_davranisi_GERI_ALABILIYOR(monkeypatch, value) -> None:
    """Kendi denetleyicisinin sözleşmeyi uyguladığını bilen bir dağıtım
    kaçış kapısına sahip olmalı."""
    with pretend_os_name("nt"):
        monkeypatch.setenv("FOOL_GATEWAY_FATAL_CONFIG_EXIT", value)

        assert _fatal_platform_exit_honored() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "OFF"])
def test_POSIX_ta_da_kapatilabiliyor(monkeypatch, value) -> None:
    """Ters yön: konteyner içinde koşan bir gateway'in denetleyicisi 78'i
    onurlandırmıyor olabilir."""
    with pretend_os_name("posix"):
        monkeypatch.setenv("FOOL_GATEWAY_FATAL_CONFIG_EXIT", value)

        assert _fatal_platform_exit_honored() is False


def test_ANLAMSIZ_deger_platform_varsayilanina_dusuyor(monkeypatch) -> None:
    """Yazım hatası olan bir ayar, sessizce ters davranışa yol açmamalı."""
    with pretend_os_name("nt"):
        monkeypatch.setenv("FOOL_GATEWAY_FATAL_CONFIG_EXIT", "belki")

        assert _fatal_platform_exit_honored() is False


def test_bos_deger_yok_sayiliyor(monkeypatch) -> None:
    with pretend_os_name("posix"):
        monkeypatch.setenv("FOOL_GATEWAY_FATAL_CONFIG_EXIT", "   ")

        assert _fatal_platform_exit_honored() is True


# ---------------------------------------------------------------------------
# Kod yolu gerçekten dallanıyor mu
# ---------------------------------------------------------------------------

def test_olumcul_cikis_ARTIK_KOSULLU() -> None:
    """Kaynak metinden okunuyor: koşul kaldırılırsa döngü geri gelir.

    Davranışı burada koşturmak gateway'in tüm açılışını kurmayı gerektirirdi;
    ölçtüğümüz şey çıkışın koşulsuz OLMADIĞI.
    """
    import inspect

    import gateway.run as run

    source = inspect.getsource(run)
    marker = "FOOL-SEAM: platform-failure-not-fatal"

    assert marker in source, "dikis kayboldu -- upstream merge geri almis olabilir"

    window = source[source.index(marker) : source.index(marker) + 3400]

    assert "_fatal_platform_exit_honored()" in window, (
        "olumcul cikis kosulsuz hale gelmis -- Windows'ta yeniden baslatma dongusu geri doner"
    )
    assert 'gateway_state="degraded"' in window, (
        "park etme yolu calisma durumuna yazmiyor -- platformlar GORUNMEZ olurdu"
    )


def test_cikis_kodu_DEGISMEDI() -> None:
    """Sözleşmeyi uygulayan denetleyiciler bu sayıya bakıyor."""
    assert GATEWAY_FATAL_CONFIG_EXIT_CODE == 78


# ---------------------------------------------------------------------------
# Runner seviyesi: döngüyü gerçekten kesiyor mu
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_denetleyicisiz_dunyada_gateway_AYAKTA_kaliyor(monkeypatch, tmp_path) -> None:
    """Asıl ölçüm: aynı koşulda gateway artık çıkmıyor.

    Üstteki testler kararı veren yüklemi (``_fatal_platform_exit_honored``)
    tutuyor; bu test kararın runner'a GERÇEKTEN uygulandığını tutuyor. İkisi
    ayrı: yüklem doğru olup çağrı yerinde unutulmuş olsaydı döngü aynen
    devam ederdi ve testler yeşil kalırdı.
    """
    from gateway.config import GatewayConfig, Platform, PlatformConfig
    from gateway.run import GatewayRunner
    from gateway.status import read_runtime_status
    from tests.gateway.test_runner_startup_failures import _NonRetryableFailureAdapter

    monkeypatch.setenv("FOOL_HOME", str(tmp_path))
    # Denetleyici 78'i onurlandirmiyor -- Windows baslaticisi gibi.
    monkeypatch.setenv("FOOL_GATEWAY_FATAL_CONFIG_EXIT", "0")

    runner = GatewayRunner(
        GatewayConfig(
            platforms={Platform.DISCORD: PlatformConfig(enabled=True, token="***")},
            sessions_dir=tmp_path / "sessions",
        )
    )
    monkeypatch.setattr(
        runner, "_create_adapter", lambda platform, platform_config: _NonRetryableFailureAdapter()
    )

    await runner.start()

    assert runner.should_exit_cleanly is not True, (
        "gateway hala cikiyor -- Windows'ta yeniden baslatma dongusu geri doner"
    )
    assert runner.exit_code != GATEWAY_FATAL_CONFIG_EXIT_CODE

    # Durum "cikis oldu" DEMEMELI. Son degeri asagidaki "adaptor kurulamadi"
    # dali yaziyor (``running`` -- cron calismaya devam ediyor) ve dogrusu da
    # bu: gateway gercekten ayakta. Onemli olan ``startup_failed`` OLMAMASI --
    # o deger baslaticiya "oldum" diyor.
    assert read_runtime_status()["gateway_state"] != "startup_failed"


@pytest.mark.asyncio
async def test_sozlesmeli_dunyada_davranis_DEGISMEDI(monkeypatch, tmp_path) -> None:
    """Ters yön: systemd/s6 altında eski davranış aynen sürüyor.

    Bu olmadan değişiklik bir düzeltme değil, sözleşmenin sessizce
    kaldırılması olurdu.
    """
    from gateway.config import GatewayConfig, Platform, PlatformConfig
    from gateway.run import GatewayRunner
    from gateway.status import read_runtime_status
    from tests.gateway.test_runner_startup_failures import _NonRetryableFailureAdapter

    monkeypatch.setenv("FOOL_HOME", str(tmp_path))
    monkeypatch.setenv("FOOL_GATEWAY_FATAL_CONFIG_EXIT", "1")

    runner = GatewayRunner(
        GatewayConfig(
            platforms={Platform.DISCORD: PlatformConfig(enabled=True, token="***")},
            sessions_dir=tmp_path / "sessions",
        )
    )
    monkeypatch.setattr(
        runner, "_create_adapter", lambda platform, platform_config: _NonRetryableFailureAdapter()
    )

    await runner.start()

    assert runner.exit_code == GATEWAY_FATAL_CONFIG_EXIT_CODE
    assert read_runtime_status()["gateway_state"] == "startup_failed"
