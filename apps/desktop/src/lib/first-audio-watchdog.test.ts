/**
 * "Preparing audio" SONSUZA kadar süremez.
 *
 * Ölçülen hata
 * ------------
 * Akış yolundaki tek zaman aşımı ``PLAYBACK_STALL_MS`` idi ve o
 * ``timeupdate`` olayına kuruluyor -- yani ancak ses BAŞLADIKTAN sonra
 * işliyor. Sentezin kendisi asılırsa hiçbir olay gelmiyor: ne ``end``, ne
 * ``close``, ne ``error``. Kod bu üçünü doğru ele alıyordu ama dördüncü hâli,
 * HİÇBİR ŞEYİN GELMEMESİNİ, hiç ele almıyordu.
 *
 * Kullanıcının bildirdiği: "prepare audio'da sonsuza kadar takılı kaldı."
 *
 * Eşik ÖLÇÜMDEN geliyor: soğuk bir motorun ilk sentezi (sidecar süreci +
 * model yükleme) kokoro'da 29,4 sn sürüyor, ısındıktan sonra 1,07 sn. Bu
 * sınav eşiğin o ölçümün ÜSTÜNDE kalmasını zorluyor -- birisi "15 saniye
 * yeter" diye kısarsa meşru bir soğuk başlangıç yedek yola düşer ve
 * kullanıcı beklemeyi iki kez öder.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const SOURCE = readFileSync(join(import.meta.dirname, 'voice-playback.ts'), 'utf8')

/** Kaynaktan sabiti oku (``45_000`` biçimi dahil). */
function constant(name: string): number {
  const match = new RegExp(`const ${name} = ([0-9_]+)`).exec(SOURCE)

  expect(match, `${name} kaynakta yok`).not.toBeNull()

  return Number((match?.[1] ?? '0').replaceAll('_', ''))
}

describe('ilk ses bekcisi', () => {
  it('kaynakta VAR', () => {
    expect(SOURCE.includes('FIRST_AUDIO_MS')).toBe(true)
    expect(SOURCE.includes('firstAudioTimer')).toBe(true)
  })

  it('OLCULEN soguk baslangicin ustunde', () => {
    // Soguk kokoro: 29,4 sn. Altina inmek mesru baslangici keser.
    expect(constant('FIRST_AUDIO_MS')).toBeGreaterThan(30_000)
  })

  it('sonsuz olmaktan cikariyor -- ust sinir da makul', () => {
    // Dakikalarca beklemek "sonsuz"un pratikte aynisi.
    expect(constant('FIRST_AUDIO_MS')).toBeLessThanOrEqual(90_000)
  })

  it('oynatma duraklamasindan AYRI bir sinir', () => {
    // Ikisi farkli seyi olcuyor: biri ses basladiktan sonraki duraklamayi,
    // digeri sesin hic baslamamasini.
    expect(constant('PLAYBACK_STALL_MS')).not.toBe(constant('FIRST_AUDIO_MS'))
  })

  it('ses BASLADIYSA atesleMEZ', () => {
    // Yoksa uzun bir cevabin ortasinda oturumu keserdi.
    expect(/if \(!started\) \{[\s\S]{0,300}?settle\('fallback'\)/.test(SOURCE)).toBe(true)
  })

  it('yedek yola dusuyor, sessizlige DEGIL', () => {
    // ``fallback`` cagirani tek seferlik POST yoluna gonderiyor; ``done``
    // deseydik "calindi" derdik ve hic ses cikmazdi.
    expect(SOURCE.includes("settle('fallback')")).toBe(true)
  })

  it('oturum kapaninca zamanlayici SOKULUYOR', () => {
    // Kalan bir zamanlayici, kapanmis bir oturumu yeniden karara baglardi.
    const settleBody = SOURCE.slice(SOURCE.indexOf('settled = true'), SOURCE.indexOf('resolve(value)'))

    expect(settleBody.includes('clearTimeout(firstAudioTimer)')).toBe(true)
  })

  it('ILK metinle kuruluyor, oturum acilirken degil', () => {
    // Metin gelmeden sentez baslamaz; erken kurmak bos bir oturumu
    // haksiz yere basarisiz sayardi.
    // indexOf KULLANILMIYOR: ayni adlar once ARAYUZ bildiriminde geciyor
    // (finish: () => void), yani dilim ters donerdi.
    const from = SOURCE.indexOf('append: text =>')
    const appendBody = SOURCE.slice(from, SOURCE.indexOf('finish: () =>', from))

    expect(appendBody.includes('FIRST_AUDIO_MS')).toBe(true)
  })
})

describe('tek seferlik yolun kendi siniri var', () => {
  it('speakText zaman asimi geciyor', () => {
    // Bu yol zaten sinirliydi; bekci yalnizca AKIS yolundaki bosluk icindi.
    const hermes = readFileSync(join(import.meta.dirname, '../hermes.ts'), 'utf8')

    expect(hermes.includes('audioSpeakRequestTimeoutMs')).toBe(true)
  })
})
