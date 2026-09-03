/**
 * Sıra yanlış olursa kullanıcının ayarı sessizce yok sayılır: tuşa basar,
 * hiçbir şey olmaz ya da başka bir tuş çalışır ve sebebini göremez.
 */

import { describe, expect, it } from 'vitest'

import { NOTCH_SHORTCUT_CANDIDATES, shortcutOrder } from './notch-shortcut'

describe('notch shortcut order', () => {
  it('kullanicinin istedigi kombinasyon VARSAYILAN ilk aday', () => {
    expect(NOTCH_SHORTCUT_CANDIDATES[0]).toBe('CommandOrControl+Alt+V')
  })

  it('secim HER ZAMAN basta', () => {
    expect(shortcutOrder('CommandOrControl+Shift+J')[0]).toBe('CommandOrControl+Shift+J')
  })

  it('secim merdivende de varsa IKI KEZ denenmiyor', () => {
    // Ikinci deneme ilkinin kendi kaydina takilip "tutulmus" gibi gorunurdu.
    const order = shortcutOrder('F13')

    expect(order.filter(item => item === 'F13')).toHaveLength(1)
    expect(order[0]).toBe('F13')
  })

  it.each([undefined, null, '', '   ', 42, {}])(
    'secim yoksa (%o) merdiven oldugu gibi kosuyor',
    raw => {
      expect(shortcutOrder(raw)).toEqual([...NOTCH_SHORTCUT_CANDIDATES])
    }
  )

  it('bosluklar kirpiliyor', () => {
    expect(shortcutOrder('  F13  ')[0]).toBe('F13')
  })

  it('merdiven her zaman yedek olarak kaliyor', () => {
    // Yalnizca secimi denemek, tutulmus bir tusta kisayolu TUMDEN
    // kaybetmek olurdu.
    expect(shortcutOrder('CommandOrControl+Shift+J').length).toBe(
      NOTCH_SHORTCUT_CANDIDATES.length + 1
    )
  })

  it('donen dizi cagirani ETKILEMIYOR', () => {
    const order = shortcutOrder('')

    order.push('bozuk')

    expect(shortcutOrder('')).not.toContain('bozuk')
  })
})
