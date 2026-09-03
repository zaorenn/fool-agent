/**
 * Bir turu YALNIZCA bir yüzey seslendirir.
 *
 * Ölçülen hata
 * ------------
 * Kullanıcının bildirdiği: "hâlâ 2 kere okuyor cevapları, speak aloud 2 kere
 * oluyor."
 *
 * Hakem doğruydu ve iki yüzey de ona başvuruyordu -- ama PAYLAŞILAN şey
 * yanlıştı. İki ayrı kusur üst üste biniyordu:
 *
 *   1. ANAHTAR AYRIŞIYORDU. Besteci ``messages.findLast(assistant).id``
 *      kullanıyordu (turun SON mesajı), çentik ise
 *      ``collectUnspokenTurnSpeech().id`` (turun İLK mesajı). Bir tur birden
 *      çok görünür asistan mesajı ürettiğinde -- ara yorum + final -- iki
 *      farklı anahtar oluşuyor, iki talep de kazanıyor ve iki yüzey de
 *      konuşuyordu.
 *
 *   2. TALEP 1 SANİYE YAŞIYORDU. Çentik ilk token'da talep ediyor, besteci
 *      ise cevap TAMAMLANINCA -- aradan saniyeler geçtiği için ilk talep
 *      çoktan düşmüş oluyor ve ikincisi de kazanıyordu. Anahtarı birleştirmek
 *      tek başına bunu çözmezdi.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import type { ChatMessage } from '@/lib/chat-messages'
import { turnSpeechKey } from '@/lib/chat-messages'

const read = (...parts: string[]) => readFileSync(join(__dirname, ...parts), 'utf8')

const message = (id: string, role: string, over: Partial<ChatMessage> = {}) =>
  ({ id, role, ...over }) as unknown as ChatMessage

describe('iki yuzey AYNI anahtari uretiyor', () => {
  const messages = [
    message('u1', 'user'),
    message('a1', 'assistant'),
    message('a2', 'assistant')
  ]

  it('anahtar TURU gosteriyor, mesaji degil', () => {
    // Regresyonun kalbi: bir turda iki asistan mesaji varken iki yuzey
    // farkli kimlikleri secip ayri ayri kazaniyordu.
    expect(turnSpeechKey(messages)).toBe('u1')
  })

  it('ayni turda mesaj EKLENSE de anahtar degismiyor', () => {
    const later = [...messages, message('a3', 'assistant')]

    expect(turnSpeechKey(later)).toBe(turnSpeechKey(messages))
  })

  it('YENI tur YENI anahtar aliyor', () => {
    const next = [...messages, message('u2', 'user'), message('a3', 'assistant')]

    expect(turnSpeechKey(next)).toBe('u2')
  })

  it('kullanici mesaji YOKSA ilk cevaba dusuyor', () => {
    // ``null`` donmek iki yuzeyi de serbest birakirdi -- yani tam olarak
    // kacinilan durum.
    expect(turnSpeechKey([message('a1', 'assistant')])).toBe('a1')
  })

  it('GIZLI mesaj anahtar olmuyor', () => {
    expect(turnSpeechKey([message('h1', 'assistant', { hidden: true }), message('a1', 'assistant')])).toBe('a1')
  })

  it('bos gecmis anahtar uretmiyor', () => {
    expect(turnSpeechKey([])).toBeNull()
  })
})

describe('dikisler', () => {
  const NOTCH = read('use-notch-voice.ts')
  const COMPOSER = read('..', '..', 'app', 'chat', 'composer', 'hooks', 'use-auto-speak-replies.ts')

  it('TEK konusan hakeme basvuruyor', () => {
    // Centik artik sentez yapmiyor (ayri pencere, bir tur geriden gelen
    // ``$messages``). Talep yine gerekli: AYNI sohbet birkac ana pencerede
    // acik olabilir.
    expect(COMPOSER).toContain('turnSpeechKey')
    expect(COMPOSER).toContain('SPEECH_CLAIM_TTL_MS')
    expect(NOTCH).not.toContain('startSpeechStream(')
  })

  it('eski MESAJ bazli anahtar geri gelmedi', () => {
    expect(COMPOSER).not.toContain('ownsAmbientCue(`speak:${id}`)')
  })
})
