/**
 * Sessizlik saptayıcısı SES İŞ PARÇACIĞINDA koşuyor, ekran karesinde değil.
 *
 * Ölçülen risk
 * ------------
 * ``onSilence`` -- eller serbest bir turun NEREDE biteceğine karar veren şey --
 * yalnızca ``requestAnimationFrame`` tikinde değerlendiriliyordu. rAF pencere
 * gizlendiğinde, küçültüldüğünde ya da örtüldüğünde kısılıyor veya tümden
 * duruyor.
 *
 * Sonucu: ana pencere küçültülmüşken eller serbest tur başlatan kullanıcının
 * kaydı hiç bitmiyor. Mikrofon açık kalıyor, cümle gönderilmiyor, ekranda
 * hiçbir hata yok.
 *
 * Aynı tuzağa araya girme izleyicisi de düşmüştü ve orada çözüm zaten
 * yazılmıştı (``lib/voice-barge-in.ts``): ``ScriptProcessorNode``. Kayıt
 * tarafı o çözümü almamıştı.
 *
 * Sınav KAYNAĞI okuyor: jsdom'da ne rAF kısılması ne de gerçek bir ses
 * grafiği var, yani davranışı taklit etmek yalnızca taklidi sınamak olurdu.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

/** Yorumlar haric GERCEK kod -- ``notch/voice-session-safety.test.ts`` ile ayni desen. */
const NEWLINE = String.fromCharCode(10)

function code(source: string): string {
  return source
    .split(NEWLINE)
    .filter(line => {
      const trimmed = line.trimStart()

      return !trimmed.startsWith('//') && !trimmed.startsWith('*') && !trimmed.startsWith('/*')
    })
    .join(NEWLINE)
}

const RECORDER = readFileSync(join(import.meta.dirname, 'use-mic-recorder.ts'), 'utf8')
const BARGE = readFileSync(join(import.meta.dirname, '../../../../lib/voice-barge-in.ts'), 'utf8')

describe('kayit olcumu rAF DEGIL', () => {
  it('requestAnimationFrame KALMADI', () => {
    // Yorumlar ayiklaniyor: gerekceyi ANLATAN satirlar rAF'i ANMAYA devam
    // ediyor ve etmeli de.
    expect(code(RECORDER).includes('requestAnimationFrame')).toBe(false)
    expect(code(RECORDER).includes('cancelAnimationFrame')).toBe(false)
  })

  it('ses is parcaciginda kosuyor', () => {
    expect(RECORDER.includes('createScriptProcessor')).toBe(true)
    expect(RECORDER.includes('onaudioprocess = tick')).toBe(true)
  })

  it('SIFIR kazancli bir hedefe bagli', () => {
    // ``onaudioprocess`` yalnizca dugum bir hedefe BAGLIYSA calisiyor; hedef
    // dogrudan hoparlor olamaz, mikrofonu geri calmak olurdu.
    const setup = RECORDER.slice(RECORDER.indexOf('createScriptProcessor'), RECORDER.indexOf('const tick'))

    expect(setup.includes('sink.gain.value = 0')).toBe(true)
    expect(setup.includes('sink.connect(audioContext.destination)')).toBe(true)
  })

  it('temizlik dugumu SOKUYOR', () => {
    // Kalan bir ``onaudioprocess``, kapanmis bir kaydin seviyesini yazmaya
    // devam ederdi.
    const cleanup = RECORDER.slice(RECORDER.indexOf('const cleanup ='), RECORDER.indexOf('useEffect(() => () => cleanup()'))

    expect(cleanup.includes('onaudioprocess = null')).toBe(true)
    expect(cleanup.includes('disconnect()')).toBe(true)
  })

  it('sokulduktan sonraki tik ERKEN donuyor', () => {
    // Ses is parcacigi bir kare daha atesleyebilir.
    const tick = RECORDER.slice(RECORDER.indexOf('const tick = () =>'), RECORDER.indexOf('analyser.getByteTimeDomainData'))

    expect(tick.includes('if (!meterRef.current)')).toBe(true)
  })

  it('sessizlik BIR KEZ tetikleniyor', () => {
    // rAF surumunde ``return`` donguyu de kesiyordu; dugum surumunde kesmiyor,
    // yani tekrari onleyen tek sey bu bayrak.
    expect(RECORDER.includes('silenceTriggeredRef.current = true')).toBe(true)
    expect(RECORDER.includes('!silenceTriggeredRef.current')).toBe(true)
  })
})

describe('iki ses yuzeyi AYNI cozumu kullaniyor', () => {
  it('araya girme izleyicisi de ses is parcaciginda', () => {
    // Biri rAF'a geri donerse bu satir onu yakalar.
    expect(BARGE.includes('createScriptProcessor')).toBe(true)
    expect(code(BARGE).includes('requestAnimationFrame')).toBe(false)
  })
})
