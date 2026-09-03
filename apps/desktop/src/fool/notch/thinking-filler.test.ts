import { describe, expect, it } from 'vitest'

import {
  createFillerState,
  FILL_AFTER_MS,
  FILLERS,
  resetTurn,
  shouldFill,
  takeFiller
} from './thinking-filler'

const input = (over: Partial<Parameters<typeof shouldFill>[1]> = {}) => ({
  elapsedMs: FILL_AFTER_MS,
  enabled: true,
  hasSpeechStarted: false,
  interrupted: false,
  ...over
})

describe('doldurma karari', () => {
  it('esige gelince dolduruyor', () => {
    expect(shouldFill(createFillerState(), input())).toBe(true)
  })

  it('kisa bosluk doldurulmuyor', () => {
    // Kisa bir duraklama insan konusmasinda ZATEN var; her turda "hmm"
    // demek bir sure sonra bir tik gibi duyuluyor.
    expect(shouldFill(createFillerState(), input({ elapsedMs: FILL_AFTER_MS - 1 }))).toBe(false)
  })

  it('cevap gelmeye basladiysa doldurulmuyor', () => {
    // Ustune konusmak, kullanicinin duymak istedigi seyi bastirmak olurdu.
    expect(shouldFill(createFillerState(), input({ hasSpeechStarted: true }))).toBe(false)
  })

  it('kullanici araya giriyorsa doldurulmuyor', () => {
    expect(shouldFill(createFillerState(), input({ interrupted: true }))).toBe(false)
  })

  it('kapaliyken hic doldurulmuyor', () => {
    expect(shouldFill(createFillerState(), input({ enabled: false }))).toBe(false)
  })

  it('tur basina EN FAZLA bir kez', () => {
    const state = createFillerState()

    expect(shouldFill(state, input())).toBe(true)
    takeFiller(state)
    expect(shouldFill(state, input({ elapsedMs: 10_000 }))).toBe(false)
  })

  it('yeni turda yeniden doldurulabiliyor', () => {
    const state = createFillerState()

    takeFiller(state)
    resetTurn(state)

    expect(shouldFill(state, input())).toBe(true)
  })
})

describe('sozcuk secimi', () => {
  it('listeden bir sozcuk donuyor', () => {
    expect(FILLERS).toContain(takeFiller(createFillerState()))
  })

  it('arka arkaya AYNI sozcuk gelmiyor', () => {
    // Iki kez ust uste "Mm-hm" duymak, insanla konusmayi taklit etmeye
    // calisan bir makineye benziyor -- olmak istedigimiz seyin tam tersi.
    const state = createFillerState()
    const first = takeFiller(state, () => 0)

    resetTurn(state)
    const second = takeFiller(state, () => 0)

    expect(second).not.toBe(first)
  })

  it('uzun bir dizide de hic tekrar etmiyor', () => {
    const state = createFillerState()
    let previous = ''

    for (let turn = 0; turn < 30; turn += 1) {
      resetTurn(state)
      const said = takeFiller(state)

      expect(said).not.toBe(previous)
      previous = said
    }
  })

  it('sozcukler kisa ve SOZ VERMIYOR', () => {
    // "bir saniye" gibi bir soz verip cevap hemen gelirse yalan soylemis
    // oluyoruz; bunlar yalnizca "buradayim, duydum" demek.
    for (const filler of FILLERS) {
      expect(filler.length).toBeLessThanOrEqual(16)
      expect(filler.toLowerCase()).not.toContain('minute')
      expect(filler.toLowerCase()).not.toContain('moment')
    }
  })

  it('secim durumu isaretliyor', () => {
    const state = createFillerState()

    takeFiller(state)

    expect(state.usedThisTurn).toBe(true)
  })
})
