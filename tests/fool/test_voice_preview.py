"""Ses panelinde model başına dinleme düğmesi.

Dört TTS motoru "kurulu" yazıyor ve kullanıcı hangisinin nasıl konuştuğunu
duymadan seçim yapmak zorunda. Daha kötüsü, bu depodaki en pahalı hata sınıfı
tam burada görünür hâle gelirdi: "cihaz cuda yazıyordu, motor CPU'da
koşuyordu". Ölçülen fark küçük değil -- Kokoro CUDA'da 0,08 sn, CPU'da
saniyeler.

Önizleme bu yüzden yalnızca ses döndürmüyor, GEÇEN SÜREYİ de döndürüyor.
Bir düğmeye basıp "3,4 saniye" görmek, panelin "CUDA" yazmasından daha
inandırıcı bir kanıt.
"""

from __future__ import annotations

import pytest

from fool import voice_preview as vp


def test_deneme_metni_kisa_ve_sabit() -> None:
    """Uzun metin ölçümü sentez süresi yerine metin uzunluğuyla karıştırır."""
    assert 0 < len(vp.PREVIEW_TEXT) <= 80


def test_bilinmeyen_motor_reddediliyor() -> None:
    with pytest.raises(ValueError):
        vp.preview("boyle-bir-motor-yok")


def test_kurulu_olmayan_motor_anlasilir_hata_veriyor(monkeypatch) -> None:
    """"Kurulu değil" ile "sentez patladı" ayrı şeyler; kullanıcı hangisi
    olduğunu bilmeden ne yapacağını bilemez."""
    monkeypatch.setattr(vp, "_status", lambda entry_id: {"installed": False})

    with pytest.raises(ValueError, match="kurulu"):
        vp.preview("kokoro")


def test_basarili_onizleme_ses_ve_sure_donuyor(monkeypatch, tmp_path) -> None:
    audio = tmp_path / "s.wav"
    audio.write_bytes(b"RIFFsahte")

    monkeypatch.setattr(vp, "_status", lambda entry_id: {"installed": True})
    monkeypatch.setattr(vp, "_synthesize", lambda provider, path, text='': str(audio))

    result = vp.preview("kokoro")

    assert result["ok"] is True
    assert result["provider"] == "kokoro"
    assert result["elapsed_ms"] >= 0
    assert result["audio_base64"]
    assert result["mime"] == "audio/wav"


def test_olculen_sure_gercekten_sentezi_kapsiyor(monkeypatch, tmp_path) -> None:
    """Süre, çağrının etrafında ölçülmeli; sabit bir sayı döndürmek yalan olurdu."""
    audio = tmp_path / "s.wav"
    audio.write_bytes(b"RIFF")

    # Tukenen bir iterator kullanmak pytest'in kendi ic cagrilarini da
    # patlatiyor; sayac son degerde kaliyor.
    ticks = [1_000.0, 1_002.5]
    state = {"i": 0}

    def _clock() -> float:
        value = ticks[min(state["i"], len(ticks) - 1)]
        state["i"] += 1

        return value

    monkeypatch.setattr(vp, "_status", lambda entry_id: {"installed": True})
    monkeypatch.setattr(vp, "_synthesize", lambda provider, path, text='': str(audio))
    monkeypatch.setattr(vp.time, "monotonic", _clock)

    assert vp.preview("kokoro")["elapsed_ms"] == 2500


def test_sentez_patlarsa_hata_yutulmuyor(monkeypatch) -> None:
    """Sessizce başarısız olan bir dinleme düğmesi, düğmenin bozuk olması."""
    def _boom(provider, path, text=''):
        raise RuntimeError("engine died")

    monkeypatch.setattr(vp, "_status", lambda entry_id: {"installed": True})
    monkeypatch.setattr(vp, "_synthesize", _boom)

    with pytest.raises(RuntimeError, match="engine died"):
        vp.preview("kokoro")


def test_gecici_dosya_temizleniyor(monkeypatch, tmp_path) -> None:
    """Her önizleme diske bir dosya bırakmamalı."""
    created: list = []

    def _synth(provider, path, text=''):
        p = tmp_path / "out.wav"
        p.write_bytes(b"RIFF")
        created.append(path)
        return str(p)

    monkeypatch.setattr(vp, "_status", lambda entry_id: {"installed": True})
    monkeypatch.setattr(vp, "_synthesize", _synth)

    vp.preview("kokoro")

    from pathlib import Path

    assert created and not Path(created[0]).exists()


def test_stt_motoru_onizlenemiyor() -> None:
    """Konuşma tanımanın dinletecek bir şeyi yok."""
    with pytest.raises(ValueError):
        vp.preview("whisper-turbo")


# ---------------------------------------------------------------------------
# ``text_to_speech_tool`` sözleşmesi
# ---------------------------------------------------------------------------
#
# Bu bölüm bir hatanın ardından yazıldı: ``_synthesize`` aracın dönüş değerini
# doğrudan ``open()``a veriyordu, ama araç bir YOL değil JSON DİZESİ döndürüyor
# ve çağrı ``OSError: Invalid argument`` ile düşüyordu. Yukarıdaki testler bu
# işlevi taklit ettikleri için görmediler; gerçek bir sentez denemesi gördü.
#
# Ders: taklit edilen sınırın SÖZLEŞMESİ ayrıca sınanmalı.

def test_arac_ciktisi_JSON_ve_yol_ondan_okunuyor(monkeypatch, tmp_path) -> None:
    import json

    produced = tmp_path / "gercek.wav"
    produced.write_bytes(b"RIFF")

    import tools.tts_tool as tt

    monkeypatch.setattr(
        tt,
        "text_to_speech_tool",
        lambda *a, **k: json.dumps({"success": True, "file_path": str(produced)}),
    )

    assert vp._synthesize("kokoro", str(tmp_path / "istenen.wav")) == str(produced)


def test_file_paths_listesi_de_okunuyor(monkeypatch, tmp_path) -> None:
    import json

    produced = tmp_path / "parca1.wav"
    import tools.tts_tool as tt

    monkeypatch.setattr(
        tt,
        "text_to_speech_tool",
        lambda *a, **k: json.dumps({"success": True, "file_paths": [str(produced)]}),
    )

    assert vp._synthesize("kokoro", "istenen.wav") == str(produced)


def test_basarisiz_sentez_hata_firlatiyor(monkeypatch) -> None:
    import json

    import tools.tts_tool as tt

    monkeypatch.setattr(
        tt,
        "text_to_speech_tool",
        lambda *a, **k: json.dumps({"success": False, "error": "engine died"}),
    )

    with pytest.raises(RuntimeError, match="engine died"):
        vp._synthesize("kokoro", "x.wav")


def test_duz_yol_donduren_surumle_de_calisiyor(monkeypatch) -> None:
    """Sözleşme değişirse sessizce bozulmamalı."""
    import tools.tts_tool as tt

    monkeypatch.setattr(tt, "text_to_speech_tool", lambda *a, **k: "/tmp/duz.wav")

    assert vp._synthesize("kokoro", "x.wav") == "/tmp/duz.wav"
