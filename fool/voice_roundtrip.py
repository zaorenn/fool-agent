"""Gerçek yerel ses turu: STT -> LLM -> TTS, uçtan uca, ölçülerek.

Neden var
---------
Birim testleri her parçayı ayrı ayrı doğruluyor ama bu oturumda ölçülen
hataların çoğu tam olarak PARÇALARIN ARASINDA duruyordu:

  * ``cuda_ready`` motora değil sürücüye soruyordu,
  * ``_synthesize`` bir yol bekliyordu, araç JSON döndürüyordu,
  * ölçüm sonuçları katalog kimliğiyle saklanıyordu, yapılandırma sağlayıcı
    adı yazıyordu.

Üçü de tek tek bakınca doğru görünen, birleşince kopan yerlerdi. Bu tur o
boşluğu kapatıyor: kullanıcının gerçekten yaptığı şeyi baştan sona yapıyor ve
her aşamayı ayrı ölçüyor.

Akış
----
1. Kullanıcının söyleyeceği cümle TTS ile SESE çevriliyor (mikrofonun yerine
   geçiyor -- bu bir simülasyon değil, gerçek ses dosyası).
2. O ses yerel STT ile yazıya dökülüyor.
3. Yazı yerel modele gönderiliyor.
4. Modelin cevabı TTS ile seslendiriliyor.

Ağa hiç çıkılmıyor; hepsi makinede. Tur ``python -m fool.voice_roundtrip``
ile çalışıyor ve her aşamanın süresini yazıyor.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
import wave
from typing import Any

#: Kullanıcının söylediği varsayılan cümle. Kısa, doğal ve modelin
#: cevaplayabileceği bir şey -- amaç modeli sınamak değil, BORUYU sınamak.
DEFAULT_UTTERANCE = "What is the capital of France? Answer in one short sentence."


def _synth(text: str, provider: str) -> str:
    """Metni sese çevir; üretilen dosyanın yolunu döndür."""
    from tools.tts_tool import text_to_speech_tool

    handle, path = tempfile.mkstemp(prefix="fool-rt-", suffix=".wav")
    os.close(handle)

    raw = text_to_speech_tool(text, output_path=path, provider=provider)
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return str(raw)

    if isinstance(payload, dict):
        if not payload.get("success", True):
            raise RuntimeError(str(payload.get("error") or "synthesis failed"))
        produced = payload.get("file_path")
        if isinstance(produced, str) and produced:
            return produced
    return path


def _audio_seconds(path: str) -> float:
    """Ses uzunluğu.

    ``wave`` yalnızca PCM okuyor; float32 WAV'da ``unknown format: 3`` ile
    düşüyor ve süre sessizce ``0.00s`` görünüyordu -- ölçüm aracının kendisi
    yanlış rapor veriyordu. ``soundfile`` varsa o kullanılıyor.
    """
    try:
        import soundfile as sf

        info = sf.info(path)
        return float(info.frames) / float(info.samplerate or 1)
    except Exception:
        pass

    try:
        with contextlib.closing(wave.open(path, "rb")) as handle:
            return handle.getnframes() / float(handle.getframerate() or 1)
    except Exception:
        return 0.0


def _transcribe(path: str) -> str:
    from tools.transcription_tools import transcribe_audio

    result = transcribe_audio(path)
    if isinstance(result, dict):
        if not result.get("success", True):
            raise RuntimeError(str(result.get("error") or "transcription failed"))
        return str(result.get("transcript") or "").strip()
    return str(result).strip()


def _ask_model(text: str) -> str:
    from fool_cli.config import load_config
    from openai import OpenAI

    config = load_config() or {}
    model_cfg = config.get("model") or {}
    model = str(model_cfg.get("default") or model_cfg.get("model") or "").strip()
    base_url = str(model_cfg.get("base_url") or "http://localhost:1234/v1").strip()

    if not model:
        raise RuntimeError("model yapilandirilmamis: `fool model` ile sec")

    client = OpenAI(base_url=base_url, api_key="local")
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": text}],
        temperature=0,
    )
    return (response.choices[0].message.content or "").strip()


def run(utterance: str = DEFAULT_UTTERANCE, provider: str | None = None) -> dict[str, Any]:
    """Turu koş ve her aşamayı ölç.

    Hata YUTULMUYOR: bir aşama düşerse tur düşer. Bu bir kapı; "kısmen
    çalıştı" diye bir sonucu yok.
    """
    if provider is None:
        from fool_cli.config import load_config
        from tools.tts_tool import _get_provider

        provider = _get_provider((load_config() or {}).get("tts") or {})

    stages: list[dict[str, Any]] = []
    artifacts: list[str] = []

    try:
        # 1. Kullanicinin sesi (mikrofonun yerine gecen gercek ses dosyasi).
        started = time.monotonic()
        user_audio = _synth(utterance, provider)
        artifacts.append(user_audio)
        stages.append({
            "stage": "user speech (TTS)",
            "seconds": round(time.monotonic() - started, 2),
            "detail": f"{_audio_seconds(user_audio):.2f}s of audio",
        })

        # 2. Yerel STT.
        started = time.monotonic()
        heard = _transcribe(user_audio)
        stages.append({
            "stage": "STT (local)",
            "seconds": round(time.monotonic() - started, 2),
            "detail": heard[:60],
        })
        if not heard:
            raise RuntimeError("STT bos metin dondu")

        # 3. Yerel model.
        started = time.monotonic()
        reply = _ask_model(heard)
        stages.append({
            "stage": "LLM (local)",
            "seconds": round(time.monotonic() - started, 2),
            "detail": reply[:60],
        })
        if not reply:
            raise RuntimeError("model bos cevap dondu")

        # 4. Cevabin seslendirilmesi.
        started = time.monotonic()
        reply_audio = _synth(reply, provider)
        artifacts.append(reply_audio)
        stages.append({
            "stage": "reply speech (TTS)",
            "seconds": round(time.monotonic() - started, 2),
            "detail": f"{_audio_seconds(reply_audio):.2f}s of audio",
        })

        return {
            "ok": True,
            "provider": provider,
            "utterance": utterance,
            "heard": heard,
            "reply": reply,
            "stages": stages,
            "total_seconds": round(sum(s["seconds"] for s in stages), 2),
        }
    finally:
        for path in artifacts:
            with contextlib.suppress(OSError):
                os.unlink(path)


def _main() -> int:  # pragma: no cover - elle calistirilan kapi
    try:
        result = run()
    except Exception as exc:
        print(f"TUR DUSTU: {exc}")
        return 1

    print(f"saglayici : {result['provider']}")
    print(f"soylenen  : {result['utterance']}")
    print(f"duyulan   : {result['heard']}")
    print(f"cevap     : {result['reply']}")
    print()
    for stage in result["stages"]:
        print(f"  {stage['stage']:22} {stage['seconds']:6.2f}s   {stage['detail']}")
    print(f"  {'TOPLAM':22} {result['total_seconds']:6.2f}s")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
