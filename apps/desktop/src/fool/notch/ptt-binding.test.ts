import { describe, expect, it } from 'vitest'

import { DEFAULT_PTT_CODE, formatPttCode, isBindableCode, sanitizePttCode } from './ptt-binding'

describe('baglanabilir tus', () => {
  it('varsayilan sag Ctrl', () => {
    expect(DEFAULT_PTT_CODE).toBe('ControlRight')
    expect(isBindableCode(DEFAULT_PTT_CODE)).toBe(true)
  })

  it('sira disi ama gecerli tuslari kabul eder', () => {
    // Sag Ctrl'si olmayan dizustulerde kullanicinin secebilecegi seyler.
    for (const code of ['ContextMenu', 'CapsLock', 'F13', 'AltRight', 'KeyQ']) {
      expect(isBindableCode(code)).toBe(true)
    }
  })

  it('kacis yollarini baglamaya izin vermez', () => {
    // Escape/Tab baglanirsa kullanici baglamayi geri almak icin tam o
    // tuslara ihtiyac duyar; Enter/Space yeniden baglama duğmesini
    // etkinlestiren tuslar -- yakalama acilir acilmaz kendilerini yakalarlardi.
    for (const code of ['Escape', 'Tab', 'Enter', 'NumpadEnter', 'Space']) {
      expect(isBindableCode(code)).toBe(false)
    }
  })

  it('bicimsiz degerleri reddeder', () => {
    for (const code of ['', ' ', 'Control Right', '1Key', null, undefined, 42, {}]) {
      expect(isBindableCode(code)).toBe(false)
    }
  })
})

describe('saklanan degeri guvene alma', () => {
  it('gecerli degeri korur', () => {
    expect(sanitizePttCode('ContextMenu')).toBe('ContextMenu')
  })

  it('bozuk degeri varsayilana dusurur', () => {
    // localStorage kullanicinin elinde: elle duzenlenmis ya da eski surumden
    // kalmis bir deger bas-konusu sessizce olu birakirdi.
    for (const raw of ['', 'Escape', 'not a code', null, 7, ['ControlRight']]) {
      expect(sanitizePttCode(raw)).toBe(DEFAULT_PTT_CODE)
    }
  })
})

describe('kullaniciya gosterilen ad', () => {
  it('bilinen tuslari insan diline cevirir', () => {
    // 'ControlRight' bir tanimlayici, arayuz metni degil.
    expect(formatPttCode('ControlRight')).toBe('Right Ctrl')
    expect(formatPttCode('ContextMenu')).toBe('Menu')
  })

  it('harf ve rakam tuslarinin onekini atar', () => {
    expect(formatPttCode('KeyQ')).toBe('Q')
    expect(formatPttCode('Digit7')).toBe('7')
  })

  it('tanimadigini oldugu gibi gosterir', () => {
    expect(formatPttCode('F13')).toBe('F13')
  })
})
