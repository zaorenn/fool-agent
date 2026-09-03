/**
 * Bir cevabı YALNIZCA bir yüzey seslendirir -- pencereler arası dahil.
 *
 * Ölçülen hata
 * ------------
 * Çentik ayrı bir ``BrowserWindow``. Sahiplik hakemi (``fool/voice-owner.ts``)
 * düz bir ``atom`` üzerinde duruyordu, yani ``claimVoice('notch')`` yalnızca
 * çentiğin kendi kopyasına yazıyor ve ana penceredeki ``canSpeak('composer')``
 * her zaman ``true`` dönüyordu. İki yüzey de aynı ``$messages`` tikinde
 * uyanıyor, ikisi de konuşuyordu: kullanıcı aynı cümleyi İKİ KEZ duyuyordu.
 *
 * Ana süreçte çözülen, yarışsız bir hakem ZATEN vardı
 * (``store/ambient.ts::ownsAmbientCue`` -> ``electron/event-dedupe.ts``).
 * Besteci onu kullanıyordu; eksik olan çentiğin katılmasıydı.
 *
 * Sınav KAYNAĞI okuyor: davranışı taklit etmek, kancanın gerçekte hangi yolu
 * çağırdığını değil taklidin ne yaptığını sınamak olurdu.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const NOTCH = readFileSync(join(import.meta.dirname, 'use-notch-voice.ts'), 'utf8')

const COMPOSER = readFileSync(
  join(import.meta.dirname, '../../app/chat/composer/hooks/use-auto-speak-replies.ts'),
  'utf8'
)

describe('TEK konusan var: ana pencere', () => {
  it('centik ARTIK sentez yapmiyor', () => {
    // Mimari degisti ve sebebi olculdu: centik ayri bir ``BrowserWindow`` ve
    // kendi ``$messages``i ana pencerenin bir tur gerisinde. O listeden "ne
    // okunacak" karari vermek, seritte ESKI cevabin gorunmesine ve yeni
    // cevabin hic okunmamasina yol aciyordu (kullanicinin ekran goruntusu +
    // gunlukte tek bir sentez: yalnizca uyandirma onayi).
    //
    // ``active-session.ts``de zaten yazili olan karar sese de uygulandi:
    // centik bir GIRDI AYGITI. Gonderimi ana pencere yapiyordu, artik
    // seslendirmeyi de o yapiyor.
    expect(NOTCH).not.toContain('startSpeechStream(')
  })

  it('centik yalnizca UYANDIRMA ONAYINI seslendiriyor', () => {
    // Tek istisna ve bilincli: onay sesi bir CEVAP degil, centigin kendi
    // geri bildirimi ("I'm listening") ve ana pencerenin haberi olmasi
    // gereken bir sey degil.
    expect(NOTCH).toContain('playSpeechText(WAKE_ACK_TEXT')
  })

  it('hakeme BESTECI basvuruyor ve akistan ONCE', () => {
    // Ayni sohbet birkac pencerede acikken cevabi TEK biri seslendirmeli.
    expect(COMPOSER).toContain('ownsAmbientCue')
    expect(COMPOSER.indexOf('ownsAmbientCue')).toBeLessThan(COMPOSER.indexOf('startSpeechStream('))
  })

  it('reddedilen cevap icin tekrar tekrar talep etmiyor', () => {
    expect(COMPOSER).toContain('declinedRef')
  })
})
