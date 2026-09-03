"""Provider-agnostic streaming TTS: sentence text → int16 PCM chunk iterator.

The keystone of Hermes' conversational voice UX. `stream_tts_to_speaker`
(``tools.tts_tool``) owns the sentence buffer, sounddevice output, and
stop/queue protocol; this module owns the *provider* half — turning one
sentence into audio the moment it's ready, so playback starts on sentence one
instead of after the whole reply.

Two provider shapes, one contract (int16 mono PCM at ``sample_rate``):

* **True streamers** (`StreamingTTSProvider.stream`) — chunked APIs
  (ElevenLabs pcm_24000, OpenAI pcm, …) that yield audio as it synthesizes.
  Lowest time-to-first-audio.
* **Everyone else** — providers with no chunked API still get per-*sentence*
  playback via the proven sync `text_to_speech_tool` path (handled by the
  dispatcher, not here), so edge (the default) is conversational too.

Adding a streamer is `@register("name")` on a `StreamingTTSProvider` subclass;
the dispatcher, config gate (`tts.<name>.streaming`), and resolver come free.
"""

from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Iterator, List, Optional

from tools.tool_backend_helpers import resolve_openai_audio_api_key
from tools.tts_tool import _get_provider, _load_tts_config, get_env_value

logger = logging.getLogger(__name__)

# Upper bound on the PCM bytes accepted from one provider stream for one
# sentence. Mirrors the 16 MiB bounded-upstream-body invariant of the sync
# providers (``_read_tts_response_bytes`` in tools.tts_tool): a buggy or
# hostile endpoint must not be able to feed us unbounded audio.
_STREAM_SENTENCE_BYTE_CAP = 16 * 1024 * 1024


def _resolve_key(env_var: str, provider_id: str) -> str:
    """Provider secret lookup: config > env/.env > credential pool.

    Thin, monkeypatchable seam over ``tools.tts_tool._resolve_provider_key``
    (which delegates to ``resolve_provider_secret``). ALL streaming-provider
    key lookups go through here — never bare ``get_env_value``.
    """
    try:
        from tools.tts_tool import _resolve_provider_key

        return _resolve_provider_key(env_var, provider_id) or ""
    except Exception:
        return get_env_value(env_var) or ""


# ---------------------------------------------------------------------------
# Interruption latch — lets the model know it was cut off mid-speech
# ---------------------------------------------------------------------------
# When the user barges in on a spoken reply (talks over it, types, hits the
# record key), the surface marks the latch; the next turn's submit path takes
# it and prepends SPEECH_INTERRUPTED_NOTE to the model-bound message (API-call
# local — never persisted, same as the CLI's model-switch notes). The TTL
# keeps a stale barge from annotating an unrelated message minutes later.

SPEECH_INTERRUPTED_NOTE = (
    "[Note: the user interrupted your previous spoken reply before it finished.]"
)
_INTERRUPT_TTL_S = 120.0
_interrupted_at: Optional[float] = None


def mark_speech_interrupted() -> None:
    global _interrupted_at
    _interrupted_at = time.monotonic()


def take_speech_interrupted() -> bool:
    """Pop the latch; True when a barge happened within the TTL."""
    global _interrupted_at
    at, _interrupted_at = _interrupted_at, None
    return at is not None and time.monotonic() - at < _INTERRUPT_TTL_S

# Sentence boundary: after .!? followed by whitespace, or a blank line.
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])(?:\s|\n)|(?:\n\n)")
_THINK_BLOCK_RE = re.compile(r"<think[\s>].*?</think>", flags=re.DOTALL)


