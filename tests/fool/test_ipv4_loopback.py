"""``localhost`` Windows'ta iki saniye — ``127.0.0.1`` dört milisaniye.

Ölçülen hata
------------
Kullanıcının bildirdiği: "her mesajda minimum 10 saniye gecikme."

Sıra sıra elendi: prompt boyutu değil (100 KB'lık istem bile 4,2 sn), backend
değil (tur logunda model çağrısı dışında hiçbir şey yok), düşünme değil,
embedding değil (0,27 sn). Sonra çıkarım YAPMAYAN bir uç nokta ölçüldü::

    GET /v1/models  ->  2,047 sn

Süre modelde değil, bağlantıdaydı. Aynı sunucu, yalnızca konak adı değişerek::

    localhost    ->  2,028 / 2,037 / 2,038 sn
    127.0.0.1    ->  0,002 / 0,013 / 0,004 sn
    [::1]        ->  bağlantı reddedildi

Windows ``localhost``u önce IPv6 ``::1``e çözüyor; yerel çıkarım sunucuları
yalnızca IPv4 dinliyor, yani her istek iki saniyeyi IPv6 zaman aşımında
harcıyor. Bir sohbet turu birden çok istek yapıyor.

Bu testler kapının yerinde durduğunu tutuyor: kalkarsa gecikme geri gelir ve
sebebi hiçbir yerde görünmez.
"""

from __future__ import annotations

from fool import loopback


def test_ciplak_localhost_IPV4e_cevriliyor() -> None:
    assert (
        loopback.prefer_ipv4_loopback("http://localhost:1234/v1")
        == "http://127.0.0.1:1234/v1"
    )
    assert (
        loopback.prefer_ipv4_loopback("http://localhost:11434/v1")
        == "http://127.0.0.1:11434/v1"
    )
    # Buyuk/kucuk harf ve port yokken de.
    assert loopback.prefer_ipv4_loopback("http://LocalHost/v1") == "http://127.0.0.1/v1"


def test_BENZER_adlara_dokunulmuyor() -> None:
    """``localhost.example.com`` baska bir makine; yeniden yazmak onu kirardi."""
    for url in (
        "http://localhost.example.com:1234/v1",
        "http://mylocalhost:1234/v1",
        "http://192.168.1.10:1234/v1",
        "https://api.openai.com/v1",
    ):
        assert loopback.prefer_ipv4_loopback(url) == url


def test_ACIKCA_yazilmis_IPv6_korunuyor() -> None:
    """IPv6'da dinleyen bir sunucuyu bilerek isteyen kullanıcı adresi açıkça
    yazıyor -- yeniden yazma yalnızca çıplak ``localhost`` için."""
    url = "http://[::1]:1234/v1"

    assert loopback.prefer_ipv4_loopback(url) == url


def test_dize_olmayan_deger_OLDUGU_GIBI_donuyor() -> None:
    for value in (None, 1234, {"a": 1}, ["x"]):
        assert loopback.prefer_ipv4_loopback(value) is value


def test_yapilandirmadaki_HER_base_url_cevriliyor() -> None:
    config = {
        "model": {"base_url": "http://localhost:1234/v1", "default": "x"},
        "auxiliary": {
            "vision": {"base_url": "http://localhost:1234/v1"},
            "web_extract": {"base_url": ""},
        },
        "providers": [{"base_url": "http://localhost:8080/v1"}],
    }

    out = loopback.normalize_config_urls(config)

    assert out["model"]["base_url"] == "http://127.0.0.1:1234/v1"
    assert out["auxiliary"]["vision"]["base_url"] == "http://127.0.0.1:1234/v1"
    assert out["providers"][0]["base_url"] == "http://127.0.0.1:8080/v1"
    # base_url DISINDAKI alanlara dokunulmuyor.
    assert out["model"]["default"] == "x"


def test_yapilandirma_yukleyicisi_KAPIYI_cagiriyor() -> None:
    """Bağlantı koparsa gecikme sessizce geri gelir."""
    from pathlib import Path

    source = Path("fool_cli/config.py").read_text(encoding="utf-8")

    assert "normalize_config_urls" in source
    assert "FOOL-SEAM: ipv4-loopback" in source


def test_otomatik_algilama_zaten_IPv4_yaziyor() -> None:
    """Yeni kurulumlar bu tuzağa hiç düşmemeli."""
    from pathlib import Path

    source = Path("fool/autodetect.py").read_text(encoding="utf-8")

    assert "//localhost:" not in source
    assert "127.0.0.1" in source
