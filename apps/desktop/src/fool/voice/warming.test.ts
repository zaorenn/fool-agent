import { describe, expect, it } from 'vitest'

import { isWarming, WARMING_AFTER_MS, warmingLabel } from './warming'

describe('uyaniyor gostergesi', () => {
  it('esigin ustunde gorunuyor', () => {
    expect(isWarming({ elapsedMs: WARMING_AFTER_MS, preparing: true })).toBe(true)
  })

  it('ISINMIS motorda gorunmuyor', () => {
    // Olculdu: isinmis sentez 0,17-2,49 sn. Her turda "yukleniyor" demek
    // gurultu olurdu.
    expect(isWarming({ elapsedMs: 300, preparing: true })).toBe(false)
  })

  it('hazirlik bitmisse gorunmuyor', () => {
    expect(isWarming({ elapsedMs: 60_000, preparing: false })).toBe(false)
  })

  it('esik soguk yukleme ile isinmis sentezi AYIRIYOR', () => {
    // Soguk yukleme 4,67 sn'den basliyor (piper), isinmis en yavas 2,49 sn
    // (kyutai). Esik ikisinin arasinda olmali.
    expect(WARMING_AFTER_MS).toBeGreaterThan(0)
    expect(WARMING_AFTER_MS).toBeLessThan(4_670)
  })
})

describe('gosterilen satir', () => {
  it('MOTOR ADINI soyluyor', () => {
    // "Yukleniyor" tek basina hangi seyin yuklendigini soylemiyor ve
    // kullanici yanlis yerde sorun ariyor.
    expect(warmingLabel('StyleTTS 2')).toContain('StyleTTS 2')
  })

  it('BIR KEZ oldugunu soyluyor', () => {
    // Yoksa her turda bekleyecegini sanir.
    expect(warmingLabel('kokoro')).toContain('once per session')
  })

  it('motor adi bilinmiyorsa yine anlamli', () => {
    expect(warmingLabel('')).toContain('the voice')
    expect(warmingLabel('   ')).not.toContain('  —')
  })
})

/**
 * Uyarı BİR KEZ çıkmalı — etiketin kendisi öyle diyor.
 *
 * Ölçüt yalnızca "hazırlık 1,2 sn'yi geçti mi"ydi. Chatterbox SICAKKEN bile
 * hazırlık o eşiği aşabiliyor (sıcak sentez 0,78 sn + akış kurulumu), yani
 * uyarı HER mesajda çıkıyordu: "her mesajda sürekli waking chatterbox diyor".
 *
 * Günlüklerde motorun tekrar tekrar durdurulduğuna dair KAYIT YOK -- motor
 * açıktı, etiket yalan söylüyordu.
 */
describe('uyari bir kez', () => {
  it('motor DAHA ONCE konustuysa uyari YOK', () => {
    expect(isWarming({ elapsedMs: 9_000, preparing: true, spokeBefore: true })).toBe(false)
  })

  it('ILK kez konusurken uyari VAR', () => {
    expect(isWarming({ elapsedMs: 9_000, preparing: true, spokeBefore: false })).toBe(true)
  })

  it('bayrak verilmezse eski davranis', () => {
    expect(isWarming({ elapsedMs: 9_000, preparing: true })).toBe(true)
  })

  it('konusmus motorda esik ne olursa olsun susuyor', () => {
    for (const elapsed of [0, 1_200, 60_000]) {
      expect(isWarming({ elapsedMs: elapsed, preparing: true, spokeBefore: true })).toBe(false)
    }
  })
})
