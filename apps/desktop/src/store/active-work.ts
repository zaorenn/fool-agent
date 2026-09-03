/**
 * Mirror of "which chats are mid-turn" to the main process.
 *
 * The renderer is the only side that knows a turn is in flight, and the main
 * process is the only side that can intercept a quit. This module bridges the
 * two: it publishes a small summary on every membership change, and
 * `electron/quit-guard.ts` turns that into the confirmation dialog.
 *
 * Imported for its side effect from `main.tsx`, alongside `store/translucency`.
 */

import { computed } from 'nanostores'

import type { FoolActiveWork } from '@/global'
import { $sessions } from '@/store/session'
import { $workingSessionIds } from '@/store/session-states'

import { whenMainWindow } from './main-window-only'

const $activeWork = computed([$workingSessionIds, $sessions], (workingIds, sessions): FoolActiveWork => {
  const titleById = new Map(sessions.map(session => [session.id, session.title?.trim() ?? '']))

  return {
    count: workingIds.length,
    titles: workingIds.map(id => titleById.get(id) ?? '').filter(Boolean)
  }
})

// FOOL-SEAM: voice-session-bridge
//
// Centik AYRI bir pencere ve kendi ``$activeSessionId``i hic dolmuyor. Ses
// oraya ``null`` gonderiyordu ve ag gecidi mesaji kendi sectigi bir oturuma
// dusuruyordu -- kullanicinin gordugu "mesajlar once bots kisminda cikiyor".
//
// Bu modul zaten ana pencerede yan etki olarak yukleniyor (``main.tsx``), yani
// koprunun dogal yeri burasi.
if (typeof window !== 'undefined') {
  whenMainWindow(() => {
    // YALNIZCA ana pencere yayinliyor.
    //
    // Centik AYNI bundle'i yukluyor (``?win=notch``), yani bu modul orada da
    // kosuyor. Guard olmadan centik kendi BOS ``$activeSessionId``ini
    // paylasilan atoma yaziyor ve ana pencerenin degerini EZIYOR -- kopru
    // kendi kendini bozuyordu. Sonucu kullanicinin gordugu sey: ses yine
    // yanlis oturuma gidiyor ve cevap bot panelinde cikiyor.
    // ODAKTAKI yuzey yayinlaniyor, calisma alani bolmesi DEGIL.
    //
    // Onceden ``$activeSessionId`` oldugu gibi yayinlaniyordu ve o, calisma
    // alani bolmesinin oturumu. Kullanici baska bir sekmeye/kutucuga gecince
    // ses HALA eski oturuma gidiyordu; yeni acilmis, henuz baslamamis bir
    // sohbette ise bir oncekinin kimligi yayinda kaliyor ve mesaj oraya
    // dusuyordu. Kullanicinin bildirdigi: "notch her zaman odaktaki sessiona
    // bagli olmali."
    //
    // HUD ayni tuzaga dusmus, ogrenmis ve kendi cozumleyicisini yazmisti
    // (``app/hud/handoff.ts``). Ders kardesine gecmemisti; cevap artik
    // ``store/focused-session.ts``te ve iki taraf da oradan okuyor.
    void import('@/store/session').then(({ $activeSessionId, $selectedStoredSessionId }) =>
      Promise.all([
        import('@/fool/notch/active-session'),
        import('@/store/focused-session'),
        import('@/store/session-states')
      ]).then(([{ $voiceSessionId }, { focusedRuntimeSessionId }, { $sessionTiles }]) => {
        // Yalnizca DEGISIMDE yaziliyor: ayni degeri yeniden yayinlamak
        // pencereler arasi atomu her odak olayinda dolduracakti.
        const publish = () => {
          const next = focusedRuntimeSessionId()

          if ($voiceSessionId.get() !== next) {
            $voiceSessionId.set(next)
          }
        }

        // UC girdi de odagi degistirebiliyor ve ucu de dinleniyor:
        //   * oturum atomlari -- sohbet acma/kapama, devam ettirme
        //   * kutucuk dizisi   -- bir kutucuk canli oturumuna baglandiginda
        //   * ``focusin``      -- sekme/kutucuk arasi gecis; besteci odak
        //                         yolu bir atom DEGIL, o yuzden tek reaktif
        //                         sinyal bu (bkz. ``markActiveComposer``).
        $activeSessionId.subscribe(publish)
        $selectedStoredSessionId.subscribe(publish)
        $sessionTiles.subscribe(publish)
        window.addEventListener('focusin', publish)

        publish()
      })
    )
  })
}

if (typeof window !== 'undefined') {
  // FOOL-SEAM: main-window-only-publisher
  //
  // YALNIZCA ana pencere yayinliyor.
  //
  // Centik AYNI bundle'i yukluyor (``?win=notch``) ve bu modul orada da
  // kosuyor. Centikte ``$sessions`` bos, yani o da ``count: 0`` yayinliyor ve
  // ana pencerenin ozetini EZIYOR -- son yazan kazaniyor. Bedeli iki yerde:
  // cikis muhafizi suren bir turu gormuyor, ve ``electron/stream-throttle.ts``
  // pencereleri akis ortasinda yeniden kisiyor.
  //
  // Ayni tuzak oturum koprusunde de yasandi (bkz. ``$voiceSessionId``): ses
  // yanlis oturuma gidip cevap bot panelinde cikiyordu.
  // `$sessions` republishes on unrelated churn (previews, heartbeats), so only
  // send when the summary itself moved — this crosses a process boundary.
  let lastSent = ''

  whenMainWindow(() =>
    $activeWork.subscribe(work => {

      const next = JSON.stringify(work)

      if (next === lastSent) {
        return
      }

      lastSent = next
      window.foolDesktop?.setActiveWork?.(work)
    })
  )
}
