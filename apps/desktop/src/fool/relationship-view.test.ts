/**
 * Barın sayıya bakan kısmı.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { describe, expect, it } from 'vitest'

import { describeSince, shouldRender, stanceFill, stanceTone, warmthPercent } from './relationship-view'

describe('warmthPercent', () => {
  it('degeri oldugu gibi veriyor', () => {
    expect(warmthPercent(37)).toBe(37)
  })

  it('araligin DISINA tasmiyor', () => {
    // Kirpmadan cizilirse tek bir bozuk deger cubugu kabin disina tasirir.
    expect(warmthPercent(140)).toBe(100)
    expect(warmthPercent(-20)).toBe(0)
  })

  it('deger YOKKEN ortada duruyor', () => {
    expect(warmthPercent(undefined)).toBe(50)
    expect(warmthPercent(Number.NaN)).toBe(50)
  })
})

describe('renk', () => {
  it('sicak ve soguk uclar AYRISIYOR', () => {
    expect(stanceTone('close')).not.toBe(stanceTone('cold'))
    expect(stanceFill('close')).not.toBe(stanceFill('cold'))
  })

  it('bilinmeyen durus notr', () => {
    expect(stanceTone(undefined)).toContain('muted')
  })
})

describe('describeSince', () => {
  const now = 1_700_000_000_000

  const ago = (seconds: number) => describeSince(now / 1000 - seconds, now)

  it('cok yeni', () => {
    expect(ago(5)).toBe('just now')
  })

  it('dakika', () => {
    expect(ago(20 * 60)).toBe('20m ago')
  })

  it('saat', () => {
    expect(ago(5 * 3600)).toBe('5h ago')
  })

  it('gun', () => {
    expect(ago(3 * 86400)).toBe('3d ago')
  })

  it('hafta', () => {
    expect(ago(21 * 86400)).toBe('3w ago')
  })

  it('GELECEK bir damga negatif sayi vermiyor', () => {
    // Saat degisikligi ya da farkli makinede yazilmis bir kayit;
    // "-2h ago" gostermek barin tek isini bozardi.
    expect(describeSince(now / 1000 + 600, now)).toBe('just now')
  })
})

describe('shouldRender', () => {
  it('cevap GELMEDEN cizilmiyor', () => {
    // Acilista bir anlik "Neutral" gostermek, kullanicinin hic yasamadigi
    // bir durumu iddia etmek olurdu.
    expect(shouldRender(null)).toBe(false)
  })

  it('siradan ajanda cizilmiyor', () => {
    expect(shouldRender({ enabled: false })).toBe(false)
  })

  it('persona profilinde ciziliyor', () => {
    expect(shouldRender({ enabled: true, started: false })).toBe(true)
  })
})
