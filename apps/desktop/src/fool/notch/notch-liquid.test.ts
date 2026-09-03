/**
 * Çentiğin sıvı açılışı/kapanışı ve üst kenar dalgaları.
 *
 * Kullanıcının tarifi:
 *
 *   "notch açılırken o top sıvı bir animasyonmuş gibi ekranın ortasına gelsin,
 *    sonra sanki yerçekimi onu yukarı çekiyormuş gibi çeksin ve sanki su
 *    sıçraması gibi notchu oluştursun, sonra kaybolsun o kırmızı top."
 *
 *   "notch kapanırken top notchu sıvı gibi dönerek içine çeksin ve ekranın
 *    üstünden yukarı çekerek kaybolsun."
 *
 *   "notch dinlerken ... notchtan çıkan dalgalar ... konuşma algılandığında
 *    dalgalar tekrardan notcha geri çekilsin."
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { LIQUID_CLOSE_MS, LIQUID_OPEN_MS } from './notch-liquid'

const read = (name: string) => readFileSync(join(__dirname, name), 'utf8')

const LIQUID = read('notch-liquid.tsx')
const SHELL = read('notch-shell.tsx')

describe('kirmizi top KALDIRILDI', () => {
  it('ayri bir nesne YOK -- akan sey centigin KENDISI', () => {
    // Kullanicinin karari: "notchun acilis animasyonu bok gibi, onu
    // basitlestir, o kirmizi topu komple kaldir ve basit bir sekilde
    // siviymis gibi notch o minimal haline aksin."
    //
    // Dogrusu da bu: iki hareketli parca (top + serit) ayni anda ekrandayken
    // goz hangisine bakacagini bilmiyordu.
    expect(SHELL).not.toContain('<NotchLiquid phase=')
    expect(SHELL).not.toContain('<NotchPet')
    expect(LIQUID).not.toContain('fool-liquid-open')
  })

  it('SERIT akiyor: ust kenardan dokuluyor', () => {
    expect(SHELL).toContain('liquidPourStyle(liquidPhase)')
    expect(LIQUID).toContain("transformOrigin: 'top center'")
  })

  it('tek salinimla yerine oturuyor', () => {
    // Sivi hissi asmayla geliyor, ama TEK salinim -- daha fazlasi zipzip
    // olurdu.
    expect(LIQUID).toContain('scaleY(1.12)')
    expect(LIQUID).toContain('scaleY(0.94)')
  })

  it('kapanista ust kenara TOPLANIYOR', () => {
    expect(LIQUID).toContain('fool-notch-drain')
  })

  it('bosta HICBIR animasyon yok', () => {
    // Surekli oynayan bir serit, kaldirilan topun yaptigi dikkat dagitmanin
    // aynisi olurdu.
    expect(LIQUID).toContain("if (phase === 'idle') {")
    expect(LIQUID).toContain('return {}')
  })
})

describe('gecis KENDILIGINDEN sonuyor', () => {
  it('sureler tanimli ve makul', () => {
    // Sonmezse top ekranda asili kalirdi -- kaldirilan davranisin ta kendisi.
    expect(LIQUID_OPEN_MS).toBeGreaterThan(300)
    expect(LIQUID_OPEN_MS).toBeLessThan(1_500)
    expect(LIQUID_CLOSE_MS).toBeGreaterThan(200)
    expect(LIQUID_CLOSE_MS).toBeLessThan(1_500)
  })

  it('sure dolunca ``idle``a donuyor', () => {
    expect(LIQUID).toContain("setPhase('idle')")
  })
})

describe('ust kenar dalgalari', () => {
  it('yalnizca DINLERKEN cikiyor', () => {
    expect(SHELL).toContain("voice.status === 'listening' && !voice.heardSpeech")
  })

  it('konusma algilaninca GERI CEKILIYOR', () => {
    // Kullanicinin istedigi: "konusma algilandiginda dalgalar tekrardan notcha
    // geri cekilsin."
    expect(LIQUID).toContain("transform: active ? undefined : 'scaleX(0)'")
    expect(LIQUID).toContain('transition: active')
  })

  it('INCE: bir piksel yuksekliginde', () => {
    // "ince dalgalar" -- kalin bir serit ekranin tepesini kapatirdi.
    expect(LIQUID).toContain('h-px')
  })

  it('CENTIKTEN cikiyor: ortadan disa dogru', () => {
    expect(LIQUID).toContain('scaleX(0.04)')
    expect(LIQUID).toContain('scaleX(1)')
  })
})

describe('genisleme YALNIZCA alt yaziyla', () => {
  it('dinlerken KUCUK kaliyor', () => {
    // Kullanicinin karari: "listening sirasinda notch bu ufak halde kalmali
    // ... sadece alt yazidan alt yaziya genislemeli." Dinlerken genis serit
    // acmak ekranin tepesini bos yere kapatiyordu.
    expect(SHELL).toContain('height: subtitleMode ? SUBTITLE_HEIGHT : COLLAPSED_HEIGHT')
    // Genislik CUMLE KADAR: "alt yazi cumle kadar genislemeli, eger cumle
    // uzunsa genis kisaysa ona gore uzunlukta olmali ki her seferinde cok yer
    // isgal etmesin." Ust sinir yine ekran genisligi.
    expect(SHELL).toContain('SUBTITLE_CHAR_PX')
    expect(SHELL).toContain('Math.min(')
    expect(SHELL).toContain('SUBTITLE_MIN_WIDTH')
  })

  it('ETKINKEN mikrofon simgesi YOK', () => {
    // "mikrofon butonu gitmeli" -- geriye seviyeye gore nefes alan tek bir
    // canli nokta kaliyor.
    expect(SHELL).toContain('{!expanded && <Mic')
  })

  it('kalin orta hal KALDIRILDI', () => {
    // 22 piksellik bir kutuya sigmayan dalga formu + durum + dugme yigini.
    expect(SHELL).not.toContain('<Waveform')
    expect(SHELL).not.toContain('<NotchText')
  })
})