class SentenceChunker:
    """Incremental sentence cutter for LLM token deltas.

    Shared by the speaker pipeline (`stream_tts_to_speaker`) and the
    speak-stream WebSocket so every surface cuts speech identically. Strips
    ``<think>`` blocks (even split across deltas) and merges fragments shorter
    than *min_len* into the following sentence, so "Ha!" rides along with the
    sentence after it instead of stalling as a tiny clip.
    """

    #: FOOL-SEAM: first-sentence-latency
    #:
    #: ILK parca icin alt sinir DAHA DUSUK.
    #:
    #: Olculdu: "Sure. The first thing to know is that the system loads the
    #: model once. ..." cumlesinde ilk parca 204 karakterin 77'sinde cikiyordu
    #: -- cunku "Sure." 20 karakterlik sinirin altinda ve SONRAKI cumleyle
    #: birlestiriliyor. Yani konusma, ilk cumle coktan bitmisken hala
    #: baslamamis oluyor.
    #:
    #: Birlestirme kurali kotu degil: "Ha!" tek basina bir klip olarak
    #: konusulunca sacma duruyor. Ama bu YALNIZCA ilk parcada pahali, cunku
    #: orada bekleyen sey sessizlik. Sonraki parcalarda zaten ses akiyor.
    #: Olculdu: 6 yetmiyordu -- "Sure." kirpilinca 5 karakter ve hala
    #: birlestiriliyordu. 4: "Sure." (5) geciyor, "Ha!" (3) hala sonraki
    #: cumleye biniyor.
    FIRST_MIN_LEN = 4

    #: Sinir GELMEDEN once en fazla bu kadar birikir.
    #:
    #: Nokta/soru isareti olmayan uzun bir cumle (liste, kod, uzun bir
    #: aciklama) tampona birikip HIC konusulmuyordu -- kullanicinin bildirdigi
    #: "uzun cumlelerde speak aloud duzgun calismiyor". Sinir asilinca en son
    #: virgul/noktali virgulden kesiliyor; o da yoksa son bosluktan.
    MAX_BUFFER = 240
    #: Kapanmayan bir ``<think`` blogu en fazla bu kadar birikebilir. Ustune
    #: cikarsa kapanis etiketi gelmeyecek demektir ve etiket duz metin
    #: sayiliyor -- bkz. ``feed``. Sinir MAX_BUFFER'in katlari duzeyinde:
    #: mesru bir akil yurutme blogu uzun olabilir, ama sinirsiz degil.
    THINK_MAX_BUFFER: int = 8_000

    def __init__(self, min_len: int = 20):
        self.min_len = min_len
        self.buf = ""
        #: Ilk parca cikti mi? Alt sinir ona gore secliyor.
        self.spoke = False

    def _limit(self) -> int:
        return self.min_len if self.spoke else self.FIRST_MIN_LEN

    def _clause_cut(self) -> int:
        """Sınır gelmeden kesilecek yer (``0`` = uygun yer yok).

        Virgül/noktalı virgül tercih ediliyor: cümle ortasından kesmek
        prosodiyi bozuyor ama tamamen sessiz kalmak daha kötü. Kesme noktası
        tamponun ikinci yarısında aranıyor -- baştan kesmek, elde zaten olan
        metni gereksiz parçalamak olurdu.
        """
        half = len(self.buf) // 2
        for mark in (", ", "; ", ": ", " -- ", " "):
            at = self.buf.rfind(mark, half)
            if at > 0:
                return at + len(mark)
        return 0

    def _drain(self) -> List[str]:
        """Tampondan konuşmaya hazır olan her şeyi çıkar."""
        out: List[str] = []
        start = 0  # skip boundaries that would leave the head too short
        while m := SENTENCE_BOUNDARY_RE.search(self.buf, start):
            head = self.buf[: m.end()]
            if len(head.strip()) < self._limit():
                start = m.end()
                continue
            out.append(head)
            self.spoke = True
            self.buf = self.buf[m.end():]
            start = 0

        # Sinir HIC gelmediyse: uzun bir cumle sessizce birikmesin.
        while len(self.buf) >= self.MAX_BUFFER:
            cut = self._clause_cut()
            if not cut:
                break
            out.append(self.buf[:cut])
            self.spoke = True
            self.buf = self.buf[cut:]

        return out

    def feed(self, delta: str) -> List[str]:
        """Absorb *delta*; return every complete sentence now ready to speak."""
        self.buf = _THINK_BLOCK_RE.sub("", self.buf + delta)

        open_at = self.buf.find("<think")

        if open_at == -1 or "</think>" in self.buf:
            return self._drain()

        # AÇIK bir ``<think`` bloğu. Eski kod burada ``return []`` diyordu ve
        # iki ayrı kusur üretiyordu:
        #
        #   1. Etiketten ÖNCEKİ metin de bekletiliyordu -- oysa o gerçek cevap
        #      ve hemen konuşulabilir. Modelin "Bir bakayım." deyip ardından
        #      düşünmeye başladığı her turda o cümle sessizce bekliyordu.
        #
        #   2. ``MAX_BUFFER`` muhafızı ATLANIYORDU: erken dönüş onun
        #      üstündeydi. Kapanış etiketi hiç gelmezse (kesilmiş akış, farklı
        #      bir kapanış belirteci) tampon sınırsız büyüyor ve tur BOYUNCA
        #      tam sessizlik oluyordu -- yani tam olarak o muhafızın var olma
        #      sebebi.
        head, pending = self.buf[:open_at], self.buf[open_at:]

        if len(pending) >= self.THINK_MAX_BUFFER:
            # Kapanış gelmeyecek kadar büyüdü. Etiketi DÜZ METİN sayıp normal
            # bölmeye dönüyoruz: akıl yürütmeyi sesli okumak kötü, ama cevabın
            # tamamını susturup belleği sınırsız büyütmek daha kötü.
            return self._drain()

        # Etiketten önceki metni şimdi konuş; düşünme bloğunu bekletmeye devam et.
        self.buf = head
        out = self._drain()
        self.buf += pending

        return out

    def flush(self) -> List[str]:
        """Drain the tail (end-of-text or long-idle flush)."""
        tail = _THINK_BLOCK_RE.sub("", self.buf).strip()
        self.buf = ""
        self.spoke = False
        return [tail] if tail else []


