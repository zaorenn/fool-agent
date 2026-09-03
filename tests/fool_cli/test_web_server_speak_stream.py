"""/api/audio/speak-stream — desktop streaming TTS over WebSocket."""

from __future__ import annotations

import json
import time
from urllib.parse import urlencode

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from fool_cli import web_server


@pytest.fixture
def stream_client(monkeypatch, _isolate_hermes_home):
    previous_auth_required = getattr(web_server.app.state, "auth_required", None)
    web_server.app.state.auth_required = False

    client = TestClient(web_server.app)
    try:
        yield client
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()
        if previous_auth_required is None:
            if hasattr(web_server.app.state, "auth_required"):
                delattr(web_server.app.state, "auth_required")
        else:
            web_server.app.state.auth_required = previous_auth_required


def _url(token: str | None = None) -> str:
    return f"/api/audio/speak-stream?{urlencode({'token': token or web_server._SESSION_TOKEN})}"


class _FakeStreamer:
    sample_rate = 24000
    channels = 1

    def __init__(self, chunks):
        self.chunks = chunks
        self.requests: list[str] = []

    def stream(self, text):
        self.requests.append(text)
        yield from self.chunks


def _patch_provider(monkeypatch, streamer, cap=4000):
    monkeypatch.setattr("tools.tts_streaming.resolve_streaming_provider", lambda cfg: streamer)
    monkeypatch.setattr("tools.tts_tool._load_tts_config", lambda: {})
    monkeypatch.setattr("tools.tts_tool._get_provider", lambda cfg: "fake")
    monkeypatch.setattr("tools.tts_tool._resolve_max_text_length", lambda provider, cfg: cap)
    # Bu testler saglayici parcalamasini olcuyor, cumle arasi sessizligi
    # degil -- o "fool/prosody.py"nin kendi test dosyasinda kapsanmis
    # (bkz. tests/fool/test_prosody.py). Sessizlik varsayilan ACIK ve her
    # cumleden sonra bir PCM parcasi daha ekliyor; kapatmadan "bir istek =
    # bir kare" varsayimi burada gecerli olmazdi.
    monkeypatch.setattr("fool.prosody.pauses_enabled", lambda cfg: False)






def test_streams_pcm_frames_then_end(stream_client, monkeypatch):
    streamer = _FakeStreamer([b"\x01\x02\x03\x04", b"\x05\x06"])
    _patch_provider(monkeypatch, streamer)

    with stream_client.websocket_connect(_url()) as conn:
        start = conn.receive_json()
        assert start == {"type": "start", "sample_rate": 24000, "channels": 1}

        conn.send_text(json.dumps({"text": "Hello there.", "done": True}))
        assert conn.receive_bytes() == b"\x01\x02\x03\x04"
        assert conn.receive_bytes() == b"\x05\x06"
        assert conn.receive_json() == {"type": "end"}

    assert streamer.requests == ["Hello there."]








def test_long_text_is_split_across_provider_requests(stream_client, monkeypatch):
    streamer = _FakeStreamer([b"\x00\x00"])
    _patch_provider(monkeypatch, streamer, cap=24)

    with stream_client.websocket_connect(_url()) as conn:
        assert conn.receive_json()["type"] == "start"
        conn.send_text(
            json.dumps(
                {"text": "First sentence here. Second sentence here. Third one.", "done": True}
            )
        )
        # One PCM frame per split piece, then end.
        frames = 0
        while True:
            message = conn.receive()
            if message.get("bytes") is not None:
                frames += 1
            else:
                assert json.loads(message["text"]) == {"type": "end"}
                break

    assert len(streamer.requests) > 1
    assert frames == len(streamer.requests)
    # Nothing lost in the split: every sentence reached the provider.
    joined = " ".join(streamer.requests)
    for fragment in ("First sentence here.", "Second sentence here.", "Third one."):
        assert fragment in joined


def test_split_text_respects_cap_and_preserves_content():
    text = "Alpha beta. Gamma delta epsilon. Zeta eta theta iota kappa."
    pieces = web_server._split_text_for_speak_stream(text, 30)
    assert pieces
    assert all(len(piece) <= 30 for piece in pieces)
    joined = " ".join(pieces)
    for word in text.replace(".", "").split():
        assert word in joined




