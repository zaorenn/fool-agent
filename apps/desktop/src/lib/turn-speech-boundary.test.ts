/**
 * Ses YALNIZCA bu turun cevabını okur — oturumun tamamını değil.
 *
 * Ölçülen hata (kullanıcının ``state.db``si, oturum 20260821_203645_a1dabe)
 * ------------------------------------------------------------------------
 * ``lastSpokenId`` null olduğunda ``spokenIndex`` -1 kalıyor ve toplayıcı
 * OTURUMUN TAMAMINI topluyordu: 6 asistan mesajı, 12.614 karakter.
 *
 * Ekranda "The Clockwork Gardener of Paris" dururken ses en baştan
 * "Sounds good. What's on your mind?" ve 21 saat önceki Elara hikâyesini
 * okuyordu. Kullanıcının bildirdiği birebir bu: "sesli okuduğu hikaye ve
 * yazılan cevap tamamen farklı."
 *
 * Çentik ``lastSpokenId``i hiç tohumlamıyordu; besteci tohumluyordu ama
 * yalnızca otomatik okuma AÇIKKEN. Yani doğruluk her yüzeyin ayrı ayrı
 * hatırlamasına bağlıydı ve biri unuttu.
 *
 * Çözüm tohumlamayı hatırlamak değil: fonksiyonun adı zaten TUR diyor, sınır
 * tek yerde uygulanıyor.
 */

import { describe, expect, it } from 'vitest'

import { type ChatMessage, collectUnspokenTurnSpeech } from './chat-messages'

function msg(id: string, role: 'assistant' | 'user', text: string, pending = false): ChatMessage {
  return {
    id,
    parts: [{ text, type: 'text' }],
    pending,
    role
  } as unknown as ChatMessage
}

/** Kullanıcının deposundaki şeklin küçültülmüş hâli. */
const SESSION: ChatMessage[] = [
  msg('u1', 'user', 'selam'),
  msg('a1', 'assistant', "Sounds good. What's on your mind?"),
  msg('u2', 'user', 'tell me a story, speak a lot'),
  msg('a2', 'assistant', 'Once upon a time, in Neo-Veridia, Elara...'),
  msg('u3', 'user', "The Fool, let's have a chat. Tell me a story."),
  msg('a3', 'assistant', 'The Clockwork Gardener of Paris...')
]

describe('tur siniri', () => {
  it('lastSpokenId YOKKEN bile yalnizca son tur', () => {
    // Hatanin tam kosulu: yeni monte olmus bir yuzey.
    const out = collectUnspokenTurnSpeech(SESSION, null)

    expect(out?.id).toBe('a3')
    expect(out?.text).toBe('The Clockwork Gardener of Paris...')
  })

  it('ESKI cevaplar hic girmiyor', () => {
    const out = collectUnspokenTurnSpeech(SESSION, null)

    expect(out?.text).not.toContain('Elara')
    expect(out?.text).not.toContain("What's on your mind")
  })

  it('turdaki TUM asistan baloncuklari giriyor', () => {
    // Araç çağrılı bir tur birkaç baloncuk üretiyor: anlatım + son cevap.
    const withTools: ChatMessage[] = [
      ...SESSION,
      msg('a4', 'assistant', 'Let me check.'),
      msg('a5', 'assistant', 'Done.')
    ]

    const out = collectUnspokenTurnSpeech(withTools, null)

    expect(out?.id).toBe('a3')
    expect(out?.text).toContain('Clockwork')
    expect(out?.text).toContain('Let me check.')
    expect(out?.text).toContain('Done.')
  })

  it('lastSpokenId turun ICINDE ise ondan sonrasi', () => {
    const withTools: ChatMessage[] = [...SESSION, msg('a4', 'assistant', 'Ek cumle.')]

    expect(collectUnspokenTurnSpeech(withTools, 'a3')?.text).toBe('Ek cumle.')
  })

  it('lastSpokenId ESKI bir turdaysa yine tur siniri kazaniyor', () => {
    // Sinir iki kisittan HANGISI daha ileriyse o.
    const out = collectUnspokenTurnSpeech(SESSION, 'a1')

    expect(out?.text).not.toContain('Elara')
    expect(out?.id).toBe('a3')
  })

  it('bu turda konusulacak sey kalmadiysa null', () => {
    expect(collectUnspokenTurnSpeech(SESSION, 'a3')).toBeNull()
  })

  it('akan cevap PENDING isaretleniyor', () => {
    const streaming = [...SESSION.slice(0, 5), msg('a3', 'assistant', 'Yaziyor', true)]

    expect(collectUnspokenTurnSpeech(streaming, null)?.pending).toBe(true)
  })

  it('hic kullanici mesaji yoksa cokmuyor', () => {
    const only = [msg('a1', 'assistant', 'merhaba')]

    expect(collectUnspokenTurnSpeech(only, null)?.text).toBe('merhaba')
  })
})
