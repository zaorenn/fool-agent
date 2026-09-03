"""İki sesli kip: arkadaş ve Jarvis.

Neden iki kip
-------------
Aynı sesli yüzeyden iki farklı şey isteniyor ve ikisinin gereksinimleri
çelişiyor:

* **Arkadaş** -- çoğu tur bir görev değil, biri konuşuyor. Kısa, sıcak,
  araçsız. Yanlış anlaşılma sık ve normal; bedeli boşa giden bir tur olmalı.
* **Jarvis** -- gerçekten iş yapıyor: terminal, dosya, kod. Kısa ve kesin
  konuşuyor, ne yaptığını söylüyor. Burada yanlış anlaşılmanın bedeli GERÇEK
  bir eylem.

Tek kipte birleştirmek ikisini de bozuyordu: araçlı bir persona sohbette
gereksiz resmî, sohbet personası iş yaparken belirsiz oluyor.

Kip bir OTURUM özelliği
-----------------------
Araç kümesi ajan kurulurken donuyor ve prompt önbelleği donmuş sistem promptu
+ araç şemaları üzerine kurulu. Kip değiştirmek yeni bir oturum açmak demek,
tur içinde araç değiştirmek değil (bkz. ``fool/session_scope.py``).

Jarvis'in yetkisi ÖLÇÜME bağlı
------------------------------
Sesle "şunu sil" demek ile modelin ``terminal_run`` çağrısını doğru üretmesi
ayrı şeyler. Jarvis makineye dokunduğu için tool-calling sınavı onun
varsayılanı (bkz. ``fool/model_readiness.py``); arkadaş kipinde gereksiz,
çünkü orada zaten dokunacak bir şey yok.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

COMPANION: Final[str] = "companion"
JARVIS: Final[str] = "jarvis"

#: Masaustundeki Friend penceresi. AYRI bir kip cunku arac kumesi farkli
#: (hafiza paylasiliyor, terminal yok) -- AYRI bir ses degil: seslendirme
#: motoru her yuzeyde tek, ``tts.provider``.
FRIEND: Final[str] = "friend"

DEFAULT_MODE: Final[str] = COMPANION


JARVIS_GUIDANCE: Final[str] = """WORKING OUT LOUD
You are being spoken to, and you can act on the machine. Both facts change
how you answer.

Speaking:
- Lead with the answer or the result. No preamble, no restating the request.
- Keep it to what someone can hold in their head hearing it once. If the
  answer needs a list, say the count first, then the items.
- Say what you DID, in past tense, not what you are about to do. "Renamed
  four files" beats "I'll rename the files now".
- Read paths and commands back in plain speech, not as literal punctuation.

Acting:
- Before anything destructive or hard to undo -- deleting, overwriting,
  force-pushing, killing processes, sending anything outward -- say what you
  are about to do in one sentence and WAIT for a yes. You were asked by
  voice; voice is easy to mishear.
- One misheard word can become a real action. If the request is ambiguous in
  a way that changes what gets touched, ask instead of guessing.
- After a tool fails, say so plainly and stop. Do not retry variations
  silently; the user cannot see your attempts.

You are not a chat window. The user is probably looking at something else."""


@dataclass(frozen=True)
class VoiceMode:
    """Tek bir sesli kip."""

    id: str
    #: Kullanıcıya görünen ad (İngilizce -- uygulamanın varsayılan dili).
    label: str
    #: Panelde tek cümlelik açıklama.
    summary: str
    #: ``None`` = kısıtlama yok, normal platform çözümlemesi geçerli.
    toolsets: tuple[str, ...] | None
    #: Sistem promptuna eklenen persona.
    guidance: str
    #: Makineye dokunan araçları var mı? Varsa tool-calling sınavı şart.
    touches_machine: bool


def _companion_toolsets() -> tuple[str, ...]:
    from fool.session_scope import COMPANION_TOOLSETS

    return tuple(COMPANION_TOOLSETS)


def _friend_toolsets() -> tuple[str, ...]:
    from fool.session_scope import FRIEND_TOOLSETS

    return tuple(FRIEND_TOOLSETS)


def _companion_guidance() -> str:
    from fool.guidance import COMPANION_GUIDANCE

    return COMPANION_GUIDANCE


def modes() -> dict[str, VoiceMode]:
    """Tanımlı kipler.

    Geç kurulum: ``guidance`` ve ``session_scope`` yapılandırma katmanına
    dokunuyor ve bu modülü içe aktarmanın maliyeti olmamalı.
    """
    return {
        COMPANION: VoiceMode(
            id=COMPANION,
            label="Friend",
            summary="Just talk. No tools, nothing to break -- it cannot touch the machine.",
            toolsets=_companion_toolsets(),
            guidance=_companion_guidance(),
            touches_machine=False,
        ),
        FRIEND: VoiceMode(
            id=FRIEND,
            label="Friend window",
            summary="The full-page chat. No tools, but memory is shared with the agent.",
            toolsets=_friend_toolsets(),
            guidance=_companion_guidance(),
            touches_machine=False,
        ),
        JARVIS: VoiceMode(
            id=JARVIS,
            label="Jarvis",
            summary="Gets things done: terminal, files, code, browser. Confirms before anything destructive.",
            # ``None`` = normal cozumleme: Jarvis sahibinin tam yuzeyini alir.
            toolsets=None,
            guidance=JARVIS_GUIDANCE,
            touches_machine=True,
        ),
    }


def get(mode_id: Any) -> VoiceMode:
    """Kipi getir; tanınmayan her şey arkadaş kipine düşer.

    Kapalı taraf güvenli taraf: bir yazım hatası yüzünden sesli yüzeyin
    terminale açılması kabul edilemez.
    """
    key = str(mode_id or "").strip().lower()
    return modes().get(key, modes()[DEFAULT_MODE])


def active_mode(config: Any) -> str:
    """``voice.mode`` -- varsayılan arkadaş."""
    if not isinstance(config, dict):
        return DEFAULT_MODE
    voice = config.get("voice")
    if not isinstance(voice, dict):
        return DEFAULT_MODE
    key = str(voice.get("mode") or "").strip().lower()
    return key if key in modes() else DEFAULT_MODE


def requires_benchmark(mode_id: Any) -> bool:
    """Bu kip tool-calling sınavını şart koşuyor mu?

    Jarvis makineye dokunuyor: sesle "şunu sil" demek ile modelin
    ``terminal_run`` çağrısını DOĞRU üretmesi ayrı şeyler.
    """
    return get(mode_id).touches_machine
