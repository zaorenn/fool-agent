"""Arkadaşınla konuşmak, ona terminalini vermek değil.

Ölçülen durum
-------------
Notch'un sesli turu, masaüstü sohbet panelinin OTURUMUNU paylaşıyor
(``$activeSessionId``). O oturum ``desktop`` kapsamında kuruluyor ve ölçtüm
(``tui_gateway.server._load_enabled_toolsets``, FOOL_DESKTOP=1):

    21 takım -- bfl, browser, clarify, code_execution, computer_use, cronjob,
    delegation, desktop_ui, file, image_gen, kanban, memory, project,
    session_search, skills, spotify, terminal, todo, tts, vision, web

Yani "hey, hava nasıl?" diyen sesli arkadaş, ``terminal_run``,
``computer_use``, ``execute_code`` ve ``delegate_task``a sahip. Kullanıcı
mikrofona konuşurken makinesinin tamamını açık tutuyor ve bunu hiçbir yerde
görmüyor.

İki ayrı sorun, tek kök:

1. **Yetki.** Sohbet için gereken araçlar ile iş yapmak için gereken araçlar
   aynı değil. Sesli sohbette yanlış anlaşılan bir cümlenin bedeli
   ``terminal_run`` olmamalı.
2. **Bağlam.** Sesli sohbet, ajanın üzerinde çalıştığı oturumun bağlamına
   karışıyor; iki farklı iş tek geçmişte birikiyor.

Bu modül KAPSAMI tanımlıyor. Kapsam bir oturum özelliği, tur özelliği değil:
tur başına araç değiştirmek ajanı yeniden kurmak demek ve donmuş sistem
promptu + araç şemaları üzerine kurulu prompt önbelleğini her turda çöpe
atardı (bkz. ``gateway/run.py`` ajan önbelleği).
"""

from __future__ import annotations

#: Uzak sesli arkadaş kapsamı (WhatsApp, Telegram, notch...).
COMPANION = "companion"

#: Masaüstündeki Friend penceresi.
#:
#: ``companion``dan TEK farkı hafıza. Uzak bir kullanıcıya sahibinin geçmiş
#: sohbetlerini açmak sızıntı; kendi makinesinde kendi penceresinde AÇMAMAK
#: ise arkadaşı hafızasız bırakmak -- her seferinde kendini yeniden anlatmak
#: zorunda kalıyorsun. Bu pencere yerel ve sahibinin, o yüzden hafıza ORTAK:
#: Friend ile ajan aynı ``MEMORY.md`` / ``USER.md`` dosyalarını görüyor.
FRIEND = "friend"

#: Sahibinin iş yaptığı kapsam (masaüstü sohbet paneli, TUI, CLI).
AGENT_SCOPES = frozenset({"cli", "desktop", "tui"})

#: Sesli sohbetin araçları.
#:
#: Ölçüt: "bu araç yanlış çağrılırsa bedeli ne?" Sohbette yanlış anlaşılma
#: sık ve normal; bedeli boşa giden bir tur olmalı, silinmiş bir dosya değil.
#:
#:   clarify      -- "ne demek istedin?" sorabilmek
#:   image_gen    -- görsel üretmek
#:   output_file  -- rapor/PDF üretmek (yalnızca yazan, okuma yetkisi yok)
#:   tts / vision -- konuşmak, gösterileni görmek
#:   web          -- bir şeye bakmak
#:
#: DIŞARIDA bırakılanlar ve sebepleri:
#:   terminal / file / code_execution / computer_use -- makinenin kendisi
#:   memory / session_search -- sahibinin geçmiş sohbetleri
#:   delegation  -- alt ajan kısıtlamayı dolanır
#:   cronjob     -- kalıcı zamanlanmış iş bırakır
#:   browser     -- oturum açılmış hesaplar
#:   tts         -- MASAÜSTÜ ZATEN SESLENDİRİYOR (bkz. aşağıdaki not)
COMPANION_TOOLSETS = (
    "clarify",
    "image_gen",
    "output_file",
    "vision",
    "web",
)

