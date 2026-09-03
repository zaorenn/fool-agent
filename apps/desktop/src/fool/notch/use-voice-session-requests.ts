/**
 * Çentiğin "bana bir sohbet aç" isteğini ANA PENCEREDE karşılar.
 *
 * Ölçülen davranış: kullanıcı giriş ekranındayken bas-konuşa basıyor,
 * konuşuyor ve çentik "No chat is open yet — open one in the main window"
 * diyor. Mesaj DOĞRUYDU: açık oturum gerçekten yoktu. Yanlış olan davranıştı —
 * bas-konuşun bütün amacı, önce pencereye gidip sohbet açmadan konuşabilmek.
 *
 * Oturumu kuran taraf ana pencere: arka uç oturumunu o açıyor ve kimliğini
 * ``$voiceSessionId``e o yayınlıyor. Çentik yalnızca isteyebiliyor. Bu kanca
 * o isteği dinliyor.
 *
 * Neden yalnızca ANA pencere
 * --------------------------
 * Çentik aynı paketi yüklüyor (``?win=notch``), yani bu kanca orada da
 * koşabilirdi -- ve kendi isteğine kendisi cevap verip ikinci bir oturum
 * açardı. ``whenMainWindow`` ile aynı gerekçe (bkz. ``store/main-window-only``).
 *
 * Neden AÇIK oturum varken hiçbir şey yapmıyor
 * --------------------------------------------
 * İstek, oturum yokken gelen bir çağrı. Varken de açsaydı, kullanıcının
 * konuştuğu sohbetin yanına boş bir tane daha açılırdı -- ve deposunda tam
 * olarak bunun izi vardı: sıfır mesajlı oturumlar.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { useEffect } from 'react'

import { isNotchWindow } from '@/fool/notch/window'
import { $activeSessionId } from '@/store/session'

import { $voiceSessionWanted } from './active-session'

export function useVoiceSessionRequests(openSession: () => Promise<unknown> | unknown): void {
  useEffect(() => {
    if (isNotchWindow()) {
      return undefined
    }

    let busy = false

    // ``listen`` DEĞİL ``subscribe``: nanostores'ta ikincisi mevcut değeri de
    // hemen veriyor. Burada istenen tam tersi -- açılışta duran ESKİ bir istek
    // damgası yeni bir oturum açmamalı, o istek çoktan karşılanmış olabilir.
    // O yüzden ilk çağrı yutuluyor.
    let first = true

    const unsubscribe = $voiceSessionWanted.subscribe(value => {
      if (first) {
        first = false

        return
      }

      if (!value || busy || $activeSessionId.get()) {
        return
      }

      busy = true

      void Promise.resolve(openSession()).finally(() => {
        busy = false
      })
    })

    return unsubscribe
  }, [openSession])
}
