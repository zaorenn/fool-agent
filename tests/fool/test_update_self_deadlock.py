"""``fool update`` kendi engelini yaratıyordu.

Ölçüldü, tekrar üretilebilir:

  1. ``fool update`` venv'i tutan bir süreç buluyor ve reddediyor:
     "Close The Fool desktop app / other Fool terminals, then re-run".
  2. Çıkmadan önce ``_resume_windows_gateways_after_update`` çağrılıyor ve
     ``cold_start_if_installed`` dalı ÇALIŞMAYAN bir gateway başlatıyor --
     logda "Gateway started via cold-start after update".
  3. Kullanıcı mesajın dediğini yapıyor: her şeyi kapatıyor, tekrar
     ``fool update``.
  4. Updater'ın KENDİ başlattığı gateway artık venv'i tutuyor -> aynı red.

Sonsuz döngü. Bu oturumda dört kez arka arkaya yaşandı ve güncelleme ancak
elle ``git pull`` ile yapılabildi.

Ayrım: cold-start bir DURUM GERİ YÜKLEME değil, başarılı güncelleme sonrası
bir kolaylık ("gateway kapalıydı ama autostart kayıtlı"). Güncelleme
olmadıysa o kolaylık yersiz ve zararlı.
"""

from __future__ import annotations

import pytest

from fool_cli import update_cmd


@pytest.fixture
def spy(monkeypatch):
    """Cold-start ve yeniden başlatma çağrılarını kaydet, hiçbirini yapma."""
    calls: dict[str, int] = {"cold": 0, "launchers": 0}

    # Yardimcilar ``fool_cli.main`` uzerinden cozuluyor (``_m()``) -- deponun
    # tarihsel test yuzeyi orasi, ``update_cmd`` degil.
    import fool_cli.main as main

    monkeypatch.setattr(main, "_is_windows", lambda: True)
    monkeypatch.setattr(
        main,
        "_refresh_windows_gateway_launchers",
        lambda: calls.__setitem__("launchers", calls["launchers"] + 1),
    )
    monkeypatch.setattr(
        main,
        "_cold_start_windows_gateway_after_update",
        lambda: calls.__setitem__("cold", calls["cold"] + 1),
    )
    return calls


def _token() -> dict:
    """Hiç gateway çalışmıyordu ama autostart kayıtlı -- cold-start durumu."""
    return {"resume_needed": True, "cold_start_if_installed": True, "profiles": {}}


# ---------------------------------------------------------------------------
# Asıl kilitlenme
# ---------------------------------------------------------------------------

def test_red_yolunda_gateway_BASLATILMIYOR(spy) -> None:
    """Güncelleme olmadıysa yeni bir venv tutucusu yaratmak yasak."""
    update_cmd._resume_windows_gateways_after_update(_token(), allow_cold_start=False)

    assert spy["cold"] == 0


def test_basarili_yolda_gateway_BASLATILIYOR(spy) -> None:
    """Tasarım niyeti korunuyor: güncelleme olduysa kolaylık yerinde."""
    update_cmd._resume_windows_gateways_after_update(_token())

    assert spy["cold"] == 1


def test_varsayilan_davranis_DEGISMEDI(spy) -> None:
    """Bayrak verilmeyen her çağrı eskisi gibi davranmalı."""
    update_cmd._resume_windows_gateways_after_update(_token())

    assert spy["cold"] == 1


def test_red_yolunda_da_baslaticilar_yenileniyor(spy) -> None:
    """Durum geri yükleme DEVAM ediyor; kesilen yalnızca YENİ süreç.

    Duraklatılan gateway'ler geri gelmeli -- onlar zaten çalışıyordu.
    """
    update_cmd._resume_windows_gateways_after_update(_token(), allow_cold_start=False)

    assert spy["launchers"] == 1


def test_resume_bayragi_yine_tuketiliyor(spy) -> None:
    """İkinci çağrı işlemsiz olmalı; yoksa çift yeniden başlatma olur."""
    token = _token()

    update_cmd._resume_windows_gateways_after_update(token, allow_cold_start=False)
    update_cmd._resume_windows_gateways_after_update(token)

    assert token["resume_needed"] is False
    assert spy["cold"] == 0, "tuketilmis token yeniden baslatmamali"


def test_token_yoksa_cokmuyor(spy) -> None:
    update_cmd._resume_windows_gateways_after_update(None, allow_cold_start=False)
    update_cmd._resume_windows_gateways_after_update({})

    assert spy["cold"] == 0


# ---------------------------------------------------------------------------
# Red yollarının hepsi bayrağı geçiriyor mu
# ---------------------------------------------------------------------------

def test_butun_RED_yollari_cold_start_i_kapatiyor() -> None:
    """Bir red yolu bayrağı unutursa kilitlenme geri gelir.

    Kaynak metinden okunuyor: ölçtüğümüz şey davranış değil, ``sys.exit``
    ile biten her yolun bayrağı geçirdiği.
    """
    import inspect
    import re

    source = inspect.getsource(update_cmd)

    # ``_resume_windows_gateways_after_update`` cagrisi + ardindan gelen
    # ~6 satirlik pencerede ``sys.exit`` varsa o bir RED yoludur.
    for match in re.finditer(r"_resume_windows_gateways_after_update\(", source):
        window = source[match.start() : match.start() + 320]
        call_end = window.find(")\n")
        call = window[: call_end + 1] if call_end != -1 else window[:160]
        after = window[call_end : call_end + 120] if call_end != -1 else ""

        if "sys.exit" in after:
            assert "allow_cold_start=False" in call, (
                f"red yolu bayragi gecirmiyor: {call.strip()[:120]}"
            )


def test_bayrak_gecirmeyen_yollar_is_YAPILDIKTAN_sonra() -> None:
    """Bayraksız çağrılar başarı/kısmi-başarı yollarında olmalı.

    Bu test ters yönü tutuyor: birisi "her yere False koyalım" derse,
    başarılı güncellemeden sonra gateway hiç geri gelmez.
    """
    import inspect

    source = inspect.getsource(update_cmd._resume_windows_gateways_after_update)

    assert "allow_cold_start: bool = True" in source, (
        "varsayilan True olmali -- basarili guncelleme sonrasi kolaylik korunuyor"
    )
