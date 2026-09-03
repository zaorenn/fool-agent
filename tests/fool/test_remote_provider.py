"""Sağlayıcı BAŞKA bir makinedeyken yerel boşaltma çalışmamalı.

İstenen düzen: modeller güçlü masaüstündeki LM Studio'da; alt kattaki zayıf
dizüstü The Fool'u kendi hafızası ve kendi ayarlarıyla çalıştırıyor ve
yalnızca sağlayıcı olarak masaüstünü kullanıyor.

O düzende ``loaded_models()`` uzaktaki makineyi doğru okuyor ama ``unload()``
YEREL ``lms`` komutunu çalıştırıyor: dizüstü, masaüstünün listesine bakarak
kendi modellerini kapatmaya çalışıyor.
"""

from __future__ import annotations

import pytest

from fool import lmstudio_residency as residency


@pytest.mark.parametrize(
    "url",
    ["", "http://localhost:1234/v1", "http://127.0.0.1:1234", "localhost:1234", "http://[::1]:1234"],
)
def test_yerel_adresler_AYNI_makine(url: str) -> None:
    assert residency.is_same_machine(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.50:1234/v1",
        "http://10.0.0.4:1234",
        "http://masaustu.local:1234/v1",
        "https://desk.example.com/v1",
    ],
)
def test_ag_adresleri_BASKA_makine(url: str) -> None:
    """``is_local_endpoint`` bunlara "yerel" diyor -- ama o, zaman aşımı ayarı
    için "yeterince yakın" diye soruyor. Buradaki soru "aynı makine mi"."""
    assert residency.is_same_machine(url) is False


def test_okunamayan_adres_BASKA_makine_sayiliyor() -> None:
    """Emin olmadan boşaltmamak, gereksiz model taşımaktan ucuz."""
    assert residency.is_same_machine("http://[bozuk") is False


def test_UZAK_saglayicida_hicbir_sey_bosaltilmiyor(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(residency, "loaded_models", lambda *a, **k: ["a", "b"])
    monkeypatch.setattr(residency, "busy_models", lambda: set())
    monkeypatch.setattr(residency, "unload", lambda mid: calls.append(mid) or True)

    dropped = residency.enforce_single("http://192.168.1.50:1234/v1", keep="a")

    assert dropped == []
    assert calls == []


def test_YEREL_saglayicida_bosaltma_calisiyor(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(residency, "loaded_models", lambda *a, **k: ["a", "b"])
    monkeypatch.setattr(residency, "busy_models", lambda: set())
    monkeypatch.setattr(residency, "unload", lambda mid: calls.append(mid) or True)

    dropped = residency.enforce_single("http://localhost:1234/v1", keep="a")

    assert dropped == ["b"]
    assert calls == ["b"]