# ---------------------------------------------------------------------------
# Yerel motorlar (chunked API'si yok) — FOOL-SEAM: local-sentence-streaming
# ---------------------------------------------------------------------------
#
# Onceki davranis: yerel bir motor secili oldugunda bu uc HEMEN
# ``{"type": "fallback"}`` gonderiyordu ve istemci AJANIN TUM CEVABINI
# bekleyip metnin TAMAMINI TEK CAGRIDA sentezliyordu. Kullanicinin "cevap
# 10 saniye gec geliyor, Jarvis gibi hissettirmiyor" dedigi sey buydu.


def _write_wav(path, *, rate=22050, channels=1, frames=b"\x01\x00\x02\x00"):
    import wave

    with wave.open(path, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)


def _patch_local_provider(monkeypatch, *, provider="kokoro", rate=22050, calls=None):
    def fake_synth(text, output_path=None, provider=None, **kw):
        _write_wav(output_path, rate=rate)
        if calls is not None:
            calls.append(text)
        return json.dumps({"success": True, "file_path": output_path})

    monkeypatch.setattr("tools.tts_streaming.resolve_streaming_provider", lambda cfg: None)
    monkeypatch.setattr("tools.tts_tool._load_tts_config", lambda: {})
    monkeypatch.setattr("tools.tts_tool._get_provider", lambda cfg: provider)
    monkeypatch.setattr("tools.tts_tool._resolve_max_text_length", lambda provider, cfg: 4000)
    monkeypatch.setattr("tools.tts_tool.text_to_speech_tool", fake_synth)


def test_local_provider_streams_per_sentence_with_learned_rate(stream_client, monkeypatch):
    """"start" bekleniyor: gercek orneklem hizi ilk cumle sentezlenene kadar
    bilinmiyor, o yuzden yalniz o ANDAN sonra gonderiliyor -- eager degil."""
    calls: list[str] = []
    _patch_local_provider(monkeypatch, provider="kokoro", rate=22050, calls=calls)

    with stream_client.websocket_connect(_url()) as conn:
        conn.send_text(json.dumps({"text": "First sentence. Second sentence.", "done": True}))

        start = conn.receive_json()
        assert start == {"type": "start", "sample_rate": 22050, "channels": 1}

        frames = 0
        while True:
            message = conn.receive()
            if message.get("bytes") is not None:
                frames += 1
            else:
                assert json.loads(message["text"]) == {"type": "end"}
                break

    assert frames >= 1
    assert any("First sentence" in c for c in calls)
    assert any("Second sentence" in c for c in calls)


def test_no_provider_at_all_still_falls_back_immediately(stream_client, monkeypatch):
    """``_get_provider`` "none" dönerse (hiçbir motor kurulu/yapılandırılı
    değil) davranış AYNEN eski gibi: hemen fallback, senkron yol denenmiyor."""
    monkeypatch.setattr("tools.tts_streaming.resolve_streaming_provider", lambda cfg: None)
    monkeypatch.setattr("tools.tts_tool._load_tts_config", lambda: {})
    monkeypatch.setattr("tools.tts_tool._get_provider", lambda cfg: "none")
    monkeypatch.setattr("tools.tts_tool._resolve_max_text_length", lambda provider, cfg: 4000)

    with stream_client.websocket_connect(_url()) as conn:
        assert conn.receive_json() == {"type": "fallback"}
        with pytest.raises(WebSocketDisconnect):
            conn.receive_json()


