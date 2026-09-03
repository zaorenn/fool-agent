/**
 * Ses ayarları AKTİF profile gitmeli.
 *
 * Ölçülen hata
 * ------------
 * ``fool/voice-api.ts`` isteklerine profil eklemiyordu, yani bütün ses
 * ayarları paneli her zaman BİRİNCİL arka uca yazıyordu. Oysa oynatma
 * (``speakText``) ve yazıya dökme (``transcribeAudio``) ``profileScoped()``
 * kullanıyor ve AKTİF profile gidiyor.
 *
 * İki yüzey iki ayrı arka uca bakınca panel yalan söylüyor. Kullanıcının
 * makinesinde ölçüldü:
 *
 *     config.yaml                       tts.provider: chatterbox   <- panelin gördüğü
 *     profiles/persona/config.yaml   tts.provider: kokoro       <- gerçekten koşan
 *
 * Ekranda çıkan hata da yanlış motoru suçluyordu: "Kokoro kurulu değil" --
 * kullanıcının hiçbir zaman seçmediği motor. Aynı kayma kurulan motorlar,
 * aygıt seçimi ve yüklenen klonlar için de geçerliydi.
 *
 * Sınav KAYNAĞI okuyor: köprünün taklidi, ``desktop.api``ye hangi alanların
 * gittiğini değil taklidin ne yaptığını sınardı.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const SOURCE = readFileSync(join(import.meta.dirname, 'voice-api.ts'), 'utf8')

describe('ses ayarlari profil kapsaminda', () => {
  it('aktif profili OKUYOR', () => {
    expect(SOURCE.includes('getApiRequestProfile')).toBe(true)
  })

  it('profili istege EKLIYOR', () => {
    expect(/\.\.\.\(profile \? \{ profile \} : \{\}\)/.test(SOURCE)).toBe(true)
  })

  it('profil cozumu istekten ONCE geliyor', () => {
    const resolveAt = SOURCE.indexOf('const profile = getApiRequestProfile()')
    const requestAt = SOURCE.indexOf('desktop.api<T>({')

    expect(resolveAt).toBeGreaterThan(-1)
    expect(requestAt).toBeGreaterThan(resolveAt)
  })
})

describe('oynatma ile ayni arka uca gidiyor', () => {
  it('speakText de profil kapsamli -- ikisi ayrismamali', () => {
    const hermes = readFileSync(join(import.meta.dirname, '..', 'hermes.ts'), 'utf8')
    const speak = hermes.slice(hermes.indexOf('export function speakText'))

    expect(speak.slice(0, 400).includes('profileScoped()')).toBe(true)
  })
})
