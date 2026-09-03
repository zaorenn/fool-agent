/**
 * Akış kurulamazsa metin YİNE seslendirilmeli.
 *
 * Ölçülen hata: bu geri düşüş bir yüzeyde vardı, diğerinde yoktu ve sonucu
 * "duyuyor, yazıyor, ama konuşmuyor" oldu -- panel TALKING yazarken hiçbir
 * ses çıkmıyordu. Sessiz başarısızlığın ders kitabı hâli.
 *
 * Friend penceresi kaldırıldı (kullanıcının kararı); geriye tek sesli yüzey
 * olarak notch kaldı, sözleşme onun üstünde duruyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

/**
 * Sözleşme artık BESTECİDE.
 *
 * Çentik seslendirmeyi bıraktı: ayrı bir ``BrowserWindow`` olduğu için kendi
 * ``$messages``i ana pencerenin bir tur gerisindeydi ve o listeden karar
 * vermek eski cevabın okunmasına yol açıyordu. Tek konuşan artık ana pencere;
 * geri düşüş sözleşmesi de onunla birlikte oraya taşındı.
 */
const COMPOSER = readFileSync(
  join(import.meta.dirname, '..', '..', 'app', 'chat', 'composer', 'hooks', 'use-auto-speak-replies.ts'),
  'utf8'
)

describe('seslendirme geri dusus sozlesmesi', () => {
  it('akis KURULAMAZSA metni yine seslendiriyor', () => {
    expect(COMPOSER).toContain('playSpeechText')
  })

  it('akis SES URETMEDEN kapanirsa metni seslendiriyor', () => {
    // ``done`` -> 'fallback' = hic ses cikmadi; cagiran konusmali.
    expect(COMPOSER).toContain("outcome !== 'fallback'")
  })

  it('once AKIS deneniyor -- tek seferlik yol geri dusus', () => {
    const streamAt = COMPOSER.indexOf('startSpeechStream')
    const fallbackAt = COMPOSER.indexOf("outcome !== 'fallback'")

    expect(streamAt).toBeGreaterThan(-1)
    expect(fallbackAt).toBeGreaterThan(streamAt)
  })
})
