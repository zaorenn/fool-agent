/**
 * Chat ↔ Cowork kipi.
 *
 * Ne olduğu
 * ---------
 * ``Cowork`` uygulamanın bugünkü hâli: bütün araçlar, proje ağacı, zamanlanmış
 * işler. ``Chat`` hızlı konuşmak için: model OKUYABİLİYOR (web, dosya, geçmiş,
 * hafıza) ama hiçbir şeyi değiştiremiyor -- yazma, komut çalıştırma, tarayıcı
 * sürme yok.
 *
 * Hız nereden geliyor
 * -------------------
 * Araç şemaları HER TURDA modele gidiyor. Ölçüldü: ``chat`` kümesi ~4.5K
 * token, ``coding`` ~10.3K. Yani Chat kipi tur başına ~5.800 token daha az
 * gönderiyor -- ağda da, modelin okuduğu bağlamda da.
 *
 * Kip neden OTURUM özelliği
 * -------------------------
 * Araç şemaları donmuş sistem promptunun parçası ve prompt önbelleği onun
 * üzerine kurulu (bkz. ``fool/session_scope.py``). Tur başına araç
 * değiştirmek ajanı yeniden kurmak demek.
 *
 * Kip oturumun ``source`` alanında yaşıyor ve ağ geçidi zaten onu okuyup
 * kapsamı seçiyor -- bu dosya yeni bir hakikat kaynağı EKLEMİYOR, var olanı
 * okuyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { computed } from 'nanostores'

import { persistentAtom } from '@/lib/persisted'
import { activeGateway, ensureActiveGatewayOpen } from '@/store/gateway'
import { $selectedStoredSessionId, $sessions, sessionMatchesStoredId, setSessions } from '@/store/session'

export type ChatMode = 'chat' | 'cowork'

/** Chat kipindeki oturumların ``source`` değeri. */
export const CHAT_SOURCE = 'chat'

/**
 * Cowork'ün ``source`` değeri -- ``'cowork'`` DEĞİL.
 *
 * Ağ geçidi ``source``u kapsam çözümlemesinde kullanıyor ve ``desktop``
 * masaüstünün olağan kapsamı. ``'cowork'`` yazmak tanınmayan bir kapsam
 * üretirdi; bugün zararsız (kısıtlama uygulanmıyor) ama sessizce yanlış --
 * ileride biri o adı gerçek bir kapsam yaptığında kip anlamını değiştirirdi.
 */
export const COWORK_SOURCE = 'desktop'

/** Bir oturumun kaynağından kipini çıkar. */
export function modeOfSource(source: null | string | undefined): ChatMode {
  return (source ?? '').trim().toLowerCase() === CHAT_SOURCE ? 'chat' : 'cowork'
}

/**
 * YENİ sohbetler hangi kipte açılsın?
 *
 * Neden ayrı bir tercih
 * ---------------------
 * Kip bir oturum özelliği, ama kullanıcı henüz oturum AÇMADAN da seçebilmeli:
 * "yeni bir sessiondayken ya da hiçbir session açık değilken de değişilip yeni
 * sessionları ordan da açabilmeliyiz."
 *
 * İlk yazımda anahtar açık oturum yoksa hiçbir şey yapmıyordu -- yani Chat
 * kipiyle yeni bir sohbete BAŞLAMANIN yolu yoktu, ancak Cowork'te açıp sonra
 * çevirebiliyordun. Tam tersi olmalı: yeni sohbet ucuz, çevirmek pahalı.
 *
 * Kalıcı: kullanıcı Chat'te çalışıyorsa uygulamayı kapatıp açınca oraya
 * dönmeli.
 */
export const $newChatMode = persistentAtom<ChatMode>('fool.desktop.chat.newSessionMode', 'cowork', {
  decode: raw => (raw === 'chat' ? 'chat' : 'cowork'),
  encode: value => value
})

/**
 * Bu saklanan oturumun kipi.
 *
 * HENÜZ LİSTEDE OLMAYAN oturum, yeni sohbet tercihine düşüyor -- ``cowork``
 * varsayılmıyor.
 *
 * Ölçülen kırıklık: kullanıcı Chat kipinde yeni sohbet ekranındayken çentikten
 * konuşuyor, ana pencere oturumu oluşturuyor ve seçim ona geçiyor -- ama
 * ``$sessions`` listesi henüz tazelenmemiş oluyor. Liste onu tanımadığı için
 * anahtar bir anda Cowork'e atlıyordu. Kullanıcının bildirdiği: "chat modunda
 * new session ekranında notchu çalıştırdım, ekran cowork'e geldi."
 *
 * Bilinen bir oturumun kaynağı hâlâ kazanıyor: düşme yalnızca liste onu
 * görene kadar geçerli, ve o aralıkta doğru cevap zaten "az önce hangi kipte
 * açtıysak o".
 */
