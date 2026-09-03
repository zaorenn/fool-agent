"""Panelin gösterdiği motor, GERÇEKTEN konuşacak motor olmalı.

Ölçülen hata
------------
Taze bir kurulumda Ayarlar "Text-To-Speech Provider: **Edge**" yazıyordu --
raporlama yolu seçim yokken ``edge``e düşüyor diye. Oysa sentez yolu
(``tools/tts_tool.py::_get_provider``) seçim yokken kurulu YEREL bir motoru
seçiyor; edge yalnızca kullanıcı onu açıkça yazdıysa kullanılıyor
(``FOOL-SEAM: local-only-tts``).

Yani panel bir ad gösteriyor, kullanıcı başka bir ses duyuyor ve sebebini
hiçbir yerde bulamıyor. Bu kod tabanının tekrar tekrar düzelttiği hata sınıfı.

Sınav GERÇEK fonksiyonu koşturuyor. Aynı kuralı testin içinde yeniden yazmak,
yalnızca kendi kopyasını sınamak olurdu.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def features(monkeypatch):
    from fool_cli import nous_subscription

    # Portal cagrisi AGA gidiyor; sinanan sey o degil.
    monkeypatch.setattr(
        nous_subscription, "get_nous_portal_account_info", lambda **k: None, raising=False
    )

    def _run(config: dict, resolved: str = "kokoro"):
        monkeypatch.setattr("tools.tts_tool._get_provider", lambda cfg: resolved, raising=False)

        return nous_subscription.get_nous_subscription_features(config)

    return _run


def _label(result) -> str:
    return str(result.tts.current_provider or "").lower()


def test_secim_yokken_EDGE_denmiyor(features) -> None:
    """Eski davranış buydu ve yalandı."""
    assert "edge" not in _label(features({"tts": {}}))


def test_secim_yokken_COZUCUNUN_dedigi_raporlaniyor(features) -> None:
    assert "piper" in _label(features({"tts": {}}, resolved="piper"))


def test_ACIK_secim_cozucuye_SORULMADAN_kullaniliyor(features) -> None:
    """Kullanıcı bulut motoru açıkça seçtiyse panel onu göstermeli."""
    assert "edge" in _label(features({"tts": {"provider": "edge"}}, resolved="piper"))


def test_kaynak_dosyada_edge_varsayilani_KALMADI() -> None:
    """Satır geri gelirse panel yine yalan söyler."""
    from pathlib import Path

    source = Path("fool_cli/nous_subscription.py").read_text(encoding="utf-8")

    assert 'tts_cfg.get("provider") or "edge"' not in source
