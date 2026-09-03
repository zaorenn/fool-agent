"""Yerel motorlar chunked API'si YOK diye tüm cevap bitene kadar sessizdi.

Ölçülen kök sebep: ``tools/tts_streaming.py`` yalnızca dört bulut sağlayıcı
için ``StreamingTTSProvider`` tanımlıyor. Yerel bir motor seçiliyken
``/api/audio/speak-stream`` hemen ``{"type": "fallback"}`` gönderiyordu ve
istemci AJANIN TÜM CEVABINI bekleyip metnin TAMAMINI TEK ÇAĞRIDA
sentezliyordu. Kullanıcının "cevap 10 saniye geç geliyor, Jarvis gibi
hissettirmiyor" dediği şey buydu.

``LocalSentenceStreamer`` senkron ``text_to_speech_tool``ü cümle başına
çağırıp aynı ``StreamingTTSProvider`` yüzeyini (``sample_rate``,
``channels``, ``stream()``) sunuyor. Bu dosya onun kendi başına doğru
davrandığını tutuyor; WS ucunun onu gerçekten kullandığı ayrı bir kaygı
(``fool_cli/web_server.py``, FOOL-SEAM: local-sentence-streaming).
"""

from __future__ import annotations

import json
import wave

import pytest

from fool import voice_stream_local as vsl


def _write_wav(path: str, *, rate: int = 22_050, channels: int = 1, sampwidth: int = 2, frames: bytes = b"\x00\x01" * 100) -> None:
    with wave.open(path, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sampwidth)
        handle.setframerate(rate)
        handle.writeframes(frames)


# ---------------------------------------------------------------------------
# usable_local_provider
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["kokoro", "styletts2", "  kyutai  ", "PIPER"])
def test_gercek_saglayici_adi_KULLANILABILIR(value) -> None:
    assert vsl.usable_local_provider(value) is True


@pytest.mark.parametrize("value", ["none", "None", "  ", "", None])
def test_yok_ya_da_bos_saglayici_KULLANILAMAZ(value) -> None:
    # "none" -- ``_get_provider`` hicbir motor kurulu/yapilandirili degilken
    # bunu donuyor (bkz. tools/tts_tool.py FOOL-SEAM: local-only-tts). Onu
    # yine de denemek her cumlede ayni hatayi uretip oturumu geciktirirdi.
    assert vsl.usable_local_provider(value) is False


# ---------------------------------------------------------------------------
# LocalSentenceStreamer.stream
# ---------------------------------------------------------------------------

def test_gercek_orneklem_hizi_ILK_sentezden_OGRENILIYOR(tmp_path, monkeypatch) -> None:
    """Sabit bir sayı yazmak riskliydi: yanlışsa oynatma perdesi/bozuk
    çıkar ama ÇÖKMEZ -- sessiz bir kalite hatası. WAV başlığından okumak
    bunu tamamen eler."""
    wav_path = str(tmp_path / "out.wav")
    _write_wav(wav_path, rate=22_050, channels=1)

    def fake_synth(text, output_path=None, provider=None, **kw):
        _write_wav(output_path, rate=22_050, channels=1)
        return json.dumps({"success": True, "file_path": output_path})

    monkeypatch.setattr("tools.tts_tool.text_to_speech_tool", fake_synth)

    streamer = vsl.LocalSentenceStreamer("piper")
    assert streamer.sample_rate == 0  # henuz sentezlenmedi

    frames = list(streamer.stream("Merhaba."))

    assert streamer.sample_rate == 22_050
    assert streamer.channels == 1
    assert frames and all(isinstance(f, bytes) and f for f in frames)


def test_provider_KENDI_yoluna_yaziyorsa_ORADAN_okunuyor(tmp_path, monkeypatch) -> None:
    """Uzun metin parçalara bölünüyor ve provider isteği yoldan farklı bir
    dosyaya yazabiliyor -- cevaptaki yol kullanılmalı (aynı desen
    ``fool/voice_preview.py``'de)."""
    elsewhere = str(tmp_path / "elsewhere.wav")
    _write_wav(elsewhere, rate=24_000)

    def fake_synth(text, output_path=None, provider=None, **kw):
        return json.dumps({"success": True, "file_path": elsewhere})

    monkeypatch.setattr("tools.tts_tool.text_to_speech_tool", fake_synth)

    streamer = vsl.LocalSentenceStreamer("kyutai")
    frames = list(streamer.stream("Merhaba."))

    assert streamer.sample_rate == 24_000
    assert frames


def test_gecici_dosyalar_TEMIZLENIYOR(tmp_path, monkeypatch) -> None:
    elsewhere = str(tmp_path / "elsewhere.wav")
    _write_wav(elsewhere)
    captured = {}

    def fake_synth(text, output_path=None, provider=None, **kw):
        captured["tmp"] = output_path
        return json.dumps({"success": True, "file_path": elsewhere})

    monkeypatch.setattr("tools.tts_tool.text_to_speech_tool", fake_synth)

    list(vsl.LocalSentenceStreamer("kyutai").stream("Merhaba."))

    import os

    assert not os.path.exists(elsewhere)
    assert not os.path.exists(captured["tmp"])


