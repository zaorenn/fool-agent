import { describe, expect, it } from 'vitest'

import {
  advance,
  ATTACK,
  BASE_SCALE,
  createOrbState,
  isHearing,
  MAX_GROWTH,
  RELEASE,
  ringOpacity,
  scaleFor,
  SILENCE_LEVEL
} from './orb-motion'

const FRAME = 16.67

/** ``ms`` boyunca sabit girdiyle ilerlet. */
const run = (input: number, ms: number, state = createOrbState()) => {
  for (let elapsed = 0; elapsed < ms; elapsed += FRAME) {
    advance(state, input, FRAME)
  }

  return state
}

describe('seviye takibi', () => {
  it('sessizlikte sifirda kaliyor', () => {
    expect(run(0, 500).level).toBeCloseTo(0, 3)
  })

  it('sese dogru yukseliyor', () => {
    expect(run(0.8, 500).level).toBeGreaterThan(0.7)
  })

  it('YUKSELIRKEN dusmekten hizli', () => {
    // Simetrik yumusatma yanlis hissettiriyor: konusma baslayinca kure gec
    // tepki veriyor, bitince aniden sonuyor. Insan sesi de boyle degil.
    expect(ATTACK).toBeGreaterThan(RELEASE)

    const rise = run(1, 100).level
    const fall = run(0, 100, run(1, 500)).level

    expect(rise).toBeGreaterThan(1 - fall)
  })

  it('girdi araligin disindaysa kirpiliyor', () => {
    expect(run(5, 300).level).toBeLessThanOrEqual(1)
    expect(run(-3, 300).level).toBeGreaterThanOrEqual(0)
  })

  it('bozuk girdi cokertmiyor', () => {
    for (const bad of [Number.NaN, Infinity, -Infinity]) {
      const state = createOrbState()

      advance(state, bad, FRAME)

      expect(Number.isFinite(state.level)).toBe(true)
    }
  })
})

describe('kare hizindan bagimsizlik', () => {
  it('30 fps ile 60 fps ayni yere variyor', () => {
    // Yumusatma sabiti kare BASINA uygulansaydi animasyon makineye gore
    // degisirdi: yavas makinede yavas, hizlida titrek.
    const fast = createOrbState()
    const slow = createOrbState()

    for (let i = 0; i < 60; i += 1) {
      advance(fast, 1, 16.67)
    }

    for (let i = 0; i < 30; i += 1) {
      advance(slow, 1, 33.33)
    }

    expect(Math.abs(fast.level - slow.level)).toBeLessThan(0.02)
  })

  it('faz GECEN SUREYE bagli, kare sayisina degil', () => {
    const fast = createOrbState()
    const slow = createOrbState()

    for (let i = 0; i < 60; i += 1) {
      advance(fast, 0, 16.67)
    }

    for (let i = 0; i < 30; i += 1) {
      advance(slow, 0, 33.33)
    }

    expect(Math.abs(fast.phase - slow.phase)).toBeLessThan(0.02)
  })

  it('sifir/negatif dt sonsuza gitmiyor', () => {
    const state = createOrbState()

    advance(state, 1, 0)
    advance(state, 1, -50)

    expect(Number.isFinite(state.level)).toBe(true)
    expect(Number.isFinite(state.phase)).toBe(true)
  })
})

describe('olcek', () => {
  it('sessizlikte taban olcekte', () => {
    expect(scaleFor(createOrbState(), 'listening')).toBeCloseTo(BASE_SCALE, 3)
  })

  it('sesle buyuyor ama sinirli', () => {
    const loud = run(1, 800)

    expect(scaleFor(loud, 'listening')).toBeGreaterThan(BASE_SCALE)
    expect(scaleFor(loud, 'listening')).toBeLessThanOrEqual(BASE_SCALE + MAX_GROWTH + 0.001)
  })

  it('DUSUNURKEN ses yok ama kure olmuyor', () => {
    // Model 1-3 saniye uretiyor; donmus bir kure "kilitlendi" gibi duruyor.
    const state = createOrbState()
    const samples = new Set<number>()

    for (let i = 0; i < 40; i += 1) {
      advance(state, 0, 50)
      samples.add(Math.round(scaleFor(state, 'thinking') * 1000))
    }

    expect(samples.size).toBeGreaterThan(3)
  })

  it('BOSTA da hafif nefes aliyor', () => {
    // Tamamen hareketsiz bir kure kapali gorunuyor.
    const state = createOrbState()
    const samples = new Set<number>()

    for (let i = 0; i < 40; i += 1) {
      advance(state, 0, 80)
      samples.add(Math.round(scaleFor(state, 'idle') * 1000))
    }

    expect(samples.size).toBeGreaterThan(3)
  })

  it('bostaki nefes dusunmekten DAHA SESSIZ', () => {
    const state = run(0, 400)
    const idleSpread = Math.abs(scaleFor(state, 'idle') - BASE_SCALE)
    const thinkSpread = Math.abs(scaleFor(state, 'thinking') - BASE_SCALE)

    expect(idleSpread).toBeLessThan(thinkSpread + 0.06)
  })
})

describe('halkalar', () => {
  it('seviye yukseldikce belirginlesiyor', () => {
    const quiet = ringOpacity(createOrbState(), 'listening', 0)
    const loud = ringOpacity(run(1, 800), 'listening', 0)

    expect(loud).toBeGreaterThan(quiet)
  })

  it('dis halkalar daha sonuk', () => {
    const state = run(0.8, 500)

    expect(ringOpacity(state, 'listening', 0)).toBeGreaterThan(ringOpacity(state, 'listening', 2))
  })

  it('opaklik 0..1 disina cikmiyor', () => {
    const state = run(1, 1_000)

    for (let i = 0; i < 4; i += 1) {
      const value = ringOpacity(state, 'speaking', i)

      expect(value).toBeGreaterThanOrEqual(0)
      expect(value).toBeLessThanOrEqual(1)
    }
  })
})

describe('duyuyorum ipucu', () => {
  it('esigin ustunde gorunuyor', () => {
    expect(isHearing(run(0.9, 500), 'listening')).toBe(true)
  })

  it('oda gurultusunde YANIP SONMUYOR', () => {
    // Esik ``HANDS_FREE_VAD`` ile ayni: iki yuzeyin farkli esikte
    // "duyuyorum" demesi kullaniciyi yaniltirdi.
    expect(isHearing(run(SILENCE_LEVEL / 2, 500), 'listening')).toBe(false)
  })

  it('dinlemiyorken hic gorunmuyor', () => {
    const loud = run(1, 500)

    for (const phase of ['idle', 'speaking', 'thinking'] as const) {
      expect(isHearing(loud, phase)).toBe(false)
    }
  })
})
