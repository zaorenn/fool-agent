/**
 * Uyandırma sözcüğü ÇENTİĞİ açar, onay verir, susunca gönderir.
 *
 * Kullanıcının tarif ettiği sıra birebir:
 *
 *   "wake word notchu aktifleştirir, tts 'I'm listening' diye ses üretir ve bu
 *    ses biter bitmez dinlemeye başlar ve notchta bu gözükür, sonra kullanıcı
 *    söyleyeceklerini bitirdiğinde oluşan o 1 saniyelik sessizliği
 *    algıladığında mesajı gönderir ve daha sonrasında kullanıcı ya tekrar wake
 *    word'ü söyleyip döngüyü başlatana ya da sağ ctrl kullanarak konuşmaya
 *    başlayana kadar böyle devam eder."
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { HANDS_FREE_VAD, listenOptionsFor, modeForActivation, shouldRearmListening } from './hands-free'

const read = (...parts: string[]) => readFileSync(join(__dirname, ...parts), 'utf8')

const NEWLINE = String.fromCharCode(10)

const HOOK = read('use-notch-voice.ts')
const SHELL = read('notch-shell.tsx')
const WIRING = read('..', '..', 'app', 'contrib', 'wiring.tsx')

describe('sessizlikle biten yakalama', () => {
  it("``'auto'`` ELLER SERBEST ayarlarini veriyor", () => {
    // Uyandirma turu yeni bir yakalama yolu YAZMIYOR: ``begin('auto')`` zaten
    // "sessizlige kadar dinle, sonra gonder" demek.
    expect(modeForActivation('auto')).toBe('hands-free')
    expect(listenOptionsFor('hands-free')).toBe(HANDS_FREE_VAD)
  })

  it('sessizlik esigi kullanicinin tarif ettigi ~1 saniye', () => {
    expect(HANDS_FREE_VAD.silenceMs).toBeGreaterThanOrEqual(1_000)
    expect(HANDS_FREE_VAD.silenceMs).toBeLessThanOrEqual(1_500)
  })

  it('bas-konus ``undefined`` aliyor -- sessizlik kaydi KESMIYOR', () => {
    // Tus basiliyken sessizlik saptayicisi cumlenin ortasinda keserdi.
    expect(listenOptionsFor('push-to-talk')).toBeUndefined()
  })
})

describe('uyandirma turu TEK SEFERLIK', () => {
  it('kip ``push-to-talk`` kaldigi icin yeniden dinlemiyor', () => {
    // Kullanicinin karari: "sonrasinda ya tekrar wake word ya sag Ctrl."
    // Kipi eller serbeste cevirseydik tur biter bitmez mikrofon kendiliginden
    // acilirdi.
    expect(
      shouldRearmListening({
        capturing: false,
        idleRounds: 0,
        mode: 'push-to-talk',
        sessionActive: true,
        status: 'idle'
      })
    ).toBe(false)
  })

  it('centik kipi DEGISTIRMIYOR', () => {
    const wake = SHELL.slice(SHELL.indexOf("request?.mode === 'wake'"))

    expect(wake.slice(0, 400)).toContain('beginWakeTurn')
    // Eller serbeste cevirmek dongu baslatirdi.
    expect(wake.slice(0, 400)).not.toContain("$listenMode.set('hands-free')")
  })
})

describe('onay sesi', () => {
  it('SECILI TTS motorundan geciyor', () => {
    // Sabit bir ses dosyasi, kullanicinin sectigi sesle alakasiz bir "bip"
    // olurdu.
    expect(HOOK).toContain('playSpeechText(WAKE_ACK_TEXT')
  })

  it('dinleme onay BITTIKTEN sonra basliyor', () => {
    // Yanki: hoparlorden cikan "I'm listening" acik bir mikrofona kullanici
    // konusmasi gibi duser ve ajan kendi onayina cevap verirdi.
    const turn = HOOK.slice(HOOK.indexOf('const beginWakeTurn'))
    const ack = turn.indexOf('playSpeechText')
    const listen = turn.indexOf("begin('auto')")

    expect(ack).toBeGreaterThan(-1)
    expect(listen).toBeGreaterThan(ack)
    expect(turn.slice(0, listen)).toContain('await')
  })

  it('onay DUYULMASA da dinleme basliyor', () => {
    // Kullanici wake word'u soyledi ve konusmayi bekliyor; sesin gelmemesi
    // turu dusurmemeli.
    const turn = HOOK.slice(HOOK.indexOf('const beginWakeTurn'))

    expect(turn.slice(0, turn.indexOf("begin('auto')"))).toContain('catch')
  })
})

/**
 * ``wake.detected`` isleyicisinin CANLI KODU.
 *
 * Iki daraltma birden gerekiyor:
 *
 *   1. Dilim ilk ``return``a kadar -- genis bir dilim, dosyanin baska
 *      yerlerindeki mesru kullanimlari da yakalardi.
 *   2. YORUMLAR eleniyor -- eski davranis bilerek yorumda anlatiliyor
 *      (deponun uslubu: olculen hatayi kaynagin kendisinde birakmak) ve
 *      yorumu tarayan bir muhafiz kendi aciklamasina takilir.
 */
const WAKE_HANDLER = (() => {
  const start = WIRING.indexOf("event.type === 'wake.detected'")
  const end = WIRING.indexOf('return', WIRING.indexOf('notch?.wake?.()', start))

  return WIRING.slice(start, end)
    .split(NEWLINE)
    .filter(line => !line.trim().startsWith('//'))
    .join(NEWLINE)
})()

describe('uyandirma CENTIGI aciyor', () => {
  it('ana penceredeki konusma kipini DEGIL', () => {
    expect(WAKE_HANDLER).toContain('notch?.wake?.()')
    expect(WAKE_HANDLER).not.toContain('requestVoiceConversationStart()')
  })

  it('YENI oturum acmiyor', () => {
    // Acik sohbet varken uyandirmak, kullanicinin okudugu konusmayi birakip
    // bos bir sayfaya gecmek olurdu. Mesaj BAKTIGI sohbete gidiyor.
    expect(WAKE_HANDLER).not.toContain('startFreshSessionDraft()')
  })
})
