/**
 * Ses artık KULLANICININ AÇIK SOHBETİNE gidiyor.
 *
 * Önce sesin kendi ``companion``/``friend`` kapsamı ve ayrı bir oturumu
 * vardı. Friend/Jarvis kipleri kullanıcının kararıyla kaldırıldı, o ayrım da
 * kalktı: mikrofon doğrudan açık sohbete konuşuyor, arada hiçbir şey yok.
 *
 * Bedeli açıkça yazılmalı ve bu sınav onu görünür tutuyor: ses artık sohbet
 * panelinin kapsamında koşuyor (``desktop`` -- terminal, dosya, kod dahil).
 * Kapsamı ayıran mekanizma kiplerdi.
 *
 * Sınav kaynağı okuyor: davranışı taklit etmek, dosyanın gerçekte ne yaptığını
 * değil taklidin ne yaptığını sınamak olurdu.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const SOURCE = readFileSync(join(import.meta.dirname, 'use-notch-voice.ts'), 'utf8')

/** Yorumlar hariç GERÇEK kod. */
function code(source: string): string {
  return source
    .split('\n')
    .filter(line => {
      const trimmed = line.trimStart()

      return !trimmed.startsWith('//') && !trimmed.startsWith('*') && !trimmed.startsWith('/*')
    })
    .join('\n')
}

describe('ses ACIK SOHBETE gidiyor', () => {
  /**
   * Çentik AYRI bir ``BrowserWindow``: kendi ``$activeSessionId``i hiç
   * dolmuyor, ``null`` kalıyor. Ses ``session_id: null`` ile gidiyor ve ağ
   * geçidi onu kendi seçtiği bir oturuma düşürüyor -- kullanıcının gördüğü
   * "mesajlar önce bots kısmında çıkıyor, ana session'a hemen düşmüyor".
   *
   * Aynı tuzağa bas-konuş bağlaması ve dinleme kipi de düşmüştü.
   */
  it('PAYLASILAN oturum kimligini kullaniyor', () => {
    const body = code(SOURCE)

    expect(body.includes('$voiceSessionId.get()')).toBe(true)
    // Centikte HIC dolmayan atom kullanilmamali.
    expect(body.includes('$activeSessionId')).toBe(false)
  })

  it('koprii ANA pencerede kuruluyor', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')

    const bridge = readFileSync(
      join(import.meta.dirname, '../../store/active-work.ts'),
      'utf8'
    )

    expect(bridge.includes('$voiceSessionId')).toBe(true)
    expect(bridge.includes('FOOL-SEAM: voice-session-bridge')).toBe(true)
  })

  it('ARACI oturum makinesi KALMADI', () => {
    const body = code(SOURCE)

    expect(body.includes('ensureCompanionSession')).toBe(false)
    expect(body.includes('createCompanionSessionState')).toBe(false)
    expect(body.includes('friendSessionStore')).toBe(false)
  })

  it('oturum yoksa kullaniciya SOYLUYOR', () => {
    expect(/setError\(/.test(code(SOURCE))).toBe(true)
  })
})

/**
 * Köprüyü YALNIZCA ana pencere kurmalı.
 *
 * Çentik AYNI bundle'ı yüklüyor (``?win=notch``), yani köprü modülü orada da
 * koşuyor. Guard olmadan çentik kendi BOŞ ``$activeSessionId``ini paylaşılan
 * atoma yazıyor ve ana pencerenin değerini eziyor -- köprü kendi kendini
 * bozuyor. Kullanıcının gördüğü: ses yine yanlış oturuma gidiyor ve cevap
 * bot panelinde çıkıyor.
 */
describe('kopru yalnizca ANA pencerede', () => {
  it('centikte yayin YAPILMIYOR', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')

    const bridge = readFileSync(join(import.meta.dirname, '../../store/active-work.ts'), 'utf8')

    // Ortak yardimci: ``whenMainWindow`` centikte govdeyi HIC calistirmiyor
    // (bkz. ``store/main-window-only.ts``).
    expect(bridge.includes('whenMainWindow(')).toBe(true)
    // Guard, abonelikten ONCE gelmeli.
    expect(bridge.indexOf('whenMainWindow(')).toBeLessThan(
      bridge.indexOf('$activeSessionId.subscribe')
    )
  })
})
