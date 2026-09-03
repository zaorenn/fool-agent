"""Zamanın farkında olmak: günün saati, aradan geçen süre, veda edilip edilmediği.

Neden ayrı ve saf
-----------------
Bir modelin saat bilmesi, sistem promptuna bir zaman damgası koymakla olmuyor.
"Şu an 09:14" satırı, modelin "günaydın" demesi gerektiğini SÖYLEMİYOR --
ondan çıkarım yapmasını bekliyor, ve o çıkarım her turda yeniden, tutarsız
biçimde yapılıyor.

Burada karar KODDA veriliyor ve modele hazır bir cümle gidiyor: "sabah",
"dört gündür konuşulmadı", "geçen sefer veda etmeden gitti". Model o cümleyle
ne yapacağına kendi karar veriyor -- ki asıl yargı gerektiren kısım o.

Neden veda AYRI bir işaret
--------------------------
İstenen davranış şuydu: kullanıcı gece konuşup veda etmeden kapatırsa, ertesi
sabah bunun HATIRLANMASI. Bunu aradan geçen süreden çıkarmak mümkün değil --
sekiz saatlik boşluk, "iyi geceler deyip yattı" ile "ortadan kayboldu"
arasında hiçbir fark görmüyor. Fark, vedanın kaydedilmiş olup olmamasında.

O yüzden iki ayrı damga tutuluyor: en son NE ZAMAN görüldüğü, ve en son ne
zaman VEDALAŞILDIĞI. Veda damgası görülme damgasının gerisindeyse, aradaki
oturum vedasız bitmiş demektir.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

#: Bu süreden kısa aralar "ara" sayılmıyor -- aynı sohbetin devamı.
CONTINUATION_SECONDS = 20 * 60

#: Vedasız ayrılığın "fark edilir" sayılması için gereken en kısa ara.
#:
#: Kısa bir kesinti (uygulama yeniden başladı, pencere kapandı) veda
#: gerektirmiyor. Bir gecelik sessizlik gerektiriyor.
UNFINISHED_GAP_SECONDS = 3 * 3600


@dataclass(frozen=True)
class TimeContext:
    """Modele giden zaman bilgisi."""

    #: "late night" | "early morning" | "morning" | "afternoon" | "evening" | "night"
    part_of_day: str
    #: Yerel saat, ``HH:MM``.
    clock: str
    #: Haftanın günü.
    weekday: str
    #: Son konuşmadan bu yana geçen süre, insan ölçeğinde. İlk kez ise boş.
    since_last: str
    #: Bu, kullanıcıyla ilk konuşma mı?
    first_ever: bool
    #: Önceki oturum VEDA EDİLMEDEN bitti mi?
    left_without_goodbye: bool

    def render(self) -> str:
        """Sistem promptuna giren blok. Boş dize = söylenecek bir şey yok."""
        lines = [
            "It is " + self.clock + " on " + self.weekday + " (" + self.part_of_day + ").",
        ]

        if self.first_ever:
            lines.append("You have never spoken with this person before.")
        elif self.since_last:
            lines.append("You last spoke " + self.since_last + ".")

        if self.left_without_goodbye:
            lines.append("They left last time without saying goodbye.")

        return "\n".join(lines)


def part_of_day(when: datetime) -> str:
    hour = when.hour

    if hour < 5:
        return "late night"

    if hour < 8:
        return "early morning"

    if hour < 12:
        return "morning"

    if hour < 18:
        return "afternoon"

    if hour < 22:
        return "evening"

    return "night"


def describe_gap(seconds: float) -> str:
    """Aradan geçen süre, insanın söyleyeceği gibi."""
    if seconds < CONTINUATION_SECONDS:
        return "a few minutes ago"

    if seconds < 3600:
        return str(int(seconds // 60)) + " minutes ago"

    hours = seconds / 3600

    if hours < 24:
        count = int(hours)

        return "an hour ago" if count <= 1 else str(count) + " hours ago"

    days = hours / 24

    if days < 2:
        return "yesterday"

    if days < 7:
        return str(int(days)) + " days ago"

    if days < 30:
        weeks = int(days // 7)

        return "a week ago" if weeks <= 1 else str(weeks) + " weeks ago"

    months = int(days // 30)

    return "a month ago" if months <= 1 else str(months) + " months ago"


def build(
    *,
    now: float,
    last_seen: float | None,
    last_farewell: float | None,
    localize=None,
) -> TimeContext:
    """Zaman bağlamını kur.

    ``localize`` sınav içindir: saat dilimi sabitlenmeden "sabah mı" sorusu
    makineye göre değişen bir cevap alır ve sınav gerçekte neyi ölçtüğünü
    kaybeder.
    """
    stamp = (localize or datetime.fromtimestamp)(now)
    first_ever = last_seen is None
    gap = 0.0 if first_ever else max(0.0, now - float(last_seen))

    # Veda damgası görülme damgasının GERİSİNDEYSE, aradaki oturum vedasız
    # bitmiş demektir. Aradan geçen süreden bunu çıkarmak mümkün olmazdı:
    # sekiz saatlik boşluk "iyi geceler deyip yattı" ile "ortadan kayboldu"
    # arasında hiçbir fark görmüyor.
    unfinished = False

    if not first_ever and gap >= UNFINISHED_GAP_SECONDS:
        unfinished = last_farewell is None or float(last_farewell) < float(last_seen)

    return TimeContext(
        part_of_day=part_of_day(stamp),
        clock=stamp.strftime("%H:%M"),
        weekday=stamp.strftime("%A"),
        since_last="" if first_ever else describe_gap(gap),
        first_ever=first_ever,
        left_without_goodbye=unfinished,
    )
