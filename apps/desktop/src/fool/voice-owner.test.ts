import { beforeEach, describe, expect, it } from 'vitest'

import { $voiceOwner, canSpeak, claimVoice, releaseVoice } from './voice-owner'

beforeEach(() => $voiceOwner.set(null))

describe('sahiplik -- AYNI pencere icinde', () => {
  it('bos alani ilk talep eden aliyor', () => {
    expect(claimVoice('composer')).toBe(true)
    expect($voiceOwner.get()).toBe('composer')
  })

  it('ayni yuzey tekrar talep edebiliyor', () => {
    claimVoice('notch')

    expect(claimVoice('notch')).toBe(true)
  })

  it(`NOTCH composer'i devraliyor`, () => {
    // Centik akis yolunu kullaniyor (ilk cumlede ses); besteci ancak cevap
    // tamamlaninca okuyor.
    claimVoice('composer')

    expect(claimVoice('notch')).toBe(true)
    expect($voiceOwner.get()).toBe('notch')
  })

  it(`composer NOTCH'u devralmiyor`, () => {
    claimVoice('notch')

    expect(claimVoice('composer')).toBe(false)
    expect($voiceOwner.get()).toBe('notch')
  })
})

describe('birakma', () => {
  it('sahip birakinca alan bosaliyor', () => {
    claimVoice('notch')
    releaseVoice('notch')

    expect($voiceOwner.get()).toBeNull()
  })

  it('sahip OLMAYAN birakamiyor', () => {
    // Yoksa kapanan bir panel, konusan baska bir yuzeyin sahipligini
    // silerdi.
    claimVoice('notch')
    releaseVoice('composer')

    expect($voiceOwner.get()).toBe('notch')
  })

  it('biraktiktan sonra dusuk oncelikli de alabiliyor', () => {
    claimVoice('notch')
    releaseVoice('notch')

    expect(claimVoice('composer')).toBe(true)
  })
})

describe('konusabilir mi', () => {
  it('sahip yoksa herkes konusabiliyor', () => {
    // Sahiplik seslendirmeyi engellemek icin degil, CAKISMAYI engellemek
    // icin var.
    for (const surface of ['composer', 'notch'] as const) {
      expect(canSpeak(surface)).toBe(true)
    }
  })

  it('sahip olan konusabiliyor', () => {
    claimVoice('notch')

    expect(canSpeak('notch')).toBe(true)
  })

  it('sahip olmayan SESSIZ kaliyor', () => {
    claimVoice('notch')

    expect(canSpeak('composer')).toBe(false)
  })
})

/**
 * HER seslendiren yüzey sahipliği sormalı.
 *
 * Ölçülen hata (kullanıcının günlüğü, 2026-08-21 18:15): aynı cümle İKİ KEZ
 * sentezleniyordu.
 *
 *   fool-speak-stream-nl_653jl.wav        Friend'in akış yolu
 *   cache/audio/tts_20260821_181550.wav   sohbet panelinin tek-seferlik yolu
 *
 * Sonucu bu dosyanın başlığında zaten yazıyordu: "Preparing audio sonsuza
 * kadar duruyor, hiç ses çıkmıyor ve iki sentez işi birden makineyi
 * kastırıyor." Mekanizma bunun için yazılmıştı; ``use-auto-speak-replies``
 * onu çağırmayı atlamıştı.
 *
 * Bu sınav kaynağı okuyor: yeni bir seslendiren yüzey eklenip kapıyı
 * sormazsa burada kırılır.
 */
describe('seslendiren HER yuzey sahiplik soruyor', () => {
  const SPEAKERS = [
    ['sohbet paneli otomatik okuma', '../app/chat/composer/hooks/use-auto-speak-replies.ts'],
    ['sohbet paneli sesli tur', '../app/chat/composer/hooks/use-voice-conversation.ts'],
    ['notch', './notch/use-notch-voice.ts']
  ] as const

  it('hepsi canSpeak ya da claimVoice cagiriyor', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')

    for (const [label, relative] of SPEAKERS) {
      const source = readFileSync(join(import.meta.dirname, relative), 'utf8')

      expect(
        /canSpeak\(|claimVoice\(/.test(source),
        `${label} ses sahipligini hic sormuyor -- ayni cevabi ikinci kez seslendirebilir`
      ).toBe(true)
    }
  })

  it('otomatik okuma OZELLIKLE canSpeak soruyor', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')

    const source = readFileSync(
      join(import.meta.dirname, '../app/chat/composer/hooks/use-auto-speak-replies.ts'),
      'utf8'
    )

    // Otomatik: kullanici bir sey tiklamiyor, yani sessizce cakisiyor.
    expect(source.includes("canSpeak('composer')")).toBe(true)
  })
})

