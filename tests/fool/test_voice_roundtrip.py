"""Gerçek yerel ses turu: STT -> LLM -> TTS.

Bu oturumda ölçülen hataların çoğu PARÇALARIN ARASINDA duruyordu -- her biri
tek başına doğru görünüyor, birleşince kopuyordu:

  * ``cuda_ready`` motora değil sürücüye soruyordu,
  * ``_synthesize`` bir yol bekliyordu, araç JSON döndürüyordu,
  * ölçüm sonuçları katalog kimliğiyle saklanıyordu, yapılandırma sağlayıcı
    adı yazıyordu.

Bu tur o boşluğu kapatıyor. Gerçek koşum ``-m integration`` ile ayrı: modelleri
yüklüyor, GPU kullanıyor ve dakikalar sürüyor -- varsayılan pakette olamaz.

Ölçüldü (bu makine, RTX 4070 Ti SUPER, ısınmış):

    aşama                  qwen3     piper
    user speech (TTS)     22,26s     1,40s   <- mikrofonun yerine gecen kosum
    STT (local)            2,68s     0,33s
    LLM (local)            5,26s     4,96s
    reply speech (TTS)     4,78s     0,05s
    TOPLAM                34,98s     6,74s

Kullanıcının HİSSETTİĞİ gecikme STT + LLM + cevap TTS:
    qwen3  12,72s      piper  5,34s   (bunun 4,96s'i modelin kendisi)

Yani seslendirme motorunu değiştirmek turu 12,7 saniyeden 5,3 saniyeye
indiriyor ve ses yığını neredeyse bedava hâle geliyor.
"""

from __future__ import annotations

import inspect

import pytest

from fool import voice_roundtrip as rt


# ---------------------------------------------------------------------------
# Sözleşme (hızlı)
# ---------------------------------------------------------------------------

def test_deneme_cumlesi_modeli_degil_BORUYU_siniyor() -> None:
    """Amaç modeli sınamak değil; cevabı belirli ve kısa olmalı."""
    assert "capital of France" in rt.DEFAULT_UTTERANCE
    assert len(rt.DEFAULT_UTTERANCE) < 120


def test_tur_dort_asamayi_da_kapsiyor() -> None:
    source = inspect.getsource(rt.run)

    for stage in ("user speech (TTS)", "STT (local)", "LLM (local)", "reply speech (TTS)"):
        assert stage in source


def test_tur_uretilen_dosyalari_temizliyor() -> None:
    """Her koşum diske ses dosyası bırakmamalı."""
    source = inspect.getsource(rt.run)

    assert "finally" in source
    assert "unlink" in source


def test_hata_YUTULMUYOR() -> None:
    """Bu bir kapı; "kısmen çalıştı" diye bir sonucu yok."""
    source = inspect.getsource(rt.run)

    assert "raise RuntimeError" in source


def test_bos_stt_ciktisi_basari_sayilmiyor() -> None:
    assert "STT bos metin dondu" in inspect.getsource(rt.run)


def test_bos_model_cevabi_basari_sayilmiyor() -> None:
    assert "model bos cevap dondu" in inspect.getsource(rt.run)


def test_sentez_JSON_sozlesmesini_okuyor() -> None:
    """``text_to_speech_tool`` yol değil JSON döndürüyor -- bir kez düşmüştü."""
    source = inspect.getsource(rt._synth)

    assert "json.loads" in source
    assert "file_path" in source


# ---------------------------------------------------------------------------
# Gerçek koşum (yavaş, ayrı)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_gercek_yerel_ses_turu(monkeypatch) -> None:
    """Uçtan uca: ses üret -> yaziya dök -> modele sor -> cevabı seslendir.

    Ağa hiç çıkmıyor. Tek bir aşama düşerse tur düşer.

    Bu kapı GERÇEK kuruluma karşı koşuyor: pytest'in hermetik ortamı
    ``FOOL_HOME``u geçici bir dizine çeviriyor ve orada ne model ne de
    seslendirme motoru var. Kapının işi kurulumu doğrulamak, taklidi değil --
    o yüzden gerçek ev geri bağlanıyor.
    """
    import os
    from pathlib import Path

    real_home = Path(os.path.expandvars("%LOCALAPPDATA%")) / "fool"
    if not real_home.is_dir():
        pytest.skip("gercek kurulum bulunamadi")

    monkeypatch.setenv("FOOL_HOME", str(real_home))

    from fool_cli import config as _config

    _config._HERMES_HOME_ENSURED.clear()

    from fool import voice_models as vm

    installed = [
        e.provider_id or e.id
        for e in vm.CATALOG
        if e.kind == "tts" and vm.status(e.id).get("installed")
    ]
    if not installed:
        pytest.skip("kurulu yerel seslendirme motoru yok")

    result = rt.run(provider=installed[0])

    assert result["ok"] is True
    assert result["heard"], "STT hicbir sey duymadi"
    assert result["reply"], "model cevap vermedi"
    # Cevap DOGRU olmali: boru calisiyor ama sacmaliyorsa tur gecmis sayilmaz.
    assert "paris" in result["reply"].lower()
    assert len(result["stages"]) == 4
    assert all(stage["seconds"] >= 0 for stage in result["stages"])
