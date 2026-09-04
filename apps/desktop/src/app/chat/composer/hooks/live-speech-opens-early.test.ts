/**
 * Sesli sohbette konuşma İLK metinle açılmalı — tur bitince değil.
 *
 * Ölçülen hata (kullanıcının ``agent.log``u, 2026-08-23 18:27)
 * -----------------------------------------------------------
 *   18:27:26.6  istem kabul edildi
 *   18:27:29.0  model akışı başladı
 *   18:27:41.3  İLK sentez başladı        <- 12,3 sn sonra
 *   18:27:41.7  ilk ses hazır             <- sentez yalnızca 0,37 sn
 *   18:27:42-57 kalan cümleler ardarda
 *
 * Sentez 0,37 saniye sürüyor, yani beklenen şey ses değil metnin
 * GÖNDERİLMESİYDİ. Ekranda o sırada sayfalarca yazı vardı.
 *
 * Sebep: ana döngü efekti ``[busy, ..., status]`` ile uyanıyor ve bu kancanın
 * mesajlara HİÇ reaktif aboneliği yoktu. ``busy`` ancak tur BİTİNCE düşüyor,
 * dolayısıyla ``openLiveSpeech`` o ana kadar hiç çağrılmıyordu: "canlı" akış
 * hiçbir zaman canlı değildi, tur sonunda açılıp her şeyi birden yutuyordu.
 *
 * Bu, denetimin tekrar eden deseni: besleme mekanizması (150 ms'lik
 * zamanlayıcı) zaten yazılmıştı, onu başlatan tetik yanlış yerdeydi.
 *
 * Sınav KAYNAĞI okuyor: kancayı render etmek mikrofon, ağ geçidi, depo ve
 * i18n ayağa kaldırmak demek -- ve taklidin ne yaptığını sınamak olurdu.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const SOURCE = readFileSync(join(import.meta.dirname, 'use-voice-conversation.ts'), 'utf8')

describe('canli konusma erken aciliyor', () => {
  it('mesajlara REAKTIF abonelik var', () => {
    // Bu olmadan kanca yalnizca busy/status degisimlerinde uyaniyordu.
    expect(SOURCE.includes('$messagesForSpeech.subscribe')).toBe(true)
  })

  it('abonelik openLiveSpeech CAGIRIYOR', () => {
    const effect = SOURCE.slice(SOURCE.indexOf('const open = () =>'), SOURCE.indexOf('$messagesForSpeech.subscribe'))

    expect(effect.includes('openLiveSpeech(response.id)')).toBe(true)
  })

  it('ayni cevap icin IKI KEZ acilmiyor', () => {
    // ``openLiveSpeech`` ``responseIdRef``i hemen yaziyor; muhafiz o.
    const effect = SOURCE.slice(SOURCE.indexOf('const open = () =>'), SOURCE.indexOf('$messagesForSpeech.subscribe'))

    expect(effect.includes('responseIdRef.current === response.id')).toBe(true)
  })

  it('yalnizca SESLI turda aciliyor', () => {
    // ``awaitingSpokenResponseRef`` gonderimde kuruluyor: yazili bir mesaj
    // sesli sohbet kipini tetiklememeli.
    const effect = SOURCE.slice(SOURCE.indexOf('const open = () =>'), SOURCE.indexOf('$messagesForSpeech.subscribe'))

    expect(effect.includes('awaitingSpokenResponseRef.current')).toBe(true)
  })

  it('useStore KULLANILMIYOR -- her token yeniden render etmesin', () => {
    // Besteci agir bir agac; token basina render gecikmeyi geri getirirdi.
    expect(SOURCE.includes('useStore(')).toBe(false)
  })

  it('besleme zamanlayicisi DURUYOR', () => {
    // Oturum acildiktan sonra metin bu zamanlayiciyla akiyor; duzeltme
    // yalnizca ACILISI one aldi.
    expect(SOURCE.includes('feedSpeechSession(responseId), 150')).toBe(true)
  })
})