def test_basarisiz_sentez_ISTISNA_firlatiyor(monkeypatch) -> None:
    """Hata YUTULMUYOR: çağıran taraf (WS ucu) bunu zaten "sentez
    başarısız" olarak günlüğe yazıp oturumu normal bitiriyor. Burada
    yutmak, o günlüğü kaybetmek olurdu."""

    def fake_synth(text, output_path=None, provider=None, **kw):
        return json.dumps({"success": False, "error": "motor coktu"})

    monkeypatch.setattr("tools.tts_tool.text_to_speech_tool", fake_synth)

    with pytest.raises(RuntimeError, match="motor coktu"):
        list(vsl.LocalSentenceStreamer("chatterbox").stream("Merhaba."))


def test_int16_OLMAYAN_ornek_genisligi_REDDEDILIYOR(tmp_path, monkeypatch) -> None:
    """Protokol yalnızca ham int16 PCM taşıyor. Başka bir genişliği
    sessizce göndermek gürültü çalar -- açıkça reddetmek doğru cevap."""
    wav_path = str(tmp_path / "float.wav")
    _write_wav(wav_path, sampwidth=4)

    def fake_synth(text, output_path=None, provider=None, **kw):
        return json.dumps({"success": True, "file_path": wav_path})

    monkeypatch.setattr("tools.tts_tool.text_to_speech_tool", fake_synth)

    with pytest.raises(RuntimeError, match="int16"):
        list(vsl.LocalSentenceStreamer("styletts2").stream("Merhaba."))


def test_duz_yol_donen_eski_bicimle_de_calisiyor(tmp_path, monkeypatch) -> None:
    """JSON değil de çıplak bir yol döndüren eski/basit bir sağlayıcı da
    çalışmalı — ``text_to_speech_tool`` sözleşmesi JSON dizesi ama savunmacı
    davranmak ucuz."""

    def fake_synth(text, output_path=None, provider=None, **kw):
        _write_wav(output_path)
        return output_path

    monkeypatch.setattr("tools.tts_tool.text_to_speech_tool", fake_synth)

    frames = list(vsl.LocalSentenceStreamer("piper").stream("Merhaba."))

    assert frames


def test_MP3_donen_saglayicilar_yerel_yola_SOKULMUYOR():
    """Sınıfın adı "yerel" diyor; kural bunu hiç uygulamıyordu.

    Ölçülen hata: ``usable_local_provider`` boş olmayan ve ``"none"`` olmayan
    HER adı kabul ediyordu. ``tts.provider: edge`` seçili olduğunda -- ki
    desteklenen bir sağlayıcı -- bu uç senkron cümle yoluna giriyor,
    ``_generate_edge_tts`` uzantıya hiç bakmadan ``.wav`` yoluna MP3 baytları
    yazıyor ve ``wave.open`` "file does not start with RIFF id" ile düşüyor.

    Bedeli iki katmanlı: her cümle bir Microsoft gidiş dönüşü israf ediyor VE
    istemci yedek yola ancak o gecikmeden sonra düşüyor. Aynı şekil
    ``minimax`` ve MP3 dönen her sağlayıcı için geçerli.
    """
    from fool.voice_stream_local import usable_local_provider

    # WAV ureten YEREL motorlar -- katalogdan turetiliyor.
    assert usable_local_provider("kokoro") is True
    assert usable_local_provider("piper") is True
    # Katalog kimligi de saglayici kimligi de kabul ediliyor.
    assert usable_local_provider("qwen3") is True
    assert usable_local_provider("qwen3-tts") is True

    # MP3 donen bulut saglayicilari BU yola girmiyor.
    assert usable_local_provider("edge") is False
    assert usable_local_provider("minimax") is False

    # Eski kural korunuyor.
    assert usable_local_provider("none") is False
    assert usable_local_provider("") is False


# ---------------------------------------------------------------------------
# Katalogda OLMAYAN, yerel kurulmuş motorlar
# ---------------------------------------------------------------------------


def test_kayitli_EKLENTI_motoru_da_akisa_giriyor(monkeypatch) -> None:
    """Lisansı dağıtıma izin vermeyen bir motor katalogda OLAMIYOR ama
    kullanıcı kendi eklenti klasörüne kurabiliyor. Yalnızca kataloğa bakmak,
    o motorda cümle-cümle akışı SESSİZCE kapatıyordu -- kullanıcı yalnızca
    "ses geç başlıyor" görür ve sebebi hiçbir yerde yazmazdı."""
    from fool import voice_stream_local

    class _Fake:
        name = "indextts2"

    monkeypatch.setattr(
        "agent.tts_registry.list_providers", lambda *a, **k: [_Fake()], raising=False
    )

    assert voice_stream_local.usable_local_provider("indextts2") is True


def test_kayitta_olmayan_ad_hala_REDDEDILIYOR(monkeypatch) -> None:
    from fool import voice_stream_local

    monkeypatch.setattr(
        "agent.tts_registry.list_providers", lambda *a, **k: [], raising=False
    )

    assert voice_stream_local.usable_local_provider("edge") is False