# ---------------------------------------------------------------------------
# ABC + registry
# ---------------------------------------------------------------------------

class StreamingTTSProvider(ABC):
    """Yields raw int16, little-endian, mono PCM chunks at ``sample_rate``."""

    sample_rate: int = 24000
    channels: int = 1
    sample_width: int = 2  # bytes/sample (int16)

    def __init__(self, tts_config: Dict, section: Dict):
        self.tts_config = tts_config
        self.section = section
        # SDK istemcisi OTURUM basina, cumle basina degil.
        #
        # Olculen hata: ``stream()`` her cagrisinda yeni bir istemci
        # kuruyordu -- yani HER CUMLEDE yeni bir baglanti havuzu, yeni TCP
        # el sikismasi ve yeni TLS anlasmasi. Tipik bedeli 100-300 ms ve
        # dogrudan ILK SESE kadar gecen sureye biniyor; ustelik sistemdeki
        # en dusuk gecikmeli iki saglayicida.
        #
        # Ornek ZATEN butun oturum boyunca yasiyor
        # (``resolve_streaming_provider`` bir kez cagriliyor), yani istemciyi
        # burada tutmak dogal yer. Kapatma ``close()`` ile.
        self._client: Any = None

    def close(self) -> None:
        """Oturum bitti — varsa SDK istemcisini bırak."""
        client = self._client
        self._client = None

        if client is None:
            return

        for method in ("close", "__exit__"):
            closer = getattr(client, method, None)
            if closer is None:
                continue
            try:
                closer() if method == "close" else closer(None, None, None)
            except Exception:  # noqa: BLE001 -- kapatma bir iyilestirme
                logger.debug("streaming TTS client close failed", exc_info=True)
            return

    @staticmethod
    @abstractmethod
    def available() -> bool:
        """True when this provider's credentials/SDK are usable right now."""

    @abstractmethod
    def stream(self, text: str) -> Iterator[bytes]:
        """Yield PCM chunks for ``text``. Raise on failure (caller logs)."""


