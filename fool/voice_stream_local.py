"""Yerel TTS motorlarını canlı seslendirmeye kat — chunked API'leri yok.

Ölçülen sorun
-------------
``tools/tts_streaming.py`` yalnızca dört bulut sağlayıcı için ``stream()``
tanımlıyor (elevenlabs, gemini, openai, xai). Yerel bir motor seçiliyse
``resolve_streaming_provider`` ``None`` dönüyor ve WS ucu hemen
``{"type": "fallback"}`` gönderiyordu. İstemci de bunu görünce AJANIN TÜM
CEVABI bitmesini bekliyor, sonra tüm metni TEK ÇAĞRIDA sentezliyordu.

Sonuç ölçüldü: LLM cevabı + tam metin sentezi ardışık — kullanıcı "Jarvis
gibi hissettirmiyor, cevap 10 saniye geç geliyor" dedi ve haklıydı. STT
zaten anında modele gidiyordu (``submitAudio`` transkripsiyondan hemen
sonra ``prompt.submit`` çağırıyor); gecikme TAMAMEN ses tarafındaydı.

Çözüm
-----
Yerel motorların chunked bir API'si yok ama HIZLI: kokoro sıcakken 0,20 sn,
styletts2 0,56 sn (ölçüldü). Cümle uzunluğunda bir metni senkron sentezlemek
zaten "gerçek zamanlıya yakın" -- eksik olan sadece bunu CÜMLE CÜMLE
yapıp yayınlamak, tüm cevabı bekleyip TEK metni sentezlemek değil.

``LocalSentenceStreamer`` bu yüzden ``StreamingTTSProvider`` ile AYNI
arayüzü (``sample_rate``, ``channels``, ``stream(text) -> Iterator[bytes]``)
sunuyor ama arkasında ``/api/audio/speak``'in kullandığı senkron
``text_to_speech_tool`` var. Çağıran taraf (``fool_cli/web_server.py``)
ikisini aynı döngüde kullanabiliyor.

Örnek hızı SONRADAN öğreniliyor
--------------------------------
Bulut akıtıcılar ``sample_rate``i sınıf sabiti olarak biliyor (API'nin
kendi sözleşmesi). Yerel motorlarda böyle bir sözleşme yok ve sabit bir
sayı YAZMAK riskli: yanlış olursa oynatma hızı/perdesi bozuk çıkar ama
ÇÖKMEZ -- sessiz bir kalite hatası. Bunun yerine ilk gerçek sentezin WAV
başlığından okunuyor; ``sample_rate``/``channels`` o ana kadar 0.

Neden ffmpeg gerekmiyor
-----------------------
WAV başlığı burada elle çözülüyor (``read_wav_as_int16``), yani sesli sohbet
yoluna ffmpeg bağımlılığı eklenmiyor.

Bir zamanlar burada stdlib'in ``wave`` modülü vardı ve bu satırlar "her yerel
motor 16-bit PCM yazıyor" diyordu. YANLIŞTI: Chatterbox ``pcm_f32le`` yazıyor
(doğrulandı, ``ffprobe`` -> ``sample_fmt=flt``) ve ``wave`` kayan noktayı
okumuyor. Yani cümle-cümle akış varsayılan klonlama motorunda HİÇ çalışmamış;
her cümle düşüyor, oturum ``fallback`` ile kapanıyor ve istemci sessizce yavaş
tam-metin yoluna geri düşüyordu. Yorum ile kod ayrışmıştı ve tek belirtisi
gecikmeydi.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import contextlib
import json
import os
import struct
import tempfile
import wave
from typing import Any, Iterator, Optional


def _wav_capable_providers() -> frozenset[str]:
    """WAV üreten YEREL motorlar -- türetiliyor, elle yazılmıyor.

    İki kaynak, ve ikincisi sonradan eklendi:

    1. **Katalog.** Uygulamayla gelen her yerel motor orada duruyor, yani yeni
       bir motor eklendiğinde burası kendiliğinden öğreniyor.

    2. **Kayıtlı TTS eklentileri.** Bazı motorlar katalogda OLAMIYOR: lisansı
       dağıtıma izin vermeyen bir motoru kullanıcı kendi eklenti klasörüne
       kurabiliyor (bkz. ``docs/fool/OPTIONAL-VOICE-ENGINES.md``). Yalnızca
       kataloğa bakmak, o motorda cümle-cümle akışı SESSİZCE kapatıyordu --
       kullanıcı yalnızca "ses geç başlıyor" görürdü ve sebebi hiçbir yerde
       yazmazdı. Eklenti sağlayıcı sözleşmesi zaten WAV yazıyor.

    İkisi de okunamazsa boş küme dönüyor ve çağıran senkron yolu hiç denemiyor
    -- yani en kötü hâl eski (yavaş ama çalışan) tam-metin yolu.
    """
    names: set[str] = set()

    try:
        from fool import voice_models

        for entry in voice_models.CATALOG:
            if entry.kind != "tts":
                continue
            names.add((entry.provider_id or entry.id).strip().lower())
            names.add(entry.id.strip().lower())
    except Exception:  # noqa: BLE001
        pass

    try:
        from agent.tts_registry import list_providers

        names.update(provider.name.strip().lower() for provider in list_providers())
    except Exception:  # noqa: BLE001
        pass

    return frozenset(names)


def usable_local_provider(provider: str) -> bool:
    """Bu ad senkron cümle-cümle sentez için denenmeye değer mi?

    Sınıfın adı "yerel" diyor ama kural bunu HİÇ uygulamıyordu: boş olmayan
    ve ``"none"`` olmayan HER ad kabul ediliyordu.

    Ölçülen sonuç: ``tts.provider: edge`` (desteklenen bir sağlayıcı) seçili
    olduğunda bu uç senkron yola giriyor, ``_generate_edge_tts`` uzantıya hiç
    bakmadan ``.wav`` yoluna MP3 baytları yazıyor ve ``wave.open`` "file does
    not start with RIFF id" ile düşüyor. Yani her cümle bir Microsoft gidiş
    dönüşü israf ediyor, hiç ses çıkmıyor ve istemci yedek yola ancak bu
    gecikmeden SONRA düşüyor. Aynı şekil ``minimax`` ve MP3 dönen her
    sağlayıcı için geçerli.

    ``_get_provider`` hiçbir motor kurulu/yapılandırılı değilken ``"none"``
    döner (bkz. ``tools/tts_tool.py`` FOOL-SEAM: local-only-tts).
    """
    name = (provider or "").strip().lower()

    if not name or name == "none":
        return False

    return name in _wav_capable_providers()


def _parse_tool_result(raw: Any) -> Optional[dict]:
    """``text_to_speech_tool``ün JSON dizesini (ya da zaten dict'i) çöz."""
    if isinstance(raw, dict):
        return raw

    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None

    return payload if isinstance(payload, dict) else None


#: WAV biçim etiketleri. 1 = tamsayı PCM, 3 = IEEE kayan nokta.
_WAVE_FORMAT_PCM = 1
_WAVE_FORMAT_FLOAT = 3
#: ``WAVE_FORMAT_EXTENSIBLE`` -- gerçek biçim ``SubFormat`` GUID'inin ilk
#: iki baytında duruyor.
_WAVE_FORMAT_EXTENSIBLE = 0xFFFE


def read_wav_as_int16(path: str) -> tuple[bytes, int, int]:
    """WAV'ı ham int16 PCM olarak oku: ``(bayt, ornekleme, kanal)``.

    Ölçülen hata
    ------------
    Burada ``wave.open`` kullanılıyordu ve o modül YALNIZCA tamsayı PCM
    okuyor. Chatterbox ise ``pcm_f32le`` yazıyor (biçim etiketi 3, 32 bit
    kayan nokta) -- doğrulandı, ``ffprobe`` çıktısı ``sample_fmt=flt``.

    Sonuç: cümle-cümle akış Chatterbox'ta HİÇ çalışmamış. Her cümle
    ``wave.Error: unknown format: 3`` ile düşüyor, çağıran taraf oturumu
    ``fallback`` ile kapatıyor ve istemci tek-seferlik POST yoluna geri
    düşüyor. Yani "ses ilk cümlede başlasın" -- üzerinde en çok çalışılan
    özellik -- tam da varsayılan klonlama motorunda kapalıydı ve tek belirtisi
    gecikmeydi.

    Kayan nokta int16'ya çevriliyor çünkü PROTOKOL öyle: soket ham int16
    taşıyor ve istemci onu öyle çözüyor. Kırpma bilinçli -- taşan bir örneği
    sarmalamak (wrap) gürültü yaratır.
    """
    with open(path, "rb") as handle:
        data = handle.read()

    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise RuntimeError("not a RIFF/WAVE file: " + str(path))

    fmt: tuple[int, int, int, int] | None = None
    payload = b""
    cursor = 12

    while cursor + 8 <= len(data):
        chunk_id = data[cursor:cursor + 4]
        size = struct.unpack("<I", data[cursor + 4:cursor + 8])[0]
        body = data[cursor + 8:cursor + 8 + size]

        if chunk_id == b"fmt " and len(body) >= 16:
            tag, channels, rate, _brate, _align, bits = struct.unpack("<HHIIHH", body[:16])

            if tag == _WAVE_FORMAT_EXTENSIBLE and len(body) >= 26:
                tag = struct.unpack("<H", body[24:26])[0]

            fmt = (tag, channels, rate, bits)
        elif chunk_id == b"data":
            payload = body

        # Parcalar cift sayiya hizali.
        cursor += 8 + size + (size & 1)

    if fmt is None:
        raise RuntimeError("WAV has no fmt chunk: " + str(path))

    tag, channels, rate, bits = fmt
    channels = channels or 1

    if tag == _WAVE_FORMAT_PCM and bits == 16:
        return payload, rate, channels

    if tag == _WAVE_FORMAT_FLOAT and bits in (32, 64):
        import array

        code = "f" if bits == 32 else "d"
        samples = array.array(code)
        usable = len(payload) - (len(payload) % (bits // 8))
        samples.frombytes(payload[:usable])

        out = array.array("h", [0]) * len(samples)

        for index, value in enumerate(samples):
            scaled = int(value * 32767.0)
            out[index] = 32767 if scaled > 32767 else (-32768 if scaled < -32768 else scaled)

        return out.tobytes(), rate, channels

    raise RuntimeError(
        "unsupported WAV format (tag=" + str(tag) + ", bits=" + str(bits) + ") in " + str(path)
    )


class LocalSentenceStreamer:
    """Chunked API'si olmayan bir motoru cümle başına senkron seslendirir.

    ``StreamingTTSProvider`` ile aynı yüzeyi sunuyor (``sample_rate``,
    ``channels``, ``stream(text)``) ki çağıran taraf true streamer ile bunu
    aynı döngüde kullanabilsin.
    """

    def __init__(self, provider: str) -> None:
        self.provider = provider
        #: İlk başarılı sentezden ÖĞRENİLİYOR — sabit yazmak yanlış
        #: olduğunda sessizce hız/perde bozar (bkz. modül docstring'i).
        self.sample_rate = 0
        self.channels = 0

    def stream(self, text: str) -> Iterator[bytes]:
        from tools.tts_tool import text_to_speech_tool

        handle_fd, tmp_path = tempfile.mkstemp(prefix="fool-speak-stream-", suffix=".wav")
        os.close(handle_fd)
        produced = tmp_path
        frames = b""

        # Cümlenin başındaki teslimat etiketi burada AYIKLANIYOR ve yerine
        # iki sentez ayarı geçiyor. Ayıklanmazsa Chatterbox onu sözcük olarak
        # okur -- satır içi etiket ayrıştırıcısı yok (bkz.
        # ``fool/voice_emotion.py``).
        from fool.voice_emotion import split_delivery

        spoken, delivery = split_delivery(text)

        try:
            raw = text_to_speech_tool(
                spoken,
                output_path=tmp_path,
                provider=self.provider or None,
                config_overrides=delivery.as_config() if delivery else None,
            )
            payload = _parse_tool_result(raw)

            if payload is not None:
                if not payload.get("success", True):
                    raise RuntimeError(str(payload.get("error") or "synthesis failed"))
                candidate = payload.get("file_path")
                if isinstance(candidate, str) and candidate:
                    produced = candidate

            frames, self.sample_rate, self.channels = read_wav_as_int16(produced)
        finally:
            for path in {tmp_path, produced}:
                with contextlib.suppress(OSError):
                    os.unlink(path)

        if frames:
            yield frames
