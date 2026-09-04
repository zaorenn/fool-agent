/**
 * Çevirinin sessiz başarısızlığı en kötü sonuç: kullanıcı tuşa basıyor,
 * hiçbir şey olmuyor, sebebini göremiyor. Testler geçersiz girdinin "" (yani
 * "kaydetme") döndüğünü tutuyor.
 */

import { describe, expect, it } from 'vitest'

import { acceleratorKey, DEFAULT_NOTCH_SHORTCUT, formatAccelerator, toAccelerator } from './shortcut-accelerator'

const chord = (over: Partial<Parameters<typeof toAccelerator>[0]>) =>
  toAccelerator({ alt: false, code: 'KeyV', ctrl: false, meta: false, shift: false, ...over })

describe('accelerator', () => {
  it('kullanicinin istedigi kombinasyon varsayilan', () => {
    expect(DEFAULT_NOTCH_SHORTCUT).toBe('CommandOrControl+Alt+V')
  })

  it('Ctrl+Alt+V dogru cevriliyor', () => {
    expect(chord({ alt: true, ctrl: true })).toBe('CommandOrControl+Alt+V')
  })

  it('Shift de tasiniyor', () => {
    expect(chord({ ctrl: true, shift: true })).toBe('CommandOrControl+Shift+V')
  })

  it('Meta ile Ctrl AYNI ada dusuyor -- ayni ayar iki platformda calissin', () => {
    expect(chord({ alt: true, meta: true })).toBe('CommandOrControl+Alt+V')
  })

  it('DEGISTIRICISIZ tus reddediliyor', () => {
    // Yoksa kullanici hicbir metin kutusuna ``v`` yazamaz hale gelirdi.
    expect(chord({})).toBe('')
  })

  it('islev tuslari tek basina KABUL ediliyor', () => {
    expect(toAccelerator({ alt: false, code: 'F13', ctrl: false, meta: false, shift: false })).toBe('F13')
  })

  it.each(['ControlLeft', 'AltRight', 'ShiftLeft', 'MetaLeft'])('tek basina degistirici (%s) kisayol olamaz', code => {
    expect(chord({ code, ctrl: true })).toBe('')
  })

  it('bilinmeyen kod OLDUGU GIBI gecirilmiyor', () => {
    // Electron onu reddeder ve kullanici ayarin neden uygulanmadigini goremez.
    expect(chord({ code: 'MediaTrackNext', ctrl: true })).toBe('')
  })

  it.each([
    ['KeyA', 'A'],
    ['Digit7', '7'],
    ['F5', 'F5'],
    ['Space', 'Space'],
    ['Semicolon', ';'],
    ['ArrowUp', 'Up']
  ])('%s -> %s', (code, expected) => {
    expect(acceleratorKey(code)).toBe(expected)
  })

  it('gosterim okunabilir', () => {
    expect(formatAccelerator('CommandOrControl+Alt+V')).toMatch(/\+ Alt \+ V$/)
    expect(formatAccelerator('')).toBe('Not set')
  })
})
