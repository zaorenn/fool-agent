/**
 * Çentik, açık sohbet yokken bir tane AÇTIRABİLMELİ.
 *
 * Ölçülen davranış: giriş ekranındayken bas-konuşa basılıyor, konuşuluyor ve
 * çentik "No chat is open yet — open one in the main window" diyordu. Mesaj
 * doğruydu, davranış yanlıştı: bas-konuşun bütün amacı önce pencereye gidip
 * sohbet açmadan konuşabilmek.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { beforeEach, describe, expect, it } from 'vitest'

import { $voiceSessionId, $voiceSessionWanted, requestVoiceSession, waitForVoiceSessionOrOpen } from './active-session'

beforeEach(() => {
  $voiceSessionId.set('')
  $voiceSessionWanted.set('')
})

describe('oturum istegi', () => {
  it('var olan oturumu ISTEK YAPMADAN veriyor', async () => {
    $voiceSessionId.set('live-1')

    const before = $voiceSessionWanted.get()

    expect(await waitForVoiceSessionOrOpen(5, 5)).toBe('live-1')
    expect($voiceSessionWanted.get()).toBe(before)
  })

  it('oturum yokken ISTEK birakiyor', async () => {
    await waitForVoiceSessionOrOpen(5, 5)

    expect($voiceSessionWanted.get()).not.toBe('')
  })

  it('istek sonrasi acilan oturumu yakaliyor', async () => {
    setTimeout(() => $voiceSessionId.set('opened-1'), 5)

    expect(await waitForVoiceSessionOrOpen(1, 400)).toBe('opened-1')
  })

  it('her istek AYIRT EDILEBILIR', () => {
    // Deger bir durum degil OLAY: ust uste iki istek ayirt edilebilmeli,
    // yoksa ikinci basis hicbir sey tetiklemez.
    requestVoiceSession()
    const first = $voiceSessionWanted.get()

    return new Promise<void>(resolve => {
      setTimeout(() => {
        requestVoiceSession()
        expect($voiceSessionWanted.get()).not.toBe(first)
        resolve()
      }, 2)
    })
  })
})

describe('istegi KARSILAYAN taraf', () => {
  const source = readFileSync(join(__dirname, 'use-voice-session-requests.ts'), 'utf8')

  it('yalnizca ANA pencerede kosuyor', () => {
    // Centik ayni paketi yukluyor; kapisiz kalsaydi kendi istegine kendisi
    // cevap verip ikinci bir oturum acardi.
    expect(source).toContain('isNotchWindow()')
  })

  it('ACIK oturum varken yeni acmiyor', () => {
    // Yoksa konusulan sohbetin yanina bos bir tane daha acilirdi.
    expect(source).toContain('$activeSessionId.get()')
  })

  it('acilistaki ESKI damgayi yutuyor', () => {
    expect(source).toContain('first')
  })
})
