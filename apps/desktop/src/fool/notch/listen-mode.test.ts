import { describe, expect, it } from 'vitest'

import {
  $listenMode,
  DEFAULT_LISTEN_MODE,
  listenModeHint,
  sanitizeListenMode,
  toggleListenMode
} from './listen-mode'

describe('listen mode', () => {
  it('varsayilan ELLER SERBEST -- sesli arayuzun amaci bu', () => {
    expect(DEFAULT_LISTEN_MODE).toBe('hands-free')
  })

  it.each([undefined, null, '', 'HANDS-FREE', 'ptt', 7, {}])(
    'taninmayan girdi (%o) varsayilana dusuyor',
    raw => {
      expect(sanitizeListenMode(raw)).toBe('hands-free')
    }
  )

  it('gecerli kipler AYNEN korunuyor', () => {
    expect(sanitizeListenMode('push-to-talk')).toBe('push-to-talk')
    expect(sanitizeListenMode('hands-free')).toBe('hands-free')
  })

  it('cevirmek iki kipi degistiriyor', () => {
    $listenMode.set('hands-free')

    expect(toggleListenMode()).toBe('push-to-talk')
    expect($listenMode.get()).toBe('push-to-talk')
    expect(toggleListenMode()).toBe('hands-free')
  })

  it('ipucu HANGI kipte oldugunu ve ne olacagini soyluyor', () => {
    // Yalnizca kipi yazmak yetmezdi: kullanici dugmeye basinca ne olacagini
    // bilmeden basmaz.
    expect(listenModeHint('hands-free', 'Ctrl+Alt+V')).toContain('push-to-talk')
    expect(listenModeHint('push-to-talk', 'Ctrl+Alt+V')).toContain('hands-free')
    expect(listenModeHint('push-to-talk', 'Ctrl+Alt+V')).toContain('Ctrl+Alt+V')
  })
})

/**
 * Notch SEÇİLEN kipe uymalı.
 *
 * ``notch-shell.tsx`` ``shouldRearmListening``e ``mode: 'hands-free'``
 * SABİT geçiyordu, yani ``$listenMode`` hiç okunmuyordu: bas-konuş seçili
 * olsa bile notch her turdan sonra mikrofonu kendiliğinden açıyordu. Seçim
 * vardı, hiçbir şey yapmıyordu.
 *
 * Kullanıcının isteği buydu: "ctrl alt v modu sadece push to talkta çalışsın."
 */
describe('notch secilen dinleme kipine uyuyor', () => {
  it('kip SABIT yazili DEGIL', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')

    const source = readFileSync(join(import.meta.dirname, 'notch-shell.tsx'), 'utf8')

    const code = source
      .split('\n')
      .filter(line => !line.trimStart().startsWith('//'))
      .join('\n')

    expect(
      /mode:\s*'hands-free'/.test(code),
      "notch kipi sabit yaziyor -- kullanicinin secimi yok sayiliyor"
    ).toBe(false)
    expect(code.includes('mode: rearmListenMode')).toBe(true)
  })

  it('kipi PAYLASILAN depodan okuyor', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')

    const source = readFileSync(join(import.meta.dirname, 'notch-shell.tsx'), 'utf8')

    expect(source.includes('useStore($listenMode)')).toBe(true)
  })

  /** Bas-konuşta mikrofonu YALNIZCA tuş açar. */
  it('bas-konusta kendiliginden ACILMIYOR', async () => {
    const { shouldRearmListening } = await import('./hands-free')

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

  it('eller serbestte kendiliginden aciliyor', async () => {
    const { shouldRearmListening } = await import('./hands-free')

    expect(
      shouldRearmListening({
        capturing: false,
        idleRounds: 0,
        mode: 'hands-free',
        sessionActive: true,
        status: 'idle'
      })
    ).toBe(true)
  })
})
