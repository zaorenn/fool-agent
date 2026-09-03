"""Bilmediğini fark et ve ara sıra sor.

İstenen davranış
----------------
"Konuştukça öğrenen, bazen tanımak için sorular sorabilen ve gerçekten
kullanıcıyı tanımaya çalışıp hem hatalarından hem kullanıcının sevdiği şeyleri
öğrenip kişiselleşen bir şey."

Bugünkü hâl bunun yalnızca yarısını yapıyor: ``remember()`` var, yani söylenen
bir şey saklanabiliyor. Ama hiçbir şey SÖYLENMEZSE hiçbir şey öğrenilmiyor.
Aylarca konuşup kullanıcının ne iş yaptığını bilmemek tamamen mümkün, çünkü
model kendi bilgi boşluğunu hiç görmüyor -- ona yalnızca BULUNAN anılar
gösteriliyor, bulunmayanlar değil.

Burası eksik olanı gösteriyor: kapsanmamış tek bir konu.

Neden en fazla BİR ve neden her oturumda değil
----------------------------------------------
Sorular ucuz görünüyor ama üst üste konduklarında sohbet anket oluyor.
Kullanıcı bir şey yaptırmak için gelmişken "peki boş vakitlerinde ne
yaparsın?" duymak, yardımcının o an ne için orada olduğunu unutmuş olması
demek. Bu yüzden:

  * turda EN FAZLA bir konu görünüyor,
  * konu bir DAVET olarak veriliyor, talimat olarak değil ("doğal gelirse"),
  * kapsanmış bir konu bir daha hiç sorulmuyor,
  * hepsi kapsandığında modül tamamen susuyor.

Neden iki ayrı konu kümesi
--------------------------
Kullanıcı hem "kişiselleşen" hem "profesyonel işlerde yetkin" istedi ve iki
profil zaten ayrı hafızalar kullanıyor. Sıradan ajanın ortasında "en sevdiğin
müzik ne?" sorusu yanlış soru: orada kişiselleşmenin anlamı, NASIL çalışılmasını
istediğini öğrenmek. Persona profilinde ise doğru soru tam da kişisel olan.

Aynı listeyi ikisine de vermek, birinde alakasız birinde yüzeysel olurdu.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    """Öğrenilmemiş tek bir şey."""

    #: Kalıcı kimlik -- kapsandı kaydı buna göre tutuluyor.
    id: str
    #: Konunun kapsanıp kapsanmadığını arayan sorgu (anlamsal arama girdisi).
    query: str
    #: Bir anının bu konuyu kapsadığını gösteren sözcükler.
    markers: tuple[str, ...]
    #: Modele verilen DAVET. Soru cümlesi değil: sorunun kendisini modelin
    #: kendi ağzıyla kurması, listeden okunmuş gibi durmamasını sağlıyor.
    invitation: str


#: Persona profili: kişiyi tanımak.
#:
#: Sıra ÖNEMLİ -- ilk sıradakiler bir insanın gerçekten önce sorduğu şeyler.
#: Aile, sağlık, para gibi konular listede YOK: bunlar kendiliğinden anlatılır,
#: sorulduğunda sorgu gibi durur.
COMPANION_TOPICS: tuple[Topic, ...] = (
    Topic(
        id="name",
        query="what they are called, their name",
        markers=("name", "called", "adı", "ismi"),
        invitation="what they would like you to call them",
    ),
    Topic(
        id="work",
        query="what they do for a living, their job or studies",
        markers=("work", "job", "studies", "student", "engineer", "iş", "çalışıyor", "okuyor"),
        invitation="what they spend their working hours on",
    ),
    Topic(
        id="place",
        query="where they live, their city or country",
        markers=("lives", "living", "city", "from", "yaşıyor", "şehir"),
        invitation="where they are",
    ),
    Topic(
        id="rest",
        query="what they do to relax, hobbies, games, music",
        markers=("hobby", "hobbies", "plays", "music", "game", "reads", "oyun", "müzik"),
        invitation="what they do when they are not working",
    ),
    Topic(
        id="dislikes",
        query="what annoys them, what they cannot stand",
        markers=("hates", "dislikes", "annoys", "cannot stand", "sevmiyor", "nefret"),
        invitation="what reliably annoys them",
    ),
    Topic(
        id="rhythm",
        query="their daily rhythm, when they sleep and wake",
        markers=("sleeps", "wakes", "night owl", "morning", "uyu", "sabah", "gece"),
        invitation="how their day is usually shaped",
    ),
    Topic(
        id="people",
        query="the people close to them, friends, partner",
        markers=("friend", "partner", "brother", "sister", "arkadaş", "kardeş"),
        invitation="who matters to them",
    ),
    Topic(
        id="wants",
        query="what they are working towards, what they want",
        markers=("wants", "hopes", "goal", "dream", "istiyor", "hedef"),
        invitation="what they are trying to get to",
    ),
)

#: Sıradan ajan: kişiyi değil, NASIL ÇALIŞILMASINI istediğini öğrenmek.
#:
#: Buradaki her konu bir sonraki turu somut olarak değiştiriyor. "En sevdiğin
#: renk" değiştirmiyor, o yüzden burada yok.
WORKING_TOPICS: tuple[Topic, ...] = (
    Topic(
        id="address",
        query="how they want to be addressed, their name",
        markers=("name", "called", "adı", "ismi"),
        invitation="what to call them",
    ),
    Topic(
        id="stack",
        query="the languages and tools they work in",
        markers=("python", "typescript", "rust", "uses", "stack", "kullanıyor"),
        invitation="what they usually work in",
    ),
    Topic(
        id="answer_shape",
        query="how much explanation they want, short or detailed answers",
        markers=("prefers", "wants", "short", "detailed", "explain", "kısa", "detay"),
        invitation="how much explanation they actually want from you",
    ),
    Topic(
        id="conventions",
        query="their conventions, code style, house rules",
        markers=("convention", "style", "always", "never", "rule", "kural", "stil"),
        invitation="the rules of their own house that you keep breaking otherwise",
    ),
    Topic(
        id="checks",
        query="whether they want to be asked before changes, or just told after",
        markers=("ask", "confirm", "before", "without asking", "sorma", "onay"),
        invitation="when they want to be asked first and when they want you to just do it",
    ),
)


def topics_for(*, companion: bool) -> tuple[Topic, ...]:
    return COMPANION_TOPICS if companion else WORKING_TOPICS


def _covered(topic: Topic, memories: list[str]) -> bool:
    """Bu konuyu kapsayan bir anı var mı?

    Sözcük eşleme, anlamsal arama DEĞİL: burada verilecek karar "sor / sorma"
    ve yanlış tarafa düşmenin bedeli asimetrik. Kapsanmışı kapsanmamış sanmak
    kullanıcıya bildiği bir şeyi tekrar sordurur -- yardımcının dinlemediğini
    gösteren tek şey. Kapsanmamışı kapsanmış sanmak yalnızca bir soruyu
    ertelemiş olur; konu listede kalır ve başka bir gün açılır.

    O yüzden eşleme GENİŞ: tek bir belirteç yetiyor.
    """
    if not memories:
        return False

    joined = " ".join(memories).lower()

    return any(re.search(r"\b" + re.escape(marker) + r"\b", joined) for marker in topic.markers)


def next_topic(
    memories: list[str],
    *,
    companion: bool,
    asked: set[str] | None = None,
) -> Topic | None:
    """Sırada sorulacak tek konu (``None`` = sorulacak bir şey kalmadı).

    ``asked`` bu profilde daha önce SORULMUŞ konular. Kapsanmış olmasa bile
    bir daha sorulmuyor: cevap vermemek de bir cevap ve aynı soruyu üçüncü kez
    sormak, dinlemediğini göstermenin en hızlı yolu.
    """
    seen = asked or set()

    for topic in topics_for(companion=companion):
        if topic.id in seen:
            continue

        if not _covered(topic, memories):
            return topic

    return None


def prompt_line(topic: Topic) -> str:
    """Sistem promptuna giren tek satır.

    Emir kipi DEĞİL. "Şunu sor" diyen bir satır, model tam da kullanıcının
    bir işi yaptırmaya çalıştığı turda sorar. "Doğal gelirse" ise soruyu
    sohbetin kendi akışına bırakıyor ve gelmezse hiç sorulmuyor -- konu
    listede kaldığı için kaybolmuyor da.
    """
    return (
        "You still do not know " + topic.invitation + ". If the conversation "
        "gives you a natural opening, ask -- once, in your own words, and let "
        "it go if they do not feel like answering. Never interrupt what they "
        "are doing to ask."
    )
