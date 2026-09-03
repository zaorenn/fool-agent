/**
 * Çentiğin "şunu gönder" isteğini ANA PENCEREDE karşılar.
 *
 * Neden bu kanca var
 * ------------------
 * Çentik ağ geçidine DOĞRUDAN ``prompt.submit`` atıyordu ve composer'ın
 * gönderim boru hattını atlıyordu. O boru hattı gönderir göndermez ekrana
 * İYİMSER bir kullanıcı balonu koyuyor
 * (``use-prompt-actions/submit.ts::optimisticId``); çentikten konuşunca o
 * balon hiç çizilmiyordu.
 *
 * Ölçülen sonuç: kullanıcı konuşuyor, mesaj gerçekten gidiyor
 * (``tui prompt accepted: chars=41``), ama ekranda hiçbir şey olmuyor ve model
 * düşünürken -- aynı günlükte ``duration=172.9s`` -- uygulama tamamen ölü
 * görünüyor. Kullanıcının bildirdiği: "söylediklerim sohbete aktarılmıyor...
 * uygulamanın tüm amacının işlevsiz olmasına sebep oluyor."
 *
 * İstenen de buydu: "çentik aynı akışın birebir aynısı, sadece atanan tuş ile
 * bas-konuş hâli olmalı."
 *
 * Artık çentik bir GİRDİ AYGITI: metni yazıyor, göndermeyi ana pencere
 * yapıyor. İyimser balon, oturum hedeflemesi, taslak temizliği ve turun geri
 * kalanı bedavaya geliyor -- çünkü hepsi zaten o yolda.
 *
 * Quick Entry penceresi aynı kararı çoktan vermişti ve gerekçesini de
 * yazmıştı: "One submit pipeline, no bespoke RPC."
 *
 * Neden yalnızca ANA pencere
 * --------------------------
 * Çentik aynı paketi yüklüyor (``?win=notch``), yani bu kanca orada da
 * koşabilirdi -- ve kendi isteğine kendisi cevap verip mesajı İKİ KEZ
 * gönderirdi.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { useEffect, useRef } from 'react'

import { isNotchWindow } from '@/fool/notch/window'

import { $voiceSubmitWanted, parseVoiceSubmit } from './active-session'

export function useVoiceSubmitRequests(submitText: (text: string) => Promise<unknown> | unknown): void {
  const submitRef = useRef(submitText)
  submitRef.current = submitText

  useEffect(() => {
    if (isNotchWindow()) {
      return undefined
    }

    // Aynı isteği iki kez işlemeyi engelliyor: ``subscribe`` açılışta mevcut
    // değeri de veriyor ve depoda duran ESKİ bir istek yeniden gönderilirdi.
    let handled = ''
    let first = true

    const unsubscribe = $voiceSubmitWanted.subscribe(value => {
      const request = parseVoiceSubmit(value)

      if (first) {
        first = false
        // Açılışta duran isteği KARŞILANMIŞ say: kullanıcı o cümleyi çoktan
        // söyledi ve uygulamayı yeniden açmak onu yeniden göndermemeli.
        handled = request?.id ?? ''

        return
      }

      if (!request || request.id === handled) {
        return
      }

      handled = request.id

      void Promise.resolve(submitRef.current(request.text)).catch(() => {
        // Yutuluyor: gönderim boru hattı hatayı kendi yüzeyinde zaten
        // gösteriyor (composer'ın hata satırı). Burada ikinci bir bildirim
        // aynı şeyi iki kez söylemek olurdu.
      })
    })

    return unsubscribe
  }, [])
}
