"""Mikrofon sesi sessizce buluta gitmemeli.

``tools/transcription_tools.py`` içinde ``stt.provider`` AÇIKÇA yazılmışsa
kullanıcının seçimine uyuluyor -- upstream bunu belgeliyor ve doğru. Ama
otomatik algılama yolunda (``stt.provider`` yoksa) merdiven şöyle:

    local > groq > openai > mistral > xai > elevenlabs > deepinfra

Yani ``faster_whisper`` yüklenemezse -- CUDA kütüphanesi eksik, tekerlek
bozuk, sürüm çakışması -- mikrofon kaydı sessizce üçüncü bir tarafa
yükleniyor. Ortada ``logger.info`` var, kullanıcıya görünen hiçbir şey yok.

Bu, sohbet için OpenAI anahtarı olan HERKESİ vuruyor; anahtar zaten orada.
Kullanıcının kurulu ``config.yaml``ında ``stt.provider`` yok, yalnızca
``stt.local.*`` var -- yani tam bu yoldan geçiyor.

Yerel-önce bir üründe bulut, açık bir tercih olmadan seçilemez.
"""

from __future__ import annotations

import pytest

from fool import local_only


# ---------------------------------------------------------------------------
# Politika
# ---------------------------------------------------------------------------

def test_bulut_varsayilan_olarak_kapali() -> None:
    assert local_only.cloud_stt_allowed({}) is False
    assert local_only.cloud_stt_allowed({"local": {"device": "cuda"}}) is False


def test_acik_tercih_bulutu_acar() -> None:
    """Kullanıcı bilerek açtıysa yol açık — makine onun."""
    assert local_only.cloud_stt_allowed({"allow_cloud_fallback": True}) is True


@pytest.mark.parametrize("raw", ["true", "yes", "1", "on"])
def test_metin_dogruluk_degerleri_de_kabul(raw: str) -> None:
    """``fool config set`` değerleri metin olarak yazıyor."""
    assert local_only.cloud_stt_allowed({"allow_cloud_fallback": raw}) is True


@pytest.mark.parametrize("raw", ["false", "no", "0", "off", "", None])
def test_yanlis_degerler_kapali_kalir(raw: object) -> None:
    assert local_only.cloud_stt_allowed({"allow_cloud_fallback": raw}) is False


def test_bozuk_yapilandirma_kapali_tarafa_duser() -> None:
    """Okunamayan bir değer buluta açılmakla sonuçlanmamalı."""
    assert local_only.cloud_stt_allowed(None) is False
    assert local_only.cloud_stt_allowed("nonsense") is False


# ---------------------------------------------------------------------------
# Gerçek çözümleyici
# ---------------------------------------------------------------------------

@pytest.fixture
def no_local_stt(monkeypatch):
    """Yerel whisper yok: otomatik algılama bulut merdivenine düşer."""
    import tools.transcription_tools as tt

    monkeypatch.setattr(tt, "_HAS_FASTER_WHISPER", False)
    monkeypatch.setattr(tt, "_has_local_command", lambda: False)
    monkeypatch.setattr(tt, "_try_lazy_install_stt", lambda: False)
    monkeypatch.setattr(tt, "_HAS_OPENAI", True)
    # Anahtar VAR: sohbet icin OpenAI/Groq anahtari olan bir kullanici.
    monkeypatch.setattr(tt, "_resolve_provider_key", lambda *a, **k: "anahtar-var")

    return tt


def test_yerel_yoksa_sessizce_buluta_gecmiyor(no_local_stt) -> None:
    tt = no_local_stt

    # ``stt.provider`` YOK -- kullanicinin kurulu yapilandirmasinin sekli.
    assert tt._get_provider({"local": {"device": "cuda"}}) == "none"


def test_acik_tercihle_bulut_yine_calisiyor(no_local_stt) -> None:
    tt = no_local_stt

    provider = tt._get_provider({"allow_cloud_fallback": True, "local": {"device": "cuda"}})

    assert provider != "none", "acik tercihe ragmen bulut kapali kaldi"


def test_kullanicinin_acik_saglayici_secimi_engellenmiyor(no_local_stt) -> None:
    """``provider: groq`` yazan kullanıcı bilerek bulut istiyor."""
    tt = no_local_stt

    assert tt._get_provider({"provider": "groq"}) == "groq"


def test_yerel_varsa_hicbir_sey_degismiyor(monkeypatch) -> None:
    import tools.transcription_tools as tt

    monkeypatch.setattr(tt, "_HAS_FASTER_WHISPER", True)

    assert tt._get_provider({"local": {"device": "cuda"}}) == "local"
