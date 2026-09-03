import { describe, expect, it } from 'vitest'

import {
  claimBarge,
  createBargeGate,
  forceClaimBarge,
  isPlayingPhase,
  releaseBarge,
  shouldMonitorBargeIn
} from './barge-in'

describe('barge kapisi', () => {
  it('turu ilk talep edene verir', () => {
    const gate = createBargeGate()

    expect(claimBarge(gate, 'voice')).toBe(true)
    expect(claimBarge(gate, 'key')).toBe(false)
  })

  it('ayni talep sahibi kendini engellemez', () => {
    // Tus tekrari ve art arda gelen VAD olaylari gercek: ikinci cagri
    // kullanicinin kendi girisimini iptal etmemeli.
    const gate = createBargeGate()

    expect(claimBarge(gate, 'key')).toBe(true)
    expect(claimBarge(gate, 'key')).toBe(true)
  })

  it('serbest birakildiktan sonra yeniden talep edilebilir', () => {
    const gate = createBargeGate()

    claimBarge(gate, 'voice')
    releaseBarge(gate)

    expect(claimBarge(gate, 'key')).toBe(true)
  })

  it('acik tus basisi sesle yakalamayi devralir', () => {
    // Ses yarim saniye once tetiklenmis olabilir; kullanici buna ragmen
    // tusa bastiysa mikrofonu kendisi yonetmek istiyordur. Ilk gelene
    // birakmak tusu sessizce yutardi.
    const gate = createBargeGate()

    claimBarge(gate, 'voice')
    forceClaimBarge(gate, 'key')

    expect(gate.claimedBy).toBe('key')
  })

  it('tus ile ses ayni anda gelirse tek gonderim kalir', () => {
    // Insan refleksi: kullanici konusmaya baslarken tusa da basiyor.
    // Kapi olmadan ayni cumle modele iki kez gidiyordu.
    const gate = createBargeGate()
    const winners = (['voice', 'key'] as const).filter(who => claimBarge(gate, who))

    expect(winners).toEqual(['voice'])
  })
})

describe('izleyici penceresi', () => {
  it('dusunme VE konusma sirasinda acik', () => {
    // 'thinking' dahil: model cevabi uretirken olan 1-3 saniyelik sessizlikte
    // yapilan araya girmeler yalnizca-oynatma izlemesiyle kaciriliyordu.
    expect(shouldMonitorBargeIn('thinking')).toBe(true)
    expect(shouldMonitorBargeIn('speaking')).toBe(true)
  })

  it('dinlerken kapali', () => {
    // Mikrofon zaten kayitta; ikinci bir getUserMedia akisi Windows'ta
    // kaydi bozuyor.
    expect(shouldMonitorBargeIn('listening')).toBe(false)
  })

  it('bosta ve yaziya dokerken kapali', () => {
    expect(shouldMonitorBargeIn('idle')).toBe(false)
    expect(shouldMonitorBargeIn('transcribing')).toBe(false)
  })

  it('evre yalnizca konusurken oynatma sayilir', () => {
    expect(isPlayingPhase('speaking')).toBe(true)
    expect(isPlayingPhase('thinking')).toBe(false)
  })
})

/**
 * İKİ YÜZEY AYNI KAPIYI kullanıyor mu?
 *
 * Friend penceresinin satır içi bir kopyası vardı:
 *
 *     const monitorActive = phase === 'thinking' || phase === 'speaking' || capturing
 *
 * Kopyalar ayrışır ve buradaki ayrışmanın bedeli, araya girmenin BİR yüzeyde
 * sessizce ölmesi. Bu testler kaynağı okuyor -- mantığı kopyalayan bir dosya
 * eklenirse kırılır.
 */
describe('araya girme olcum saati', () => {
  it('kare saatine BAGLI DEGIL', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')

    const source = readFileSync(join(import.meta.dirname, '../../lib/voice-barge-in.ts'), 'utf8')

    // Yorumlar hariç GERÇEK çağrılar.
    const code = source
      .split('\n')
      .filter(line => !line.trimStart().startsWith('//') && !line.trimStart().startsWith('*'))
      .join('\n')

    expect(
      /window\.requestAnimationFrame\s*\(/.test(code),
      'olcum dongusu rAF ile kosuyor: arka plandaki pencerede bogulur'
    ).toBe(false)
  })

  it('ses is parcaciginda kosuyor', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')

    const source = readFileSync(join(import.meta.dirname, '../../lib/voice-barge-in.ts'), 'utf8')

    expect(source.includes('createScriptProcessor')).toBe(true)
    expect(source.includes('onaudioprocess')).toBe(true)
  })

  /**
   * Düğüm bir hedefe bağlı olmadan çalışmıyor, ama hedef doğrudan hoparlör
   * OLAMAZ: mikrofonu geri çalmak anında geri besleme demek.
   */
  it('mikrofonu hoparlore GERI CALMIYOR', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')

    const source = readFileSync(join(import.meta.dirname, '../../lib/voice-barge-in.ts'), 'utf8')

    expect(source.includes('gain.value = 0')).toBe(true)
  })
})