export function modeOfSession(storedSessionId: null | string): ChatMode {
  if (!storedSessionId) {
    return $newChatMode.get()
  }

  const found = $sessions.get().find(session => sessionMatchesStoredId(session, storedSessionId))

  return found ? modeOfSource(found.source) : $newChatMode.get()
}



/**
 * Şu an geçerli kip: açık sohbetin kipi, sohbet yoksa YENİ sohbet tercihi.
 *
 * Sohbet yokken ``cowork`` varsaymak, kullanıcının seçtiği Chat kipini
 * anahtarda göstermemek olurdu -- seçim yapılmış ama görünmüyor.
 */
export function activeMode(): ChatMode {
  const selected = $selectedStoredSessionId.get()

  return selected ? modeOfSession(selected) : $newChatMode.get()
}

/**
 * Kenar çubuğu SADELEŞSİN mi?
 *
 * Chat kipinde projeler, zamanlanmış işler, pinler ve filtreler gizleniyor;
 * geriye arama ve sohbet listesi kalıyor.
 *
 * Gizlenen bölümlerin DURUMU korunuyor (açık/kapalı, sıralama, filtreler):
 * Chat'e girip çıkmak kullanıcının düzenini sıfırlamamalı. O yüzden bu bir
 * görünürlük kapısı, bir sıfırlama değil.
 */
export const $chatSimpleSidebar = computed(
  [$selectedStoredSessionId, $sessions, $newChatMode],
  (selected, sessions, newMode): boolean => {
    // Sohbet YOKKEN de sadeleşiyor: kullanıcı Chat kipini seçtiyse kenar
    // çubuğu onu göstermeli, ilk mesajı beklemeden.
    if (!selected) {
      return newMode === 'chat'
    }

    const found = sessions.find(session => sessionMatchesStoredId(session, selected))

    // Liste henüz tazelenmemişse yeni sohbet tercihine düş: aksi hâlde
    // kenar çubuğu, oturum oluşur oluşmaz bir an Cowork'e açılırdı.
    return found ? modeOfSource(found.source) === 'chat' : newMode === 'chat'
  }
)

/** Yeni bir oturumun ``source``u -- ``session.create``e giden değer. */
export function newSessionSource(): string {
  return $newChatMode.get() === 'chat' ? CHAT_SOURCE : COWORK_SOURCE
}

/**
 * Bir oturumun kipini DEĞİŞTİR.
 *
 * Ağ geçidi canlı ajanı bırakıyor: araç kümesi değişince sistem promptu ve
 * onun üzerine kurulu önbellek geçersiz oluyor. Bedeli TEK bir tur -- değişimden
 * sonraki ilk cevap önbelleksiz geliyor. Arayüz bunu kullanıcıya soruyor.
 *
 * Yerel liste ÖNCE güncelleniyor: ağ geçidi cevabını beklemek, kullanıcının
 * onayladığı değişimin bir saniye boyunca ekranda görünmemesi demekti. Hata
 * olursa geri alınıyor.
 */
export async function setSessionMode(storedSessionId: string, mode: ChatMode): Promise<void> {
  const source = mode === 'chat' ? CHAT_SOURCE : COWORK_SOURCE
  const previous = $sessions.get().find(session => sessionMatchesStoredId(session, storedSessionId))?.source ?? null

  const write = (value: null | string) =>
    setSessions(sessions =>
      sessions.map(session => (sessionMatchesStoredId(session, storedSessionId) ? { ...session, source: value } : session))
    )

  write(source)

  try {
    let gateway = activeGateway()

    if (!gateway || gateway.connectionState !== 'open') {
      gateway = await ensureActiveGatewayOpen()
    }

    if (!gateway) {
      throw new Error('The Fool gateway is not connected')
    }

    await gateway.request('session.mode', { mode, session_key: storedSessionId })
  } catch (error) {
    // GERİ AL: kip değişmediği hâlde değişmiş görünmek, kullanıcının Chat
    // sandığı bir sohbette modele terminal vermek olurdu.
    write(previous)

    throw error
  }
}