def test_local_synthesis_failure_ends_session_CLEANLY_without_start(stream_client, monkeypatch):
    """Bir cümle patlarsa sunucu ÇÖKMEMELİ ve SESSİZLİĞİ SÖYLEMELİ.

    Sözleşme GÜÇLENDİRİLDİ: eskiden burada ``end`` bekleniyordu ve gerekçesi
    "istemci ``started`` bayrağıyla ayırt eder" idi. Doğru ama kırılgan --
    sunucu "oturum temiz kapandı" derken istemcinin ondan "hiçbir şey
    duyulmadı" sonucunu ÇIKARMASI gerekiyordu. İki ayrı şeyi tek kareye
    yüklemek, aradaki farkı her yeni istemcinin yeniden keşfetmesi demek.

    Sunucu artık gerçekten ilettiği baytı sayıyor ve sıfırsa ``fallback``
    gönderiyor. ``end`` yalnızca ses AKMIŞ bir oturumun kapanışı.
    ``fallback`` ise doğrudan "hiç ses çıkmadı, metni sen oku" demek --
    istemcinin zaten uyguladığı davranışın adı konmuş hâli.
    """

    def fake_synth(text, output_path=None, provider=None, **kw):
        return json.dumps({"success": False, "error": "motor coktu"})

    monkeypatch.setattr("tools.tts_streaming.resolve_streaming_provider", lambda cfg: None)
    monkeypatch.setattr("tools.tts_tool._load_tts_config", lambda: {})
    monkeypatch.setattr("tools.tts_tool._get_provider", lambda cfg: "kokoro")
    monkeypatch.setattr("tools.tts_tool._resolve_max_text_length", lambda provider, cfg: 4000)
    monkeypatch.setattr("tools.tts_tool.text_to_speech_tool", fake_synth)

    with stream_client.websocket_connect(_url()) as conn:
        conn.send_text(json.dumps({"text": "This will fail.", "done": True}))
        # "start" hic gelmiyor -- hicbir sentez basarili olmadi. Tek mesaj
        # "fallback" olmali, arada ne ikili bir kare ne baska bir sey.
        assert conn.receive_json() == {"type": "fallback"}


def test_one_failed_sentence_does_not_kill_the_rest_of_the_reply(stream_client, monkeypatch):
    """Bir cümlenin düşmesi turun GERİ KALANINI öldürmemeli.

    Ölçülen hata
    ------------
    ``try/except`` bütün ``for sentence in _sentences()`` döngüsünü sarıyordu.
    Tek bir geçici hata -- motor süreci boşaltma sırasında toplandı,
    sağlayıcı bir HTTP 500 döndü, motor bir cümleyi sindiremedi -- kalan
    BÜTÜN cümlelerin sentezini iptal ediyordu.

    Sessiz sınıfın ders kitabı hâli: ses zaten başlamış olduğu için istemci
    ``end`` karesini "başarıyla çalındı" diye okuyor. Kullanıcı cevabın ilk
    yarısını duyuyor, ikinci yarısı hiç konuşulmuyor ve hiçbir yerde hata
    görünmüyor.
    """

    calls: list[str] = []

    def flaky_synth(text, output_path=None, provider=None, **kw):
        calls.append(text)
        # IKINCI cumle duser; birinci ve ucuncu calisir.
        if len(calls) == 2:
            raise RuntimeError("gecici hata")
        _write_wav(output_path)
        return json.dumps({"success": True, "file_path": output_path})

    monkeypatch.setattr("tools.tts_streaming.resolve_streaming_provider", lambda cfg: None)
    monkeypatch.setattr("tools.tts_tool._load_tts_config", lambda: {})
    monkeypatch.setattr("tools.tts_tool._get_provider", lambda cfg: "kokoro")
    monkeypatch.setattr("tools.tts_tool._resolve_max_text_length", lambda provider, cfg: 4000)
    monkeypatch.setattr("tools.tts_tool.text_to_speech_tool", flaky_synth)

    with stream_client.websocket_connect(_url()) as conn:
        conn.send_text(
            json.dumps(
                {
                    "text": (
                        "Birinci cumle burada duruyor ve yeterince uzun. "
                        "Ikinci cumle sentezde dusecek olan cumledir. "
                        "Ucuncu cumle bundan sonra hala konusulmali."
                    ),
                    "done": True,
                }
            )
        )

        assert conn.receive_json() == {"type": "start", "sample_rate": 22050, "channels": 1}

        audio_frames = 0
        while True:
            message = conn.receive()
            if message.get("bytes") is not None:
                audio_frames += 1
                continue
            # Ses AKTI: oturum "end" ile kapaniyor, "fallback" ile degil.
            assert json.loads(message["text"]) == {"type": "end"}
            break

    # UC cumlenin ucu de DENENDI -- ikincinin dusmesi ucuncuyu engellemedi.
    assert len(calls) == 3, calls
    assert audio_frames >= 1
