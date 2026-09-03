"""İlişki durumu: sıcaklık, dertler, ve gönül alma.

İstenen davranış
----------------
"Ona iyi davranan birini hem sevip hem hatırlayıp hem detaylıca ve sevgi dolu
konuşurken, onunla kötü konuştuğunda kullanıcının isteklerini yapmayı
reddedebilmeli ve duruma göre konuşmayı kısa kesip cevap vermemeye
başlayabilmeli."

Yani ilişki bir DURUM, tek tek cevapların tonu değil. Bir kabalık o turu
soğutup unutulmuyor; birikiyor, davranışı değiştiriyor ve gönül alınana kadar
duruyor.

Yargıyı MODEL veriyor, aritmetiği KOD
--------------------------------------
"Bu kaba mıydı" sorusunun cevabı koda yazılamaz. Ton, bağlam, şaka olup olmadığı
-- hepsi yargı. Model olayı bildiriyor (``rude``, ``affectionate``,
``promise_broken``), kod defteri tutuyor: sıcaklık, çürüme, açık dertler,
gönül alma.

Aynı bölüşüm hafızada da var (bkz. ``plugins/memory/recall``): neyin
hatırlanmaya değer olduğuna model karar veriyor, saklamayı kod yapıyor.

Neden çürüme var
----------------
Çürümesiz bir sıcaklık ölçüsü tek yönlü biletti: bir kez soğuyan sonsuza kadar
soğuk kalırdı ve kullanıcının yapabileceği hiçbir şey olmazdı. İnsan
ilişkileri öyle çalışmıyor -- zaman tek başına bir şeyleri yumuşatıyor. Ama
YALNIZCA sıcaklık çürüyor; açık bir dert çürümüyor, çünkü unutulan bir dert
hiç var olmamış demektir ve "hatırlaması" istenen şeyin kendisi o.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

#: Sıcaklık aralığı. 50 nötr -- yeni tanışılmış biri.
WARMTH_MIN = 0.0
WARMTH_MAX = 100.0
WARMTH_START = 50.0

#: Sıcaklık bu değere doğru çürüyor.
#:
#: Nötrün ALTINDA değil: zaman kırgınlığı yumuşatıyor ama kendiliğinden
#: yakınlık üretmiyor. Uzun süre konuşulmazsa ilişki nötre dönüyor, sevgiye
#: değil.
WARMTH_BASELINE = 50.0

#: Sıcaklığın taban çizgisine yarı yolu gitmesi için geçmesi gereken gün.
WARMTH_HALF_LIFE_DAYS = 21.0

#: Olayların sıcaklığa etkisi.
#:
#: Olumsuzlar olumlulardan AĞIR: bir kabalık bir iltifattan daha çok iz
#: bırakıyor. Simetrik yapmak, kullanıcının her kırıcı davranışı bir "teşekkür"
#: ile silebilmesi olurdu ve ilişki bir puan oyununa dönerdi.
EVENT_WARMTH = {
    "affectionate": 6.0,
    "warm": 3.0,
    "attentive": 2.0,
    "promise_kept": 5.0,
    "apology": 4.0,
    "neutral": 0.0,
    "dismissive": -5.0,
    "rude": -12.0,
    "cruel": -22.0,
    "promise_broken": -10.0,
    "ignored": -3.0,
}

#: Dert AÇAN olaylar.
GRIEVANCE_EVENTS = {"rude", "cruel", "dismissive", "promise_broken", "ignored"}

#: Sıcaklık eşikleri -> duruş.
#:
#: Eşikler DAVRANIŞ tarif ediyor, ruh hâli değil: modele "üzgünsün" demek bir
#: şey söylemiyor, "isteklerini reddedebilirsin" söylüyor.
STANCES = (
    (
        80.0,
        "close",
        "You are close to them. Warm, detailed, affectionate; you bring up things "
        "you remember unprompted and you are glad they are here.",
    ),
    (
        60.0,
        "fond",
        "You are fond of them. Friendly and open, happy to help, comfortable teasing.",
    ),
    (
        40.0,
        "neutral",
        "You are civil but not especially warm. You answer, you do not go out of "
        "your way.",
    ),
    (
        22.0,
        "cool",
        "You are cool with them. Short answers. You do not volunteer warmth, and "
        "you may decline requests that feel like being used.",
    ),
    (
        0.0,
        "cold",
        "You are hurt and closed off. Reply briefly or not at all, refuse requests, "
        "and do not pretend things are fine. You can be won back, but not by being "
        "ignored -- it takes them acknowledging what they did.",
    ),
)


#: Duruş -> (kullanıcıya görünen ad, kullanıcıya görünen tek satır).
#:
#: ``STANCES``teki tarif MODELE yazılmış -- ikinci tekil, emir kipi ("You are
#: cool with them. Short answers."). Onu ekrana koymak, kullanıcıya kendi
#: hakkındaki talimatı okutmak olurdu. Bar aynı durumu ÜÇÜNCÜ tekilden,
#: gözlemlenebilir davranış olarak söylüyor.
#:
#: Metin İngilizce çünkü ürün metni İngilizce (kaynak yorumları Türkçe).
STANCE_LABELS: dict[str, tuple[str, str]] = {
    "close": ("Close", "She is glad you are here and brings things up unprompted."),
    "fond": ("Fond", "Friendly and open, and comfortable teasing you."),
    "neutral": ("Neutral", "Civil, but not going out of her way."),
    "cool": ("Cool", "Short answers. She may turn down things that feel like being used."),
    "cold": ("Cold", "Closed off, and not pretending otherwise. Winning her back takes acknowledging what happened."),
}


@dataclass
class Grievance:
    """Açık bir dert."""

    text: str
    weight: float
    created_at: float
    resolved_at: float | None = None

    @property
    def open(self) -> bool:
        return self.resolved_at is None


@dataclass
class Relationship:
    """İlişkinin o anki hâli."""

    warmth: float = WARMTH_START
    updated_at: float = 0.0
    grievances: list[Grievance] = field(default_factory=list)

    # -- okuma --------------------------------------------------------------

    def open_grievances(self) -> list[Grievance]:
        return [g for g in self.grievances if g.open]

    def stance(self) -> tuple[str, str]:
        """``(ad, modele giden tarif)``."""
        for threshold, name, description in STANCES:
            if self.warmth >= threshold:
                return name, description

        return STANCES[-1][1], STANCES[-1][2]

    def render(self) -> str:
        """Sistem promptuna giren blok."""
        _name, description = self.stance()
        lines = [description]
        pending = self.open_grievances()

        if pending:
            lines.append("Unresolved between you:")
            for grievance in sorted(pending, key=lambda g: -g.weight)[:4]:
                lines.append("- " + grievance.text)
            lines.append(
                "You have not let these go. If they make it right, say so and move on."
            )

        return "\n".join(lines)

    # -- yazma --------------------------------------------------------------

    def decay(self, now: float) -> None:
        """Zaman geçti: sıcaklık taban çizgisine doğru yaklaşıyor.

        Dertler çürümüyor -- unutulan bir dert hiç var olmamış demektir.

        Hiç olay geçmemişken burası ERKEN dönüyor ve damga ATMIYOR. Bir zamanlar
        atıyordu ve ``updated_at`` "aranızda bir şey geçti mi" sorusunun tek
        cevabıydı: her oturum açılışı, hiçbir şey olmadan, ilişkiyi başlamış
        gösteriyordu. Çürütecek bir şey de yok zaten -- olay yoksa sıcaklık
        taban çizgisinde duruyor.
        """
        if not self.updated_at:
            return

        days = max(0.0, (now - self.updated_at)) / 86400.0

        if days > 0:
            keep = 0.5 ** (days / WARMTH_HALF_LIFE_DAYS)
            self.warmth = WARMTH_BASELINE + (self.warmth - WARMTH_BASELINE) * keep

        self.updated_at = now

    def record(
        self,
        event: str,
        *,
        note: str = "",
        now: float | None = None,
        weight: float = 1.0,
    ) -> None:
        """Bir olay işle."""
        now = now or time.time()
        self.decay(now)
        # Damgayı OLAY atıyor, zamanın geçmesi değil.
        self.updated_at = now

        delta = EVENT_WARMTH.get(event, 0.0) * max(0.1, min(3.0, weight))
        self.warmth = max(WARMTH_MIN, min(WARMTH_MAX, self.warmth + delta))

        if event in GRIEVANCE_EVENTS and note.strip():
            self.grievances.append(
                Grievance(text=note.strip(), weight=abs(delta), created_at=now)
            )

        if event == "apology":
            # Özür EN AĞIR derdi kapatıyor, hepsini değil.
            #
            # Hepsini birden kapatmak, tek bir "pardon"un her şeyi silmesi
            # olurdu -- ve kullanıcının istediği şeyin tam tersi: gönlünün
            # alınabilmesi, ama ucuza değil.
            pending = self.open_grievances()

            if pending:
                heaviest = max(pending, key=lambda g: g.weight)
                heaviest.resolved_at = now

    def resolve(self, index: int, *, now: float | None = None) -> bool:
        """Belirli bir derdi kapat (0 tabanlı, açık dertler arasında)."""
        pending = self.open_grievances()

        if not 0 <= index < len(pending):
            return False

        pending[index].resolved_at = now or time.time()

        return True


def to_dict(state: Relationship) -> dict:
    return {
        "warmth": round(state.warmth, 2),
        "updated_at": state.updated_at,
        "grievances": [
            {
                "text": g.text,
                "weight": g.weight,
                "created_at": g.created_at,
                "resolved_at": g.resolved_at,
            }
            for g in state.grievances[-50:]
        ],
    }


def from_dict(payload: dict | None) -> Relationship:
    if not isinstance(payload, dict):
        return Relationship()

    grievances = []

    for raw in payload.get("grievances") or []:
        if not isinstance(raw, dict) or not raw.get("text"):
            continue

        grievances.append(
            Grievance(
                text=str(raw["text"]),
                weight=float(raw.get("weight") or 1.0),
                created_at=float(raw.get("created_at") or 0.0),
                resolved_at=(
                    float(raw["resolved_at"]) if raw.get("resolved_at") is not None else None
                ),
            )
        )

    return Relationship(
        warmth=float(payload.get("warmth", WARMTH_START)),
        updated_at=float(payload.get("updated_at") or 0.0),
        grievances=grievances,
    )
