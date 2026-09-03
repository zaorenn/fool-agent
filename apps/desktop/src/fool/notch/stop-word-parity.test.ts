/**
 * İki sesli yüzey AYNI kuralları kullanıyor mu.
 *
 * İstenen: "notch bu conversation modun birebir aynısı ancak bas-konuş hali
 * olmalı." İki ayrı kanca olmalarının gerçek bir sebebi var (kaydın sınırını
 * biri sessizlik, diğeri kullanıcı çiziyor) ama KURALLARIN ayrışması bunun
 * parçası değil -- ve sessizce ayrıştılar.
 *
 * Buradaki testler kaynağa bakıyor çünkü sınanan şey davranışın kendisi değil,
 * iki dosyanın aynı seçimleri yapması: bir yüzeyde çağrılan bir şeyin
 * diğerinde unutulmuş olmaması.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const NOTCH = readFileSync(join(__dirname, 'use-notch-voice.ts'), 'utf8')

const CONVERSATION = readFileSync(
  join(__dirname, '..', '..', 'app', 'chat', 'composer', 'hooks', 'use-voice-conversation.ts'),
  'utf8'
)

describe('sesli yuzey esligi', () => {
  it('IKISI de sozlu durdurma sozcugunu taniyor', () => {
    // Notch bunu gondermeye devam ediyordu: "dur" demek modele "dur" yazmakti
    // ve konusma hic bitmiyordu.
    expect(NOTCH).toContain('isVoiceStopCommand')
    expect(CONVERSATION).toContain('isVoiceStopCommand')
  })

  it('IKISI de araya girerken oynatmayi ORTAK yardimciyla kesiyor', () => {
    // Susturmak ve modele soylemek tek is. Ayri durduklarinda notch yalnizca
    // susturuyordu ve model sozunun kesildigini hic ogrenmiyordu.
    expect(NOTCH).toContain('interruptVoicePlayback')
    expect(CONVERSATION).toContain('interruptVoicePlayback')
  })

  it('hicbir yuzey mandali ELLE kurmuyor', () => {
    // ``stopVoicePlayback`` araya girme DISINDA hala mesru (tur bitti, yuzey
    // kapandi, bayat bir oturum cozuldu) -- ama ikisini elle esleyen kod
    // kalmamali: bir yerde biri unutuldugunda ayni hata sessizce geri gelir.
    // Cift her zaman ortak yardimcidan gecmeli.
    for (const source of [NOTCH, CONVERSATION]) {
      expect(source).not.toContain('markVoicePlaybackInterrupted(')
    }
  })

  it('IKISI de ayni araya girme kapisini kullaniyor', () => {
    // FOOL-SEAM: shared-voice-policy
    expect(NOTCH).toContain('claimBarge')
    expect(CONVERSATION).toContain('claimBarge')
  })

  it('notch gonderimi KESILDI bayragini tasiyor', () => {
    // Notch ag gecidine dogrudan gidiyor, yani besteci gonderiminin mandali
    // tuketen yolundan gecmiyor.
    expect(NOTCH).toContain('takeVoicePlaybackInterrupted')
    expect(NOTCH).toContain('interrupted')
  })

  it('IKISI de araya girdikten sonra turun YATISMASINI bekliyor', () => {
    // Farkin kaldigi son yer buydu: sohbet kipinde bir dongu vardi, centikte
    // hic bekleme yoktu. Kural artik ``interrupt.ts``te tek kopya.
    expect(NOTCH).toContain('settle:')
    expect(CONVERSATION).toContain('waitUntilSettled')
  })

  it('bekleme kurali ORTAK modulde, kopyalanmis degil', () => {
    for (const source of [NOTCH, CONVERSATION]) {
      expect(source).not.toContain('INTERRUPT_SETTLE_TIMEOUT_MS =')
    }
  })
})