_REGISTRY: Dict[str, type[StreamingTTSProvider]] = {}


def register(name: str) -> Callable[[type[StreamingTTSProvider]], type[StreamingTTSProvider]]:
    def _wrap(cls: type[StreamingTTSProvider]) -> type[StreamingTTSProvider]:
        _REGISTRY[name] = cls
        return cls

    return _wrap


def _try_instantiate(name: str, tts_config: Dict) -> Optional[StreamingTTSProvider]:
    """Construct the registered streamer *name* if it's usable, else None."""
    cls = _REGISTRY.get(name)
    if cls is None or not cls.available():
        return None
    try:
        return cls(tts_config, tts_config.get(name) or {})
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("streaming provider %s init failed: %s", name, exc)
        return None


# Fallback priority for ``tts.streaming.provider: auto`` — best chunked
# latency/quality first. Deliberately hard-coded (a UX decision, not a
# config knob); edge is absent because it has no chunked-PCM API — the
# dispatcher's per-sentence sync path keeps it conversational instead.
_PROVIDER_PRIORITY: List[str] = ["elevenlabs", "gemini", "openai", "xai"]


def resolve_streaming_provider(
    tts_config: Dict,
    preferred: Optional[str] = None,
) -> Optional[StreamingTTSProvider]:
    """Return a ready streamer for the *configured* provider, else ``None``.

    Resolution order:

    1. ``tts.streaming.provider`` (config knob) when set:
       * a provider name pins that exact streamer (or ``None`` if unusable);
       * ``auto`` walks the priority list (``elevenlabs → gemini → openai
         → xai``) and returns the first usable streamer — an explicit
         opt-in to "give me the best chunked voice available".
    2. Otherwise the *configured* TTS provider (or ``preferred`` override).
       ``None`` means "no chunked API for this provider" — the dispatcher
       then speaks per-sentence via the sync path, preserving the user's
       chosen voice. We never silently swap to a different provider just
       to get streaming.
    """
    streaming_cfg = tts_config.get("streaming") or {}
    pinned = str(streaming_cfg.get("provider") or "").lower().strip()
    if pinned == "auto":
        for name in _PROVIDER_PRIORITY:
            inst = _try_instantiate(name, tts_config)
            if inst is not None:
                return inst
        return None
    if pinned:
        return _try_instantiate(pinned, tts_config)

    name = (preferred or _get_provider(tts_config)).lower().strip()
    return _try_instantiate(name, tts_config)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

@register("elevenlabs")
class ElevenLabsStreamer(StreamingTTSProvider):
    """ElevenLabs chunked HTTP → pcm_24000 (the original reference path)."""

    sample_rate = 24000

    @staticmethod
    def available() -> bool:
        return bool(_resolve_key("ELEVENLABS_API_KEY", "elevenlabs"))

    def stream(self, text: str) -> Iterator[bytes]:
        from tools.tts_tool import (
            DEFAULT_ELEVENLABS_STREAMING_MODEL_ID,
            DEFAULT_ELEVENLABS_VOICE_ID,
            _elevenlabs_environment_kwargs,
            _import_elevenlabs,
        )

        if self._client is None:
            self._client = _import_elevenlabs()(
                api_key=_resolve_key("ELEVENLABS_API_KEY", "elevenlabs"),
                **_elevenlabs_environment_kwargs(self.section),
            )

        client = self._client
        voice_id = self.section.get("voice_id", DEFAULT_ELEVENLABS_VOICE_ID)
        model_id = self.section.get(
            "streaming_model_id",
            self.section.get("model_id", DEFAULT_ELEVENLABS_STREAMING_MODEL_ID),
        )
        # ``_capped``: cumle basina 16 MiB siniri bu modulun belgelenmis
        # degismezi ama VARSAYILAN akis saglayicisinda uygulanmiyordu --
        # OpenAI ve Gemini yollarinda vardi, burada yoktu.
        yield from _capped(
            client.text_to_speech.convert(
                text=text,
                voice_id=voice_id,
                model_id=model_id,
                output_format="pcm_24000",
            ),
            "ElevenLabs streaming TTS",
        )


