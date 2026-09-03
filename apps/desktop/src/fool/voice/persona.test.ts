/**
 * Persona: ses ve renk TEK seçim.
 *
 * Eşleştirme gerçek katalog verisiyle sınanıyor -- uydurma kimliklerle değil.
 * Ölçülen listeler (``fool/voice_models.py``):
 *
 *   kokoro     af_heart, af_bella, af_nicole, am_michael, am_puck,
 *              bf_emma, bm_george
 *   qwen3-tts  ryan, serena, aiden, dylan, eric, vivian, ...
 *   piper      en_US-lessac-medium  (TEK ses)
 */

import { describe, expect, it } from 'vitest'

import { persona, PERSONAS, voiceForPersona } from './persona'

const KOKORO = [
  { id: 'af_heart', label: 'American female - warm' },
  { id: 'af_bella', label: 'American female - clear' },
  { id: 'af_nicole', label: 'American female - soft' },
  { id: 'am_michael', label: 'American male - even' },
  { id: 'am_puck', label: 'American male - lively' },
  { id: 'bf_emma', label: 'British female' },
  { id: 'bm_george', label: 'British male' }
]

const QWEN = [
  { id: 'ryan', label: 'Even male' },
  { id: 'serena', label: 'Clear female' },
  { id: 'aiden', label: 'Young male' },
  { id: 'dylan', label: 'Low, calm male' },
  { id: 'eric', label: 'Narration tone' },
  { id: 'vivian', label: 'Warm female' }
]

const PIPER = [{ id: 'en_US-lessac-medium', label: 'en_US-lessac-medium' }]

describe('personalar', () => {
  it('hepsi ayri kimlik ve ayri renk tasiyor', () => {
    expect(new Set(PERSONAS.map(entry => entry.id)).size).toBe(PERSONAS.length)
    expect(new Set(PERSONAS.map(entry => entry.accent)).size).toBe(PERSONAS.length)
  })

  it('kullaniciya gorunen metin INGILIZCE', () => {
    for (const entry of PERSONAS) {
      expect(/^[\x20-\x7E]+$/.test(entry.label), entry.label).toBe(true)
      expect(/^[\x20-\x7E]+$/.test(entry.summary), entry.summary).toBe(true)
    }
  })

  it('bilinmeyen kimlik null', () => {
    expect(persona('yok-boyle')).toBeNull()
  })
})

describe('voiceForPersona — kokoro', () => {
  it('kadin personasi KADIN sesi seciyor', () => {
    expect(voiceForPersona(persona('ember')!, KOKORO)).toBe('af_heart')
  })

  it('erkek personasi ERKEK sesi seciyor', () => {
    expect(voiceForPersona(persona('slate')!, KOKORO)).toBe('am_michael')
  })

  it('berrak persona berrak kadin sesini seciyor', () => {
    expect(voiceForPersona(persona('frost')!, KOKORO)).toBe('af_bella')
  })

  it('canli persona canli erkek sesini seciyor', () => {
    expect(voiceForPersona(persona('iris')!, KOKORO)).toBe('am_puck')
  })
})

describe('voiceForPersona — qwen3', () => {
  it('ayni personalar BASKA motorda da dogru cinsiyeti buluyor', () => {
    expect(voiceForPersona(persona('ember')!, QWEN)).toBe('vivian')
    expect(voiceForPersona(persona('slate')!, QWEN)).toBe('ryan')
    expect(voiceForPersona(persona('frost')!, QWEN)).toBe('serena')
    expect(voiceForPersona(persona('iris')!, QWEN)).toBe('aiden')
  })
})

describe('voiceForPersona — sinir durumlari', () => {
  /**
   * Boş dönmek doğru cevap: Piper'ın tek sesi var ve onu "erkek sesi" diye
   * sunmak yalan olurdu. Arayüz bunu kullanıcıya söylüyor.
   */
  it('TEK sesli motorda hicbir sey secmiyor', () => {
    for (const entry of PERSONAS) {
      expect(voiceForPersona(entry, PIPER), entry.id).toBe('')
    }
  })

  it('bos listede hicbir sey secmiyor', () => {
    expect(voiceForPersona(persona('ember')!, [])).toBe('')
  })

  /**
   * Etiketler yerelleştirilse bile kokoro'nun KİMLİK kuralı değişmiyor:
   * ``af_``/``bf_`` kadın, ``am_``/``bm_`` erkek. İkinci basamak bu.
   */
  it('etiketler ANLAMSIZ olsa bile kimlik kuralindan buluyor', () => {
    const opaque = [
      { id: 'af_heart', label: '???' },
      { id: 'am_michael', label: '???' }
    ]

    expect(voiceForPersona(persona('ember')!, opaque)).toBe('af_heart')
    expect(voiceForPersona(persona('slate')!, opaque)).toBe('am_michael')
  })

  it('hicbir kural tutmuyorsa sessizce YANLIS ses secmiyor', () => {
    const unknown = [
      { id: 'speaker-1', label: 'one' },
      { id: 'speaker-2', label: 'two' }
    ]

    expect(voiceForPersona(persona('ember')!, unknown)).toBe('')
  })
})