# ``tts`` BİLEREK dışarıda -- ölçülen gerçek hata
# ---------------------------------------------------
# Masaüstü zaten HER cevabı kendi hattından seslendiriyor
# (``use-friend-voice.ts`` / ``use-notch-voice.ts``, cümle cümle akıtarak).
# Ajana AYRICA bir ``text_to_speech`` aracı vermek, WhatsApp/Telegram gibi
# istemci tarafı sesi OLMAYAN yüzeyler için doğru (orada "konuşmak" = ses
# dosyası üretip mesaj olarak göndermek, başka yolu yok) ama masaüstü sesli
# yüzeylerinde yanlış: ajan kendi kendine de sentez çağırmaya başlıyor.
#
# Gerçekte gözlemlendi (kullanıcının ekran görüntüsü): tek bir "hava nasıl"
# turunda ajan ÜÇ KEZ "Thought → Text To Speech" döngüsüne girdi, final
# metin öncekiyle YİNELENEREK göründü (aynı cümle art arda iki kez), ve
# masaüstünün kendi sentezi -- aynı motoru paylaştığı için -- "Preparing
# audio" / "Waking the model" durumunda TAKILI kaldı. Üç gereksiz araç
# çağrısı final metnin gelişini de geciktiriyordu -- kullanıcının "sonrasında
# model uyandırılıyor dedi" şikayetinin bir parçası buydu.
#
# Kapsam bilerek FRIEND_TOOLSETS ile PAYLAŞILMIYOR (ikisi de ayrı tanımlı,
# ortak bir sabite çıkarılmadı): biri değişip diğeri unutulursa sessizce
# ayrışırlardı; burada ikisinin de "tts" içermediği ayrı ayrı test ediliyor.

#: Notch'un ``prompt.submit`` ile gönderdiği yüzey ipucu. Bugün sunucu
#: tarafında hiçbir şey okumuyor -- bu modülün var olma sebeplerinden biri.
COMPANION_SURFACES = frozenset({"companion", "hud", "notch"})

#: Friend penceresinin araçları: uzak arkadaşınkiler + HAFIZA.
#:
#: ``memory`` burada var, ``companion``da yok ve fark bilinçli: orada
#: kullanıcı uzakta ve tanınmıyor, burada makinenin sahibi kendi
#: penceresinde. ``session_search`` yine DIŞARIDA -- geçmiş sohbetleri
#: taramak hatırlamaktan farklı bir şey ve sohbet için gerekmiyor.
#: ``tts`` burada da YOK, aynı sebepten -- yukarıdaki notu bkz.
FRIEND_TOOLSETS = (
    "clarify",
    "image_gen",
    "memory",
    "output_file",
    "vision",
    "web",
)


#: Masaüstündeki Chat kipi (Chat/Cowork anahtarının "Chat" tarafı).
CHAT = "chat"

#: Chat kipinin araçları.
#:
#: TEK BİR BİLEŞİK küme -- komşularının aksine (``COMPANION_TOOLSETS`` ve
#: ``FRIEND_TOOLSETS`` birer takım listesi). Sebep somut: Chat'in "oku ama
#: yazma" sınırı mevcut takımların hiçbiriyle çizilemiyor. ``file`` takımı
#: karışık (``read_file``/``search_files`` okuyor, ``write_file``/``patch``
#: yazıyor) ve yarısını almak ancak araç ADIYLA mümkün -- takım adıyla değil.
#: Bileşik ``toolsets.py``de tanımlı ve ``tests/fool/test_chat_toolset.py``
#: yazan hiçbir aracın sızmadığını orada tutuyor.
#:
#: Çentikten FARKI: ``companion`` sesle konuşan uzak kullanıcı,
#: ``chat`` ise sahibinin kendi klavyesi. Sahibi dosyasını OKUTABİLMELİ ve
#: geçmişini aratabilmeli; uzak kullanıcı ikisini de yapamamalı. Aynı sabite
#: çıkarılmamasının sebebi de bu -- ayrı sorular, ayrı cevaplar.
CHAT_TOOLSETS = ("chat",)


