/**
 * "Kullanıcı ŞU AN hangi sohbete bakıyor?" — tek cevap.
 *
 * Neden tek bir yerde
 * -------------------
 * Bu soruya iki yüzey birden ihtiyaç duyuyor ve ikisi de aynı tuzağa düştü:
 *
 *   * HUD düştü, öğrendi ve kendi çözümleyicisini yazdı
 *     (``app/hud/handoff.ts::hudTargetSessionId``). Yorumu ölçülen hatayı
 *     anlatıyor: ``$selectedStoredSessionId`` ÇALIŞMA ALANI bölmesinin
 *     oturumu, yani hangi sekme önde olursa olsun HUD'a ana sekme gidiyordu.
 *   * Çentik düşmedi -- çünkü o dersi hiç görmedi. Ses köprüsü
 *     (``store/active-work.ts``) ``$activeSessionId``i olduğu gibi yayınlıyor
 *     ve kullanıcı başka bir sekmeye/kutucuğa geçtiğinde ses hâlâ eski
 *     oturuma gidiyor.
 *
 * Kullanıcının bildirdiği: "notch her zaman odaktaki sessiona bağlı olmalı,
 * kullanıcı yeni sessionda notchu kullanırsa o sessiona gitmeli mesaj."
 *
 * Ders bir modülde yazılıp kardeşine geçmediği sürece üçüncü yüzey de aynı
 * yere düşecekti. Cevap artık burada, ve iki taraf da buradan okuyor.
 *
 * Neden ``getActiveComposer``
 * ---------------------------
 * Odak veri yolu bu soruyu ZATEN cevaplıyor: iddiası gömülü ya da yok olduğunda
 * görünür yüzeye iyileşiyor, ve bir kutucuğun yönlendirme anahtarı
 * (``tile:<id>``) doğrudan onun saklanan oturum kimliği. Atomlar kutucukları
 * hiç görmüyor -- HUD'un ayrı bir çözümleyici yazmak zorunda kalmasının sebebi
 * tam olarak buydu.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { getActiveComposer } from '@/app/chat/composer/focus'
import { $activeSessionId, $selectedStoredSessionId } from '@/store/session'
import { $sessionTiles } from '@/store/session-states'

/** Kutucuk besteciler ``tile:<storedSessionId>`` ile yönlendiriliyor. */
const TILE_PREFIX = 'tile:'

/**
 * Kullanıcının baktığı sohbetin saklanan kimliği (``null`` = yok).
 *
 * Önce odaktaki besteci, sonra çalışma alanı bölmesi. Sıra önemli: tersi,
 * hangi kutucuk önde olursa olsun ana sekmeyi döndürürdü.
 */
export function focusedSessionId(): null | string {
  const target = getActiveComposer()
  const tile = target.startsWith(TILE_PREFIX) ? target.slice(TILE_PREFIX.length) : null

  return tile || $selectedStoredSessionId.get()
}

/**
 * Odaktaki yüzeyin CANLI (ağ geçidi) oturum kimliği (``''`` = yok).
 *
 * ``focusedSessionId`` ile AYNI ŞEY DEĞİL ve karıştırmak göndermeyi tümden
 * bozar. İki ayrı kimlik uzayı var:
 *
 *   * SAKLANAN kimlik -- kenar çubuğu satırının kalıcı kimliği. Yönlendirme,
 *     devretme ve okundu işareti bunu kullanıyor.
 *   * CANLI (``runtimeId``) -- ağ geçidinin o an bağlı olduğu oturum.
 *     ``prompt.submit`` ve ``session.interrupt`` bunu istiyor.
 *
 * Kutucuklar ikisini ayrı taşıyor (``SessionTile.storedSessionId`` /
 * ``runtimeId``); çalışma alanı bölmesinin canlısı ``$activeSessionId``.
 *
 * ``''`` DÖNMEK BİR CEVAP: odaktaki sohbet henüz başlamamışsa (yeni bir
 * sekme, ya da devam ettirilmemiş bir kutucuk) canlı oturum YOK. Bu durumda
 * bir öncekinin kimliğini vermek, sesi kullanıcının bakmadığı sohbete
 * göndermek olurdu -- bildirilen hatanın ta kendisi. Boş dönmek çentiğin
 * "önce bir oturum aç" yolunu (``waitForVoiceSessionOrOpen``) tetikliyor.
 */
export function focusedRuntimeSessionId(): string {
  const target = getActiveComposer()

  if (target.startsWith(TILE_PREFIX)) {
    const storedSessionId = target.slice(TILE_PREFIX.length)
    const tile = $sessionTiles.get().find(item => item.storedSessionId === storedSessionId)

    if (tile?.runtimeId) {
      return tile.runtimeId
    }

    // Kutucuğun canlı oturumu YOKSA burada BOŞ DÖNMÜYORUZ, çalışma alanına
    // düşüyoruz.
    //
    // Ölçülen kırıklık: boş dönmek çentiği "yeni oturum aç" yoluna sokuyordu
    // ve kullanıcının ekranda AÇIK bir sohbeti dururken mesaj bambaşka bir
    // yere gidiyordu -- bildirdiği tam olarak buydu: "bambaşka bir sessiondaki
    // mesaj anlık gözüktü, sohbete düşmedi bile."
    //
    // Kullanıcının kuralı: "kullanıcı hâlihazırda bir session penceresindeyse
    // o sessiona gitmeli mesaj." Odaktaki kutucuk henüz canlı değilse, ekranda
    // canlı olan şey çalışma alanının sohbetidir; ona gitmek, hiçbir yere
    // gitmemekten de yeni bir oturum açmaktan da doğru.
  }

  return $activeSessionId.get() ?? ''
}
