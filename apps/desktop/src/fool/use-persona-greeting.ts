/**
 * Tanışma selamını GÖNDEREN taraf. Kararı ``persona-greeting.ts`` veriyor.
 *
 * Ana pencerede BİR KEZ takılıyor. Kendiliğinden mesaj gönderen bir uygulama
 * yanlış açtığında en can sıkıcı şey olduğu için kapı dar tutuldu; koşullar ve
 * gerekçeleri karar modülünde yazılı.
 *
 * ``prompt.submit`` DOĞRUDAN çağrılıyor (çentiğin yaptığı gibi), besteci
 * yolundan değil: besteci yolu iyimser bir kullanıcı balonu yaratıyor ve bu
 * metin kullanıcının yazdığı bir şey değil.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { useStore } from '@nanostores/react'
import { useEffect, useRef } from 'react'

import { useGatewayRequest } from '@/app/gateway/hooks/use-gateway-request'
import { COMPANION_BUILD } from '@/fool/companion/build-flag'
import { $activeSessionId, $busy, $messages } from '@/store/session'

import { PERSONA_KICKOFF, shouldGreet } from './persona-greeting'
import { fetchRelationship } from './relationship-bar'

export function usePersonaGreeting(active: boolean): void {
  const sessionId = useStore($activeSessionId) ?? ''
  const messages = useStore($messages)
  const busy = useStore($busy)
  const { requestGateway } = useGatewayRequest()
  // Denenen oturumlar. Atom aynası DEĞİL -- bir kere denendi bilgisi render
  // etmiyor ve etmemeli.
  const attempted = useRef(new Set<string>())

  useEffect(() => {
    // ``active``: yalnizca ana pencerenin BIRINCIL gorunumu. Her sohbet
    // kutucugu ayni bilesenden turuyor ve hepsi ayni kuresel atomlari okuyor;
    // kapisiz kalsaydi acik kutucuk sayisi kadar selam gonderilirdi.
    if (!COMPANION_BUILD || !active || !sessionId || messages.length > 0 || busy || attempted.current.has(sessionId)) {
      return
    }

    let cancelled = false

    void (async () => {
      const snapshot = await fetchRelationship().catch(() => null)

      if (cancelled || !snapshot) {
        return
      }

      // Durum SUNUCUDAN geldiği anda yeniden bakılıyor: bekleme sırasında
      // kullanıcı yazmış ya da tur başlamış olabilir.
      const state = {
        enabled: snapshot.enabled === true,
        met: snapshot.met === true,
        sessionId: $activeSessionId.get() ?? '',
        messageCount: $messages.get().length,
        attempted: attempted.current.has(sessionId),
        busy: $busy.get()
      }

      if (state.sessionId !== sessionId || !shouldGreet(state)) {
        return
      }

      attempted.current.add(sessionId)

      // Sessiz: selam bir ARAÇ değil. Ağ geçidi henüz ayaktayken düşen bir
      // çağrı için kullanıcıya hata göstermek, hiç istemediği bir özelliğin
      // bozulduğunu bildirmek olurdu.
      await requestGateway('prompt.submit', { session_id: sessionId, text: PERSONA_KICKOFF }).catch(
        () => undefined
      )
    })()

    return () => {
      cancelled = true
    }
  }, [active, busy, messages.length, requestGateway, sessionId])
}
