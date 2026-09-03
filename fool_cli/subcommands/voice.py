"""``fool voice`` subcommand parser.

Neden bir komut gerekiyordu
---------------------------
Ajanın sesi değiştirebilmesinin başka yolu yoktu. Kullanıcı konuşurken "erkek
sesine geç" diyor ve ajanın elinde yalnızca ham ``fool config set`` vardı --
motor adını, ayar anahtarını ve ses kimliğini birlikte doğru bilmesi
gerekiyordu (``tts.kokoro.voice`` = ``am_michael``). Ölçüldü: bunları
uydurmaya çalışıyor ve tur boşa gidiyor.

Ayrıca ``fool voice`` daha önce ajanın UYDURDUĞU komutlardan biriydi
(bkz. ``fool/guidance.py`` içindeki CLI notu) -- artık gerçek.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

from typing import Callable


def build_voice_parser(subparsers, *, cmd_voice: Callable) -> None:
    """``voice`` altkomutunu ``subparsers``a bağla."""
    voice_parser = subparsers.add_parser(
        "voice",
        help="Show and change the speaking voice",
        description=(
            "Inspect and change the text-to-speech engine and its voice. "
            "Takes effect on the next sentence spoken -- no restart."
        ),
    )
    voice_sub = voice_parser.add_subparsers(dest="voice_command")

    voice_sub.add_parser("list", help="Show the engine in use and every voice it offers")

    voice_set = voice_sub.add_parser(
        "set", help="Switch to another voice of the current engine (e.g. `voice set am_michael`)"
    )
    voice_set.add_argument("voice", help="Voice id, as printed by `fool voice list`")

    voice_engine = voice_sub.add_parser("engine", help="Switch the speaking engine")
    voice_engine.add_argument("engine", help="Engine id, as printed by `fool voice list`")

    voice_parser.set_defaults(func=cmd_voice)