def _openai_config_api_key() -> str:
    """Return ``tts.openai.api_key`` from config.yaml, or empty string."""
    try:
        openai_cfg = (_load_tts_config().get("openai") or {})
    except Exception:
        return ""
    return openai_cfg.get("api_key") or ""


@register("openai")
class OpenAIStreamer(StreamingTTSProvider):
    """OpenAI speech with ``response_format=pcm`` (24 kHz mono int16)."""

    sample_rate = 24000

    @staticmethod
    def available() -> bool:
        return bool(_openai_config_api_key() or resolve_openai_audio_api_key())

    def stream(self, text: str) -> Iterator[bytes]:
        from openai import OpenAI

        if self._client is None:
            self._client = OpenAI(
                api_key=(self.section.get("api_key") or resolve_openai_audio_api_key()),
                base_url=(
                    self.section.get("base_url")
                    or get_env_value("OPENAI_BASE_URL")
                    or None
                ),
            )

        client = self._client
        model = self.section.get("model", "gpt-4o-mini-tts")
        voice = self.section.get("voice", "alloy")
        with client.audio.speech.with_streaming_response.create(
            model=model,
            voice=voice,
            input=text,
            response_format="pcm",
        ) as response:
            yield from _capped(response.iter_bytes(), "OpenAI streaming TTS")


def _capped(chunks: Iterator[bytes], label: str) -> Iterator[bytes]:
    """Pass chunks through, aborting past the 16 MiB per-sentence cap.

    The streaming mirror of ``_read_tts_response_bytes``'s bounded-body
    invariant: one sentence of PCM should never approach the cap, so
    exceeding it means a runaway/hostile upstream — stop pulling.
    """
    total = 0
    for chunk in chunks:
        total += len(chunk)
        if total > _STREAM_SENTENCE_BYTE_CAP:
            logger.warning("%s exceeded %d bytes for one sentence; truncating",
                           label, _STREAM_SENTENCE_BYTE_CAP)
            return
        yield chunk


