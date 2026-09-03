"""Hangi platform hangi araçlara erişir.

İki ayrı sorunu tek yerde çözüyor; ikisi de sessiz sınıfından.

**Bir: marka yeniden adlandırması bileşik takım adlarını kopardı.**
``fool_cli/platforms.py`` her platformun ``default_toolset`` değerini
``hermes-telegram`` -> ``fool-telegram`` diye çevirdi, ama bileşikleri
tanımlayan ``toolsets.py`` upstream'in dosyası ve hâlâ ``hermes-*`` diyor.
``resolve_toolset("fool-telegram")`` boş liste döndürüyordu. ``config.yaml``
içinde açık kaydı olmayan her platform SIFIR araçla koşuyordu -- hata yok,
uyarı yok, model sadece istenen şeyi yapamıyor. Adı ``upstream_toolset_alias``
ile geri çeviriyoruz; markalama görünürde kalıyor, çözümleme çalışıyor.

**İki: uzak platformlar varsayılan olarak kısıtsız.** Yukarıdaki adı
düzeltmek tek başına DAHA KÖTÜ olurdu: her platform bir anda 59 araçlık
bileşiğe kavuşurdu ve içinde ``computer_use``, ``execute_code``,
``terminal_run``, ``read_file``, 13 tane ``browser_*`` var. WhatsApp'a ya da
Telegram'a yazabilen herkes -- aile, arkadaş, numarayı bilen biri -- makineyi
sürerdi. O yüzden iki yarı birlikte iniyor.

Politika **liste dışında kalan her şey uzaktır** diye yazıldı, tersi değil.
Yarın eklenecek bir platform eklentisi kısıtlı doğar; birinin güvenlik
listesini güncellemeyi hatırlamasına bağlı değil.

Kullanıcının ``config.yaml``'a kendi yazdığı liste her zaman kazanır: burası
yalnızca hiç seçim yapılmamışken devreye giren varsayılan.
"""

from __future__ import annotations

_FOOL_PREFIX = "fool-"
_UPSTREAM_PREFIX = "hermes-"

#: Sahibinin kendi makinesindeki yüzeyler. Buradan gelen istem kullanıcının
#: kendisinden geliyor, o yüzden kısıtlama yok. ``cron`` da buraya ait:
#: zamanlanmış işleri kuran kişi sahibin kendisi.
#:
#: Not: ``apps/desktop/src/lib/session-source.ts`` içindeki
#: ``LOCAL_SESSION_SOURCE_IDS`` ile aynı ayrım -- ikisi birlikte güncellenmeli.
LOCAL_PLATFORMS = frozenset({
    "acp",
    "cli",
    "codex",
    "cron",
    "desktop",
    "gateway",
    "kanban",
    "local",
    "tui",
})

#: Uzak birinin mesajıyla açılan bir oturumda kalan araçlar. Araştırma ve
#: içerik üretimi kalıyor; kontrol ve bilgi sızması kesiliyor:
#:
#:   file        -> ``read_file`` diskteki her şeyi okur
#:   terminal    -> keyfi komut
#:   code_execution / computer_use -> makinenin kendisi
#:   memory / session_search       -> sahibinin geçmiş sohbetleri
#:   delegation  -> alt ajan kısıtlamayı dolanır
#:   cronjob     -> kalıcı zamanlanmış iş bırakır
#:   browser     -> oturum açılmış hesaplar
SAFE_REMOTE_TOOLSETS = (
    "clarify",
    "image_gen",
    # Yalnizca YAZAN, okuma yetkisi olmayan dosya uretimi. Bu takim olmadan
    # "bana bunun PDF'ini cikar" demek imkansizdi: dosya yazmak ``file``
    # takimini gerektiriyor, o da ``read_file`` getiriyor -- yani tek bir
    # dosya uretebilmek icin tum diski okutmak gerekiyordu.
    "output_file",
    "tts",
    "vision",
    "web",
)


def upstream_toolset_alias(name: str) -> str | None:
    """``fool-telegram`` -> ``hermes-telegram``; başka her şey için ``None``.

    Yalnızca ÖN EKİ çevirir. Çağıran taraf önce ``fool-*`` adının gerçekten
    tanımlı olup olmadığına bakar; bu yalnızca tanımsızsa denenen yedek yol.
    """
    if not isinstance(name, str) or not name.startswith(_FOOL_PREFIX):
        return None
    return _UPSTREAM_PREFIX + name[len(_FOOL_PREFIX):]


def is_remote_platform(platform: str) -> bool:
    """İstemi UZAK biri mi gönderiyor?

    Bilinmeyen ad ``True`` döner -- yeni bir adaptör sessizce tam yetki
    almasın diye kapalı tarafa düşüyoruz.
    """
    if not isinstance(platform, str):
        return True
    return platform.strip().lower() not in LOCAL_PLATFORMS


def default_toolsets_for(platform: str) -> list[str] | None:
    """Hiç yapılandırılmamış bir platformun araç takımı listesi.

    Uzak platformlar için güvenli liste, yerel olanlar için ``None`` --
    ``None`` "üstteki normal varsayılana (platformun bileşiği) devam et"
    demek.
    """
    if is_remote_platform(platform):
        return list(SAFE_REMOTE_TOOLSETS)
    return None
