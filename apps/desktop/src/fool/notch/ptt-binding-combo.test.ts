/**
 * Değiştiricili bas-konuş bağlamaları.
 *
 * İstenen: "kullanıcı ayarlardan istediği tuş kombinasyonuyla değiştirebilmeli,
 * sağ Ctrl'ü Shift gibi bir tuşla kombine de edip kaydedebilmeli."
 *
 * Tek tuş her makinede yetmiyor: sağ Ctrl bazı dizüstülerde fiziksel olarak
 * yok, bazılarında IME'ye bağlı. Kullanıcı başka bir tuş seçtiğinde ise TEK
 * tuş çakışıyor -- ``KeyV`` bağlarsan yazarken mikrofon açılır.
 */

import { describe, expect, it } from 'vitest'

import {
  bindingMatches,
  DEFAULT_PTT_CODE,
  formatPttBinding,
  formatPttBindingLabel,
  parsePttBinding
} from './ptt-binding'

describe('parse/format', () => {
  it('degistiricisiz ESKI degerler calismaya devam ediyor', () => {
    // Bu bir bicim genisletmesi, goc degil.
    const b = parsePttBinding('ControlRight')

    expect(b.code).toBe('ControlRight')
    expect(b.ctrl || b.alt || b.shift || b.meta).toBe(false)
    expect(formatPttBinding(b)).toBe('ControlRight')
  })

  it('kombo cozuluyor ve ayni dizeye geri yaziliyor', () => {
    const b = parsePttBinding('Shift+ControlRight')

    expect(b.code).toBe('ControlRight')
    expect(b.shift).toBe(true)
    expect(formatPttBinding(b)).toBe('Shift+ControlRight')
  })

  it('degistirici SIRASI sabit', () => {
    // Ayni baglamanin iki farkli dize olarak saklanmasi, karsilastirmayi
    // sessizce basarisiz yapardi.
    expect(formatPttBinding(parsePttBinding('Shift+Alt+KeyV'))).toBe(
      formatPttBinding(parsePttBinding('Alt+Shift+KeyV'))
    )
  })

  it('BOZUK deger varsayilana dusuyor', () => {
    for (const bad of ['', 'Escape', 'Shift+Escape', 'Shift+', '???', null, 42]) {
      expect(parsePttBinding(bad).code).toBe(DEFAULT_PTT_CODE)
    }
  })
})

describe('eslesme', () => {
  const shiftRightCtrl = parsePttBinding('Shift+ControlRight')
  const plainRightCtrl = parsePttBinding('ControlRight')
  const shiftV = parsePttBinding('Shift+KeyV')

  it('kombo YALNIZCA degistirici basiliyken esliyor', () => {
    expect(bindingMatches(shiftRightCtrl, { code: 'ControlRight', shiftKey: true })).toBe(true)
    expect(bindingMatches(shiftRightCtrl, { code: 'ControlRight', shiftKey: false })).toBe(false)
  })

  it('FAZLADAN degistirici esleseni bozuyor', () => {
    // ``ControlRight`` bagliyken Shift'e basili yazarken mikrofon acilmamali.
    expect(bindingMatches(plainRightCtrl, { code: 'ControlRight', shiftKey: true })).toBe(false)
    expect(bindingMatches(plainRightCtrl, { code: 'ControlRight', shiftKey: false })).toBe(true)
  })

  it('baglamanin KENDI degistiricisi fazladan sayilmiyor', () => {
    // ControlRight'a basmak ctrlKey'i zaten true yapiyor. Bunu "fazladan"
    // saymak baglamayi hic eslesmez hale getirirdi.
    expect(bindingMatches(plainRightCtrl, { code: 'ControlRight', ctrlKey: true })).toBe(true)
    expect(bindingMatches(shiftRightCtrl, { code: 'ControlRight', ctrlKey: true, shiftKey: true })).toBe(true)
  })

  it('BASKA tus esleşmiyor', () => {
    expect(bindingMatches(shiftV, { code: 'KeyB', shiftKey: true })).toBe(false)
    expect(bindingMatches(shiftV, { code: 'KeyV', shiftKey: true })).toBe(true)
    expect(bindingMatches(shiftV, { code: 'KeyV', shiftKey: false })).toBe(false)
  })
})

describe('etiket', () => {
  it('insan okur bicimde', () => {
    expect(formatPttBindingLabel(parsePttBinding('Shift+ControlRight'))).toBe('Shift + Right Ctrl')
    expect(formatPttBindingLabel(parsePttBinding('ControlRight'))).toBe('Right Ctrl')
  })
})
