/**
 * Kombo bağlama UÇTAN UCA bağlı mı?
 *
 * Mantık (``ptt-binding.ts``) çalışıyordu ama HİÇBİR YERE bağlı değildi:
 * ayar paneli tek tuş yakalıyor, depo kombo dizesini varsayılana düşürüyor,
 * ana süreç ``'ControlRight'``e sabitlenmiş yönlendiriyordu. Yani kullanıcı
 * ``Shift + Sağ Ctrl`` atayamıyor, atasa bile saklanmıyor, saklansa bile
 * odak dışında hiç ulaşmıyordu.
 *
 * Bu dosya o üç dikişi ayrı ayrı tutuyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { captureKeyDown, createBindingCapture, formatPttBinding, parsePttBinding } from './ptt-binding'
import { createPushToTalkState, MIN_HOLD_MS, onKeyDown, onKeyUp } from './push-to-talk'

describe('yakalama -- ayarlardaki "Rebind"', () => {
  it('TEK BASINA degistirici HENUZ tamam degil', () => {
    // Hemen baglasaydik kombo HIC kurulamazdi: kullanici Shift'e basar
    // basmaz yakalama kapanir, ikinci tusa sira gelmezdi.
    const capture = captureKeyDown({ code: 'ShiftLeft', shiftKey: true })

    expect(capture?.complete).toBe(false)
    expect(formatPttBinding(capture!.binding)).toBe('ShiftLeft')
  })

  it('degistirici BASILIYKEN gelen tus komboyu TAMAMLIYOR', () => {
    // Kullanicinin istedigi tam olarak bu: Shift'i tut, sag Ctrl'ye bas.
    const capture = captureKeyDown({ code: 'ControlRight', ctrlKey: true, shiftKey: true })

    expect(capture?.complete).toBe(true)
    expect(formatPttBinding(capture!.binding)).toBe('Shift+ControlRight')
  })

  it('tusun KENDI ailesi degistirici sayilmiyor', () => {
    // ``ControlRight``e basmak ``ctrlKey``i zaten true yapiyor. Saymak
    // ``Ctrl+ControlRight`` uretirdi -- hicbir olayla eslesmeyen bir baglama.
    const capture = captureKeyDown({ code: 'ControlRight', ctrlKey: true })

    expect(formatPttBinding(capture!.binding)).toBe('ControlRight')
    expect(capture?.complete).toBe(false)
  })

  it('duz tus TEK BASINA tamam', () => {
    expect(captureKeyDown({ code: 'F13' })?.complete).toBe(true)
  })

  it('BAGLANAMAYAN tus yok sayiliyor', () => {
    for (const code of ['Escape', 'Tab', 'Enter', 'Space', '']) {
      expect(captureKeyDown({ code })).toBeNull()
    }
  })
})

describe('durum makinesi komboyu goruyor', () => {
  const HELD = 'Shift+ControlRight'

  it('degistirici BASILI degilse basis SAYILMIYOR', () => {
    const state = createPushToTalkState()

    expect(onKeyDown(state, { code: 'ControlRight', ctrlKey: true }, 0, HELD)).toBeNull()
  })

  it('kombo eslesince kayit basliyor', () => {
    const state = createPushToTalkState()

    expect(onKeyDown(state, { code: 'ControlRight', ctrlKey: true, shiftKey: true }, 0, HELD)).toEqual({
      type: 'start'
    })
  })

  it('SHIFT ONCE birakilsa bile kayit KAPANIYOR', () => {
    // En sinsi hata bu olurdu: kullanici Shift'i once birakiyor, sonra
    // ControlRight'in keyup'i ``shiftKey: false`` ile geliyor. Tam eslesme
    // istemek o olayi elerdi ve mikrofon SONSUZA KADAR acik kalirdi.
    const state = createPushToTalkState()

    onKeyDown(state, { code: 'ControlRight', ctrlKey: true, shiftKey: true }, 0, HELD)

    expect(onKeyUp(state, { code: 'ControlRight', shiftKey: false }, MIN_HOLD_MS + 1, HELD)).toEqual({
      heldMs: MIN_HOLD_MS + 1,
      type: 'commit'
    })
  })

  it('ESKI degerler calismaya devam ediyor', () => {
    const state = createPushToTalkState()

    expect(onKeyDown(state, { code: 'ControlRight', ctrlKey: true }, 0, 'ControlRight')).toEqual({
      type: 'start'
    })
  })
})

describe('yakalama SIRASI -- gercek tus dizileri', () => {
  it('Shift bas -> sag Ctrl bas = kombo', () => {
    // Kullanicinin birebir istedigi dizi.
    const capture = createBindingCapture()

    expect(capture.down({ code: 'ShiftLeft', shiftKey: true })?.complete).toBe(false)

    const done = capture.down({ code: 'ControlRight', ctrlKey: true, shiftKey: true })

    expect(done?.complete).toBe(true)
    expect(formatPttBinding(done!.binding)).toBe('Shift+ControlRight')
  })

  it('degistirici TEK BASINA birakilinca tek tus baglaniyor', () => {
    // Duz ``ControlRight`` atamak eskisi gibi calismaya devam etmeli.
    const capture = createBindingCapture()

    capture.down({ code: 'ControlRight', ctrlKey: true })

    const done = capture.up({ code: 'ControlRight' })

    expect(done && formatPttBinding(done)).toBe('ControlRight')
  })

  it('kombo TAMAMLANDIKTAN sonra birakma bir sey baglamiyor', () => {
    // Aksi halde Shift birakilinca baglama ``ShiftLeft``e geri donerdi:
    // kullanici komboyu kurar, parmagini kaldirir ve ayari kaybederdi.
    const capture = createBindingCapture()

    capture.down({ code: 'ShiftLeft', shiftKey: true })
    capture.down({ code: 'ControlRight', ctrlKey: true, shiftKey: true })

    expect(capture.up({ code: 'ShiftLeft' })).toBeNull()
    expect(capture.up({ code: 'ControlRight' })).toBeNull()
  })

  it('BASKA tusun birakilmasi bekleyeni baglamiyor', () => {
    const capture = createBindingCapture()

    capture.down({ code: 'ShiftLeft', shiftKey: true })

    expect(capture.up({ code: 'KeyA' })).toBeNull()
  })

  it('BAGLANAMAZ tus null donuyor -- olay YUTULMUYOR', () => {
    // ``Tab`` yakalamanin icinde de kullanicinin kacis yolu. ``down`` bunu
    // ayirt edemezse arayuz onu yutar ve kullanici panelde kilitlenir.
    const capture = createBindingCapture()

    expect(capture.down({ code: 'Tab' })).toBeNull()
    expect(capture.down({ code: 'Enter' })).toBeNull()
  })

  it('bekleyen varken BAGLANAMAZ tus bekleyeni BOZMUYOR', () => {
    const capture = createBindingCapture()

    capture.down({ code: 'ShiftLeft', shiftKey: true })
    capture.down({ code: 'Tab' })

    const done = capture.up({ code: 'ShiftLeft' })

    expect(done && formatPttBinding(done)).toBe('ShiftLeft')
  })
})

// ---------------------------------------------------------------------------
// Dikisler: kaynakta duruyorlar mi?
// ---------------------------------------------------------------------------

const read = (...parts: string[]) => readFileSync(join(__dirname, ...parts), 'utf8')

describe('dikisler bagli', () => {
  it('depo kombo dizesini SAKLIYOR', () => {
    // ``sanitizePttCode`` komboyu tanimiyor ve varsayilana dusururdu: kullanici
    // kaydeder, panel bir sonraki acilista yine "Right Ctrl" gosterirdi.
    const store = read('ptt-store.ts')

    expect(store).toContain('formatPttBinding(parsePttBinding(raw))')
    expect(store).not.toContain('decode: raw => sanitizePttCode(raw)')
  })

  it('ayar paneli KOMBO yakaliyor', () => {
    const settings = read('..', 'voice-settings.tsx')

    expect(settings).toContain('createBindingCapture')
    // Tek tus yakalayan eski yol geri gelirse burasi duser.
    expect(settings).not.toContain('$pttCode.set(event.code)')
  })

  it('ana surec baglamayi RENDERERDAN ogreniyor', () => {
    // Sabit ``'ControlRight'`` suzgeci, kullanicinin yeniden bagladigi tusu
    // odak disinda hic gecirmiyordu -- ve odak ilk cevap cizilir cizilmez
    // ana pencereye geciyor.
    const main = read('..', '..', '..', 'electron', 'main.ts')
    const forward = main.slice(main.indexOf('function installPushToTalkForwarding'))

    expect(forward.slice(0, 1200)).toContain('input.code !== pushToTalkCode')
    expect(main).toContain("ipcMain.handle('fool:notch:set-ptt'")
  })

  it('iletilen olay DEGISTIRICILERI tasiyor', () => {
    // Tasimazsa kombo baglamalar odak disinda HIC eslesmezdi.
    const main = read('..', '..', '..', 'electron', 'main.ts')
    const send = main.slice(main.indexOf("send('fool:notch:ptt'"))

    for (const field of ['altKey:', 'ctrlKey:', 'metaKey:', 'shiftKey:']) {
      expect(send.slice(0, 600)).toContain(field)
    }
  })

  it('centik sentetik olayda kombo dizesini CODE diye vermiyor', () => {
    // ``code: pttCode`` ile ``Shift+ControlRight`` bir ``code`` sanilirdi ve
    // hicbir olayla eslesmezdi.
    const shell = read('notch-shell.tsx')

    expect(shell).toContain('code: parsePttBinding(pttCode).code')
    expect(shell).not.toMatch(/^\s+code: pttCode,$/m)
  })

  it('composer da bindingMatches kullaniyor', () => {
    const composer = readFileSync(
      join(__dirname, '..', '..', 'app', 'chat', 'composer', 'hooks', 'use-composer-voice.ts'),
      'utf8'
    )

    expect(composer).toContain('bindingMatches(binding, event)')
    expect(composer).not.toContain('event.code !== pttCode')
  })
})

describe('etiket ham dize gostermiyor', () => {
  it('centik ve ayar paneli insan okur ad kullaniyor', () => {
    expect(read('notch-shell.tsx')).toContain('formatPttBindingLabel(parsePttBinding(pttCode))')
    expect(read('..', 'voice-settings.tsx')).toContain('formatPttBindingLabel(binding)')
  })

  it('varsayilan degismedi', () => {
    expect(formatPttBinding(parsePttBinding(undefined))).toBe('ControlRight')
  })
})
