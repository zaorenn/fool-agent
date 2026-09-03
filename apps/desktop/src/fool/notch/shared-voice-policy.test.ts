/**
 * Notch ile Composer aynı kuralları kullanmalı.
 *
 * İki ayrı ses yüzeyi var ve ikisi de kendi kopyasını tutuyordu:
 * ``use-voice-conversation.ts`` (composer) sessizlik eşiklerini elle yazıyor,
 * ``use-notch-voice.ts`` başka bir yerden okuyordu. İki yüzeyin farklı eşikte
 * susması, aynı cümlenin farklı yerde kesilmesi demek -- kullanıcı için
 * "bazen cümlemi yiyor" diye görünen, tekrar üretilemeyen bir hata.
 *
 * Bu testler kaynak metni okuyor. Alışılmadık ama burada doğru araç: ölçtüğümüz
 * şey davranış değil, İKİ DOSYANIN AYNI KAYNAĞA BAĞLI OLDUĞU. Bir sonraki
 * kişi sabiti yeniden elle yazarsa burada kırılıyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { HANDS_FREE_VAD } from './hands-free'

const ROOT = join(import.meta.dirname, '..', '..')
const COMPOSER = join(ROOT, 'app', 'chat', 'composer', 'hooks', 'use-voice-conversation.ts')

const composerSource = readFileSync(COMPOSER, 'utf8')

describe('ortak ses politikasi', () => {
  it('composer VAD ayarini ORTAK kaynaktan aliyor', () => {
    expect(composerSource).toContain("from '@/fool/notch/hands-free'")
    expect(composerSource).toContain('...HANDS_FREE_VAD')
  })

  it('composer sessizlik esiklerini ELLE yazmiyor', () => {
    // Elle yazilmis bir kopya sessizce ayrisir; asil hata bu.
    expect(composerSource).not.toContain('silenceLevel: 0.075')
    expect(composerSource).not.toContain('silenceMs: 1_250')
    expect(composerSource).not.toContain('idleSilenceMs: 12_000')
  })

  it('composer araya girme kapisini ORTAK kaynaktan aliyor', () => {
    expect(composerSource).toContain("from '@/fool/notch/barge-in'")
    expect(composerSource).toContain('claimBarge(')
    expect(composerSource).toContain('releaseBarge(')
  })

  it('ortak VAD ayari CLI varsayilanlariyla ayni', () => {
    // ``tools.voice_mode`` degerleri. Bunlar degisirse iki yuzey de birlikte
    // degismeli -- tek kaynak olmasinin sebebi bu.
    expect(HANDS_FREE_VAD.silenceLevel).toBe(0.075)
    expect(HANDS_FREE_VAD.silenceMs).toBe(1_250)
    expect(HANDS_FREE_VAD.idleSilenceMs).toBe(12_000)
  })

  it('dikis isaretli -- merge yutarsa gorunur', () => {
    expect(composerSource).toContain('FOOL-SEAM: shared-voice-policy')
  })
})