/**
 * BİR cevap, BİR ses — yüzey İÇİNDEKİ çakışma.
 *
 * Sahiplik yüzeyler arasını çözüyor ama ``canSpeak`` sahip YOKKEN de ``true``
 * dönüyor (bilerek: sahiplik konuşmayı engellemek için değil, çakışmayı
 * engellemek için). Sonuçta sohbet panelinin İKİ seslendiren yolu -- otomatik
 * okuma ve sesli tur -- aynı kapıdan birlikte geçiyordu.
 *
 * Kullanıcının bildirdiği: "friend'i mutelediğimde okuyor, sadece onda da
 * 2 kere okuyor aynı şeyi."
 *
 * Doğru yer oynatma katmanı: her seslendiren yol oradan geçiyor.
 */
describe('bir cevap bir ses', () => {
  it('oynatma katmani mesaj basina kayit tutuyor', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')

    const source = readFileSync(join(import.meta.dirname, '../lib/voice-playback.ts'), 'utf8')

    expect(source.includes('function claimSpeech')).toBe(true)
    // IKI giris de talep ediyor.
    expect(source.match(/claimSpeech\(options\.messageId\)/g)?.length).toBe(2)
  })

  it('ELLE okuma kaydi birakiyor -- ikinci tiklama calisiyor', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')

    const source = readFileSync(
      join(import.meta.dirname, '../components/assistant-ui/thread/assistant-message.tsx'),
      'utf8'
    )

    expect(source.includes('forgetSpokenMessage(messageId)')).toBe(true)
  })

})

/**
 * Sesli turda SAĞ CTRL bas-konuş ve TUŞLA araya girme.
 *
 * Composer'ın sesli turu sesle araya girmeyi zaten destekliyordu; eksik olan
 * tuşla araya girmekti. Kullanıcının isteği: "sağ ctrl ile konuşabilelim, hem
 * direkt cevap versin hem konuşursak direkt interrupt olsun."
 */
describe('composer sesli turunda bas-konus', () => {
  const source = async (name: string) => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')

    return readFileSync(join(import.meta.dirname, '../app/chat/composer/hooks', name), 'utf8')
  }

  it('bas-konus giris/cikis noktalari var', async () => {
    const text = await source('use-voice-conversation.ts')

    expect(text.includes('const pttDown')).toBe(true)
    expect(text.includes('const pttUp')).toBe(true)
  })

  /** Yoksa yakalanan cümle eski cevabın arkasına kuyruklanır. */
  it('tusa basmak KONUSAN modeli kesiyor', async () => {
    const text = await source('use-voice-conversation.ts')
    const body = text.slice(text.indexOf('const pttDown'), text.indexOf('const pttUp'))

    // Susturmak ve modele "sozunu kestim" demek TEK is; ikisi ortak
    // yardimcida esli duruyor (bkz. ``interruptVoicePlayback``).
    expect(body.includes('interruptVoicePlayback()')).toBe(true)
    expect(body.includes('onInterruptRef.current?.()')).toBe(true)
  })

  /** Açık kullanıcı eylemi sesle başlamış bir yakalamayı devralmalı. */
  it('tus kapiyi ZORLA aliyor', async () => {
    const text = await source('use-voice-conversation.ts')

    expect(text.includes("forceClaimBarge(bargeGateRef.current, 'key')")).toBe(true)
  })

  it('tus kodu centikle ORTAK depodan', async () => {
    const text = await source('use-composer-voice.ts')

    expect(text.includes('$pttCode')).toBe(true)
  })

  /** Tuş hâlâ basılıyken odak giderse mikrofon sonsuza kadar açık kalırdı. */
  it('odak kaybi birakma sayiliyor', async () => {
    const text = await source('use-composer-voice.ts')

    expect(text.includes("window.addEventListener('blur'")).toBe(true)
  })

  it('SESLE araya girme kapanmadi', async () => {
    const text = await source('use-voice-conversation.ts')

    // Iki yol da ayni kapiyi paylasiyor.
    expect(text.includes('monitorSpeechDuringPlayback')).toBe(true)
    expect(text.includes("claimBarge(bargeGateRef.current, 'voice')")).toBe(true)
  })
})
