/**
 * Araya girme, sesi ÇALAN pencerede durdurmalı.
 *
 * Ölçülen hata: çentikten araya girildiğinde konuşma durmuyordu. Cevabı ana
 * pencere seslendiriyor (çentik ``canSpeak('notch')`` ile susuyor), ama
 * ``stopVoicePlayback()`` çağrıldığı pencerenin kendi ``AudioContext``ini
 * durduruyor -- yani çentik kendi sessizliğini kesiyordu.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it, vi } from 'vitest'

const stopVoicePlayback = vi.fn()

vi.mock('@/lib/voice-playback', () => ({ stopVoicePlayback: () => stopVoicePlayback() }))

const PLAYBACK = readFileSync(join(__dirname, '..', 'lib', 'voice-playback.ts'), 'utf8')
const MAIN = readFileSync(join(__dirname, '..', 'main.tsx'), 'utf8')

describe('sesi kes koprusu', () => {
  it('istek DIGER pencerelerde sesi kesiyor', async () => {
    const { $voiceStopRequest } = await import('./voice-stop-bridge')

    stopVoicePlayback.mockClear()
    $voiceStopRequest.set(String(Date.now()))

    expect(stopVoicePlayback).toHaveBeenCalled()
  })

  it('acilistaki ESKI damga sesi kesmiyor', async () => {
    // ``listen`` kullaniliyor, ``subscribe`` degil: yeni acilan bir pencere
    // depoda duran eski bir damga yuzunden kendi sesini kesmemeli.
    const source = readFileSync(join(__dirname, 'voice-stop-bridge.ts'), 'utf8')

    expect(source).toContain('$voiceStopRequest.listen(')
    expect(source).not.toContain('$voiceStopRequest.subscribe(')
  })

  it('araya girme yolu istegi YAYINLIYOR', () => {
    const block = PLAYBACK.slice(PLAYBACK.indexOf('export function interruptVoicePlayback'))

    expect(block.slice(0, 900)).toContain('requestVoiceStopEverywhere')
  })

  it('kopru HER pencerede yukleniyor', () => {
    // ``whenMainWindow`` YOK: durmasi gereken taraf tam da sesi calan taraf.
    expect(MAIN).toContain("import './fool/voice-stop-bridge'")

    const source = readFileSync(join(__dirname, 'voice-stop-bridge.ts'), 'utf8')

    // Cagri arantiyor, sozcuk degil: dosyanin kendi aciklamasi da geciyor.
    expect(source).not.toContain('whenMainWindow(')
  })
})
