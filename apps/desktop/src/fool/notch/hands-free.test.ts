import { describe, expect, it } from 'vitest'

import {
  HANDS_FREE_VAD,
  listenOptionsFor,
  MAX_IDLE_ROUNDS,
  modeForActivation,
  nextIdleRounds,
  type RearmInput,
  shouldRearmListening
} from './hands-free'

const base: RearmInput = {
  capturing: false,
  idleRounds: 0,
  mode: 'hands-free',
  sessionActive: true,
  status: 'idle'
}

describe('eller serbest yeniden acma', () => {
  it('tur bitince mikrofonu kendiliginden acar', () => {
    expect(shouldRearmListening(base)).toBe(true)
  })

  it('ajan konusurken ACMAZ', () => {
    // Yanki dongusu: hoparlorden cikan ses kullanici konusmasi saniliyor,
    // ajan kendi cevabini duyup kendine cevap veriyor. Windows'ta yanki
    // bastirma ayni uygulamanin kendi oynatmasini kesmiyor.
    expect(shouldRearmListening({ ...base, status: 'speaking' })).toBe(false)
  })

  it('ajan dusunurken ACMAZ', () => {
    expect(shouldRearmListening({ ...base, status: 'thinking' })).toBe(false)
  })

  it('zaten dinlerken ya da yaziya dokerken ACMAZ', () => {
    expect(shouldRearmListening({ ...base, status: 'listening' })).toBe(false)
    expect(shouldRearmListening({ ...base, status: 'transcribing' })).toBe(false)
  })

  it('oturum kapaliyken ACMAZ', () => {
    expect(shouldRearmListening({ ...base, sessionActive: false })).toBe(false)
  })

  it('araya girme yakalamasi surerken ACMAZ', () => {
    // O yol mikrofonu kendi yonetiyor; ikinci bir getUserMedia akisi
    // Windows'ta kaydi bozuyor.
    expect(shouldRearmListening({ ...base, capturing: true })).toBe(false)
  })

  it('bas-konus kipinde hic acmaz', () => {
    expect(shouldRearmListening({ ...base, mode: 'push-to-talk' })).toBe(false)
  })

  it('art arda sessiz turlardan sonra kendini susturur', () => {
    // Kullanici odadan cikti: kosulsuz yeniden acma mikrofonu sonsuza kadar
    // acik birakirdi.
    expect(shouldRearmListening({ ...base, idleRounds: MAX_IDLE_ROUNDS - 1 })).toBe(true)
    expect(shouldRearmListening({ ...base, idleRounds: MAX_IDLE_ROUNDS })).toBe(false)
  })
})

describe('sessiz tur sayaci', () => {
  it('konusma duyulunca sifirlanir', () => {
    // Birikmis sayac, kullanici geri dondugunde onu bir sonraki
    // sessizlikte erken susturmamali.
    expect(nextIdleRounds(2, true)).toBe(0)
  })

  it('sessizlikte artar', () => {
    expect(nextIdleRounds(1, false)).toBe(2)
  })

  it('sinira gelince susma kararini uretir', () => {
    let rounds = 0

    for (let turn = 0; turn < MAX_IDLE_ROUNDS; turn += 1) {
      expect(shouldRearmListening({ ...base, idleRounds: rounds })).toBe(true)
      rounds = nextIdleRounds(rounds, false)
    }

    expect(shouldRearmListening({ ...base, idleRounds: rounds })).toBe(false)
  })
})

describe('dinleme ayarlari', () => {
  it('eller serbestte CLI ile ayni VAD ayarini verir', () => {
    // Iki yuzeyin farkli esikte susmasi, ayni cumlenin farkli yerde
    // kesilmesi demekti -- tekrar uretilemeyen bir "cumlemi yiyor" hatasi.
    expect(listenOptionsFor('hands-free')).toBe(HANDS_FREE_VAD)
    expect(HANDS_FREE_VAD.silenceLevel).toBe(0.075)
    expect(HANDS_FREE_VAD.silenceMs).toBe(1_250)
  })

  it('bas-konusta sessizlik saptayicisi VERMEZ', () => {
    // Kullanici hala tusu basili tutarken kaydi kapatirdi: cumlenin
    // ortasinda kesilen bir kayit.
    expect(listenOptionsFor('push-to-talk')).toBeUndefined()
  })
})

describe('aktivasyon kipi', () => {
  it('kendiliginden acilan kayit eller serbest kuralini alir', () => {
    expect(modeForActivation('auto')).toBe('hands-free')
    expect(listenOptionsFor(modeForActivation('auto'))).toBe(HANDS_FREE_VAD)
  })

  it('tusla acilan kayit eller serbest OTURUMDA BILE bas-konus kalir', () => {
    // Kip oturumun degil tek bir acilisin ozelligi. Oturum duzeyinde
    // baglamak, tus hala basiliyken sessizlik saptayicisinin kaydi
    // kapatmasi demekti.
    expect(modeForActivation('key')).toBe('push-to-talk')
    expect(listenOptionsFor(modeForActivation('key'))).toBeUndefined()
  })
})
