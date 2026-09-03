import { describe, expect, it } from 'vitest'

import {
  createPttSpeechState,
  observeLevel,
  PTT_SPEECH_LEVEL,
  PTT_SPEECH_LEVEL_PLAYING,
  PTT_SPEECH_SUSTAIN_MS
} from './ptt-speech'

/** Bir dizi örneği besle; ``true`` dönen ilk anın zamanını ver. */
function feed(samples: { level: number; playing?: boolean }[], step = 45): null | number {
  const state = createPttSpeechState()
  let now = 0

  for (const sample of samples) {
    if (observeLevel(state, { level: sample.level, now, playing: sample.playing ?? false })) {
      return now
    }

    now += step
  }

  return null
}

describe('tusa basmak YETMEZ -- konusulmasi gerekiyor', () => {
  it('sessizlikte hic tetiklenmiyor', () => {
    expect(feed(Array.from({ length: 40 }, () => ({ level: 0.01 })))).toBeNull()
  })

  it('tek bir sicrama tetiklemiyor -- klavye tikirtisi, oksuruk', () => {
    expect(feed([{ level: 0.01 }, { level: 0.9 }, { level: 0.01 }, { level: 0.02 }])).toBeNull()
  })

  it('SUREKLI konusma tetikliyor', () => {
    const at = feed(Array.from({ length: 20 }, () => ({ level: 0.3 })))

    expect(at).not.toBeNull()
    expect(at).toBeGreaterThanOrEqual(PTT_SPEECH_SUSTAIN_MS)
  })

  it('esigin altina dusunce sayac SIFIRLANIYOR', () => {
    // Ikiser ornek yuksek, arada dusuk: hicbiri sureyi tamamlamiyor.
    const samples = []

    for (let i = 0; i < 10; i += 1) {
      samples.push({ level: 0.3 }, { level: 0.3 }, { level: 0.01 })
    }

    expect(feed(samples)).toBeNull()
  })

  it('yalnizca BIR kez tetikliyor', () => {
    const state = createPttSpeechState()
    let fired = 0

    for (let now = 0; now <= 900; now += 45) {
      if (observeLevel(state, { level: 0.3, now, playing: false })) {
        fired += 1
      }
    }

    expect(fired).toBe(1)
  })
})

describe('oynatma surerken esik YUKSEK -- hoparlor sizintisi tetiklemesin', () => {
  it('sizinti duzeyindeki ses oynatma sirasinda tetiklemiyor', () => {
    // Sessiz esigi gecen ama oynatma esiginin altinda kalan bir seviye.
    const bleed = (PTT_SPEECH_LEVEL + PTT_SPEECH_LEVEL_PLAYING) / 2

    expect(feed(Array.from({ length: 30 }, () => ({ level: bleed, playing: true })))).toBeNull()
    // Ayni seviye SESSIZKEN konusma sayiliyor.
    expect(feed(Array.from({ length: 30 }, () => ({ level: bleed, playing: false })))).not.toBeNull()
  })

  it('gercek konusma oynatma sirasinda da tetikliyor', () => {
    expect(feed(Array.from({ length: 30 }, () => ({ level: 0.5, playing: true })))).not.toBeNull()
  })
})
