/**
 * Tanışma selamının kapısı.
 *
 * Kendiliğinden mesaj gönderen bir uygulama yanlış açtığında en can sıkıcı
 * şeydir; buradaki testler kapının dört kanadını da tutuyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { describe, expect, it } from 'vitest'

import { type GreetingState, isPersonaKickoff, PERSONA_KICKOFF, shouldGreet } from './persona-greeting'

const ready: GreetingState = {
  enabled: true,
  met: false,
  sessionId: 's1',
  messageCount: 0,
  attempted: false,
  busy: false
}

describe('shouldGreet', () => {
  it('persona profilinde, hic tanisilmamisken, bos oturumda GONDERIYOR', () => {
    expect(shouldGreet(ready)).toBe(true)
  })

  it('siradan ajanda GONDERMIYOR', () => {
    // Kod yazarken kullanilan ajan kendi kendine konusmaya baslamaz.
    expect(shouldGreet({ ...ready, enabled: false })).toBe(false)
  })

  it('DAHA ONCE tanisilmissa gondermiyor', () => {
    expect(shouldGreet({ ...ready, met: true })).toBe(false)
  })

  it('oturum YOKKEN gondermiyor', () => {
    expect(shouldGreet({ ...ready, sessionId: '' })).toBe(false)
  })

  it('SUREN bir sohbetin ortasina girmiyor', () => {
    expect(shouldGreet({ ...ready, messageCount: 1 })).toBe(false)
  })

  it('ajan calisirken gondermiyor', () => {
    // Kullanici tam o anda yazmis olabilir; turun ustune tur gondermek
    // konusmayi ikiye bolerdi.
    expect(shouldGreet({ ...ready, busy: true })).toBe(false)
  })

  it('ayni oturumda IKINCI kez gondermiyor', () => {
    expect(shouldGreet({ ...ready, attempted: true })).toBe(false)
  })
})

describe('isPersonaKickoff', () => {
  it('gonderilen metni TANIYOR', () => {
    expect(isPersonaKickoff(PERSONA_KICKOFF)).toBe(true)
  })

  it('bastaki bosluga TAKILMIYOR', () => {
    // Metin sunucuda normallestirmeden geciyor; sondaki bir bosluk yuzunden
    // tanimanin bozulmasi sacma bir kirilganlik olurdu.
    expect(isPersonaKickoff('\n  ' + PERSONA_KICKOFF)).toBe(true)
  })

  it('kullanicinin yazdigi bir seyi selam SANMIYOR', () => {
    expect(isPersonaKickoff('hey, first time using this')).toBe(false)
    expect(isPersonaKickoff('')).toBe(false)
  })

  it('metnin ICINDE gecmesi yetmiyor -- BASTA olmali', () => {
    expect(isPersonaKickoff('she said: ' + PERSONA_KICKOFF)).toBe(false)
  })
})

describe('PERSONA_KICKOFF', () => {
  it('modele NOTU ANMAMASINI soyluyor', () => {
    // Aksi halde ilk cumlesi "bana ilk konusmami soylediler" olurdu.
    expect(PERSONA_KICKOFF).toContain('do not mention this note')
  })
})
