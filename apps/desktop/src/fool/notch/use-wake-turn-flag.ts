/**
 * Uyandırma turunu ANA PENCEREYE bildir.
 *
 * Çentik turu biliyor, dinleyicinin kirası ana pencerede -- neden böyle
 * ayrıldığı ``active-session.ts::$wakeTurnActive`` başlığında.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { useCallback, useEffect, useState } from 'react'

import { setWakeTurnActive } from './active-session'
import type { NotchStatus } from './use-notch-voice'
import { WAKE_TURN_START_GRACE_MS, wakeTurnStep } from './wake-turn'

/**
 * Turu izle; bittiğinde bayrağı indir. Dönen çağrı turu BAŞLATIR.
 */
export function useWakeTurnFlag(status: NotchStatus): () => void {
  const [armed, setArmed] = useState(false)
  const [seenActive, setSeenActive] = useState(false)

  const end = useCallback(() => {
    setArmed(false)
    setSeenActive(false)
    setWakeTurnActive(false)
  }, [])

  useEffect(() => {
    if (!armed) {
      return
    }

    const step = wakeTurnStep(seenActive, status)

    if (step === 'running') {
      // Tur gerçekten başladı: bundan sonra ``idle`` BİTTİ demek.
      if (!seenActive) {
        setSeenActive(true)
      }

      return
    }

    if (step === 'ended') {
      end()

      return
    }

    // Hiç başlayamamış olabilir (mikrofon açılmadı). Mühlet dolarsa bayrağı
    // indiriyoruz: takılı bırakmak kulağı kalıcı olarak sağır ederdi.
    const timer = setTimeout(end, WAKE_TURN_START_GRACE_MS)

    return () => clearTimeout(timer)
  }, [armed, end, seenActive, status])

  // Çentik gidiyorsa tur da bitti -- bayrağı arkamızda bırakmıyoruz.
  useEffect(() => () => setWakeTurnActive(false), [])

  return useCallback(() => {
    setSeenActive(false)
    setArmed(true)
    setWakeTurnActive(true)
  }, [])
}
