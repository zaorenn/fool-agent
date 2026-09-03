/**
 * Klonladığın ses BAŞKA bir motorda duruyorsa bunu görmelisin.
 *
 * Ölçülen hata
 * ------------
 * Kullanıcının yapılandırması::
 *
 *   tts.provider              kokoro
 *   tts.kokoro.voice          bf_emma        <- İngiliz KADIN sesi
 *   tts.chatterbox.voice_sample  .../humans-cling-to-their-precious-...mp3
 *   tts.styletts2.reference      (aynı dosya)
 *
 * Yani Ultron klonu diskte, yapılandırmada ve panelde duruyordu -- ama konuşan
 * motor kokoro'ydu ve klon hiç duyulmuyordu. Kullanıcının bildirdiği:
 * "şuan uygulamada duyduğum ses kadın."
 *
 * Persona seçicisi yalnızca AKTİF motorun ses listesinde arama yapıyor ve
 * motor değiştirmiyor. Chatterbox'ın tek sesi olduğu için persona orada zaten
 * hiçbir şey yapamaz. Sonuç: o klona seçiciden ulaşmanın HİÇBİR yolu yoktu ve
 * arayüz sebebi de söylemiyordu.
 *
 * Sessizce motor değiştirmek yanlış cevap: kullanıcı hızlı motoru bilerek
 * seçmiş olabilir (ölçüldü, kokoro 200 ms / chatterbox 1894 ms). Doğru cevap
 * durumu SÖYLEMEK ve geçişi bir tıka indirmek.
 */

import { describe, expect, it } from 'vitest'

import type { VoiceItem } from '../voice-api'

import { idleClone, speakingSummary } from './persona'

function item(patch: Partial<VoiceItem>): VoiceItem {
  return {
    active: false,
    assets_installed: true,
    clone: '',
    clone_capable: false,
    clone_help: '',
    cpu_warning: '',
    cuda_ready: false,
    device: 'cpu',
    engine_error: '',
    engine_installed: true,
    id: 'x',
    installed: true,
    kind: 'tts',
    label: 'X',
    voice: '',
    voices: [],
    ...patch
  } as VoiceItem
}

const KOKORO = item({
  active: true,
  id: 'kokoro',
  label: 'Kokoro',
  voice: 'bf_emma',
  voices: [
    { id: 'bf_emma', label: 'Emma — british female' },
    { id: 'am_michael', label: 'Michael — male' }
  ]
})

const CHATTERBOX = item({
  clone: 'ultron.mp3',
  clone_capable: true,
  id: 'chatterbox',
  label: 'Chatterbox'
})

describe('bosta duran klon', () => {
  it('AKTIF OLMAYAN motordaki klon yakalaniyor', () => {
    expect(idleClone([KOKORO, CHATTERBOX])?.id).toBe('chatterbox')
  })

  it('klon AKTIF motordaysa uyari YOK', () => {
    const active = item({ ...CHATTERBOX, active: true })

    expect(idleClone([item({ ...KOKORO, active: false }), active])).toBeNull()
  })

  it('KURULU olmayan motor sayilmiyor', () => {
    // Kurulu olmayan bir motora gecmeyi onermek, kullaniciyi calismayan bir
    // yola sokardi.
    expect(idleClone([KOKORO, item({ ...CHATTERBOX, installed: false })])).toBeNull()
  })

  it('klon yoksa uyari YOK', () => {
    expect(idleClone([KOKORO, item({ ...CHATTERBOX, clone: '' })])).toBeNull()
  })

  it('STT ogeleri karismiyor', () => {
    const stt = item({ clone: 'x.mp3', id: 'whisper-turbo', kind: 'stt' })

    expect(idleClone([KOKORO, stt])).toBeNull()
  })
})

describe('konusan ses tek satirda yaziyor', () => {
  it('SES ADIYLA -- kullanicinin cevabini aradigi satir', () => {
    // "Neden kadin sesi duyuyorum" sorusunun cevabi burada.
    expect(speakingSummary(KOKORO)).toBe('Kokoro — Emma — british female')
  })

  it('klon secilmisse KLON adi', () => {
    expect(speakingSummary(item({ ...CHATTERBOX, active: true }))).toContain('ultron.mp3')
  })

  it('ses listesi yoksa yalnizca motor adi', () => {
    expect(speakingSummary(item({ id: 'piper', label: 'Piper', voice: 'en_US-lessac' }))).toBe('Piper')
  })

  it('motor yoksa bos', () => {
    expect(speakingSummary(null)).toBe('')
  })
})