def is_companion_surface(surface: object) -> bool:
    """Bu yüzey sesli arkadaş mı?"""
    if not isinstance(surface, str):
        return False
    return surface.strip().lower() in COMPANION_SURFACES


def scope_toolsets(scope: object) -> list[str] | None:
    """Bu kapsamın araç takımları.

    ``None`` = "kapsama özel bir kısıtlama yok, normal çözümlemeye devam et".
    Bilinmeyen bir kapsamı kısıtlamak, tanımadığımız bir yüzeyi sessizce
    kırmak olurdu.

    ``jarvis`` bilerek ``None`` döner: Jarvis kipi sahibinin TAM yüzeyini
    alıyor (kullanıcının açık tercihi). Kısıtlama orada değil, tool-calling
    sınavında -- bkz. ``fool/voice_modes.py`` ve ``fool/agent_authority.py``.
    """
    key = scope.strip().lower() if isinstance(scope, str) else ""
    if key == COMPANION:
        return list(COMPANION_TOOLSETS)
    if key == FRIEND:
        return list(FRIEND_TOOLSETS)
    if key == CHAT:
        return list(CHAT_TOOLSETS)
    return None


#: KENDİ cevabını KENDİSİ seslendiren kapsamlar.
#:
#: Yukarıdaki ``COMPANION_TOOLSETS`` notu bu hatayı zaten anlatıyor ve dersi
#: iki komşuya (companion, friend) uygulamıştı. ``desktop`` ATLANMIŞTI ve
#: ölçüldü: masaüstü kapsamının son araç listesinde ``text_to_speech`` duruyor.
#: Kullanıcının bildirdiği: "bazen aynı cümleleri 2 kere speak aloud yapıyor."
#:
#: Bu depoda tekrar eden kalıbın ta kendisi -- bir modülde öğrenilen ders
#: kardeşine taşınmıyor. O yüzden kural artık bir YORUM değil, tek bir yerde
#: duran VERİ: masaüstünün her yüzeyi burada.
SELF_VOICED_SCOPES = frozenset({"chat", "companion", "desktop", "friend", "hud", "notch"})

#: Seslendiren yüzeyden düşürülen takım ve yerine konan.
#:
#: Takım toptan düşürülMÜYOR: ``tts`` iki araç taşıyor ve ikincisi
#: ``set_language_mode`` -- "ses dilini japonca yap" isteğini gerçekten
#: uygulayan araç. Onu da almak, düzeltilmiş bir hatayı sessizce geri kırmak
#: olurdu (model "tamam" der, ayar değişmez). ``speech_settings`` tam olarak
#: o aracı taşıyor, ``text_to_speech``i taşımıyor.
SELF_VOICED_DROP = "tts"
SELF_VOICED_KEEP = "speech_settings"


def strip_self_voiced(scope: object, toolsets: list[str] | None) -> list[str] | None:
    """Seslendiren yüzeyden sentez aracını düşür, dil ayarını bırak.

    ``None`` aynen geçer: "kapsama özel kısıtlama yok" demek ve burada bir
    şey uydurmak, çözümlemenin geri kalanını atlamak olurdu.

    Kapsam seslendirmiyorsa liste DOKUNULMADAN döner -- WhatsApp/Telegram gibi
    istemci tarafı sesi olmayan yüzeylerde "konuşmak" = ses dosyası üretmek ve
    ``text_to_speech`` orada tek yol.
    """
    if toolsets is None:
        return None

    key = scope.strip().lower() if isinstance(scope, str) else ""
    if key not in SELF_VOICED_SCOPES or SELF_VOICED_DROP not in toolsets:
        return list(toolsets)

    kept = [name for name in toolsets if name != SELF_VOICED_DROP]
    if SELF_VOICED_KEEP not in kept:
        kept.append(SELF_VOICED_KEEP)

    return sorted(kept)