@register("gemini")
class GeminiStreamer(StreamingTTSProvider):
    """Gemini ``streamGenerateContent?alt=sse`` → base64 PCM chunks (24 kHz).

    Salvaged from PR #47588 (@Cdddo) and rebased onto the post-campaign
    infrastructure: credentials via the provider-secret resolver, requests
    (not httpx) with a bounded streamed body, and main's provider ABC.
    """

    sample_rate = 24000

    @staticmethod
    def available() -> bool:
        return bool(
            _resolve_key("GEMINI_API_KEY", "gemini")
            or _resolve_key("GOOGLE_API_KEY", "gemini")
        )

    def stream(self, text: str) -> Iterator[bytes]:
        import base64
        import json as _json

        import requests

        from tools.tts_tool import (
            DEFAULT_GEMINI_TTS_BASE_URL,
            DEFAULT_GEMINI_TTS_MODEL,
            DEFAULT_GEMINI_TTS_VOICE,
        )

        api_key = (
            _resolve_key("GEMINI_API_KEY", "gemini")
            or _resolve_key("GOOGLE_API_KEY", "gemini")
        )
        model = str(self.section.get("model", DEFAULT_GEMINI_TTS_MODEL)).strip() or DEFAULT_GEMINI_TTS_MODEL
        voice = str(self.section.get("voice", DEFAULT_GEMINI_TTS_VOICE)).strip() or DEFAULT_GEMINI_TTS_VOICE
        base_url = str(
            self.section.get("base_url")
            or get_env_value("GEMINI_BASE_URL")
            or DEFAULT_GEMINI_TTS_BASE_URL
        ).strip().rstrip("/")

        payload = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": voice},
                    },
                },
            },
        }
        # ``?alt=sse`` flips the response from a single JSON blob to an SSE
        # feed of base64 PCM chunks — the whole point of this provider.
        url = f"{base_url}/models/{model}:streamGenerateContent"

        def _sse_chunks() -> Iterator[bytes]:
            with requests.post(
                url,
                params={"alt": "sse", "key": api_key},
                json=payload,
                timeout=60,
                stream=True,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data: "):
                        continue
                    try:
                        event = _json.loads(line[len("data: "):])
                        parts = event["candidates"][0]["content"]["parts"]
                    except (ValueError, KeyError, IndexError, TypeError):
                        continue
                    for part in parts:
                        inline = part.get("inlineData") or part.get("inline_data") or {}
                        b64 = inline.get("data", "")
                        if not b64:
                            continue
                        try:
                            yield base64.b64decode(b64)
                        except (ValueError, TypeError) as exc:
                            logger.warning("Gemini SSE: bad base64 audio: %s", exc)

        yield from _capped(_sse_chunks(), "Gemini streaming TTS")


@register("xai")
class XAIStreamer(StreamingTTSProvider):
    """xAI WebSocket TTS → binary PCM frames (24 kHz mono int16).

    Salvaged from PR #47588 (@Cdddo): xAI's chunked TTS API is
    WebSocket-only (``wss://api.x.ai/v1/tts``). Credentials route through
    ``resolve_xai_http_credentials`` (OAuth or XAI_API_KEY), same as the
    sync ``_generate_xai_tts`` path. The async WS loop is bridged to the
    sync iterator contract via ``_collect_async`` — the seam unit tests
    monkeypatch.
    """

    sample_rate = 24000

    @staticmethod
    def available() -> bool:
        try:
            from tools.xai_http import resolve_xai_http_credentials

            creds = resolve_xai_http_credentials()
            return bool(str(creds.get("api_key") or "").strip())
        except Exception:
            return False

    def stream(self, text: str) -> Iterator[bytes]:
        yield from _capped(iter(self._collect_async(text)), "xAI streaming TTS")

    # -- async→sync bridge (test seam) ------------------------------------

    def _collect_async(self, text: str) -> List[bytes]:
        import asyncio

        return asyncio.run(self._drain_async(text))

    async def _drain_async(self, text: str) -> List[bytes]:
        frames: List[bytes] = []
        async for frame in self._async_frames(text):
            frames.append(frame)
        return frames

    async def _async_frames(self, text: str):
        import json as _json

        import websockets

        from tools.tts_tool import DEFAULT_XAI_VOICE_ID
        from tools.xai_http import resolve_xai_http_credentials

        creds = resolve_xai_http_credentials()
        api_key = str(creds.get("api_key") or "").strip()
        if not api_key:
            raise RuntimeError("No xAI credentials for streaming TTS")
        voice = str(self.section.get("voice_id", DEFAULT_XAI_VOICE_ID)).strip() or DEFAULT_XAI_VOICE_ID
        ws_url = str(
            self.section.get("streaming_url") or "wss://api.x.ai/v1/tts"
        ).strip()

        async with websockets.connect(
            ws_url, extra_headers={"Authorization": f"Bearer {api_key}"}
        ) as ws:
            await ws.send(_json.dumps({
                "text": text,
                "voice_id": voice,
                "response_format": "pcm",
            }))
            try:
                while True:
                    message = await ws.recv()
                    if isinstance(message, (bytes, bytearray, memoryview)):
                        yield bytes(message)
                        continue
                    try:
                        envelope = _json.loads(message)
                    except (ValueError, TypeError):
                        if message == "done":
                            return
                        continue
                    etype = envelope.get("type")
                    if etype == "done":
                        return
                    if etype == "error":
                        logger.warning("xAI WS error envelope: %s",
                                       envelope.get("error") or envelope.get("message") or envelope)
                        return
            except Exception as exc:
                if exc.__class__.__name__ == "ConnectionClosed":
                    return
                logger.warning("xAI WS receive failed: %s", exc)
                return
