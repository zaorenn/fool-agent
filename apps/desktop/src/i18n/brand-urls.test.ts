/**
 * Marka dönüşümü URL'lere DOKUNMAMALI.
 *
 * Ölçülen hata
 * ------------
 * ``brandText``in son kuralı ``\bhermes\b`` -> ``fool`` ve ``\b`` sınırı
 * ``-`` karakterinde de geçerli. Katalogdaki
 *
 *     curl -fsSL https://hermes-agent.nousresearch.com/install.sh | sh
 *
 * kullanıcıya ``https://fool-agent.nousresearch.com/...`` olarak
 * gösteriliyordu: VAR OLMAYAN bir alan adı, dört dilde birden, hem de
 * kopyalanıp çalıştırılması beklenen bir komutun içinde.
 *
 * Aynı koruma çalışma-zamanı ARGÜMANLARI için zaten vardı
 * (``brandTextPreserving``) ve gerekçesi tam olarak bu alan adını örnek
 * veriyordu -- şablonun kendi metni atlanmıştı.
 *
 * Bir alan adı marka değil ADRESTİR.
 */

import { brandText } from '@fool/shared'
import { describe, expect, it } from 'vitest'

import { catalogFor } from './catalog'
import { LOCALE_OPTIONS } from './languages'

describe('markalama URL leri bozmuyor', () => {
  it('semali URL oldugu gibi kaliyor', () => {
    const url = 'https://hermes-agent.nousresearch.com/install.sh'

    expect(brandText(`Install it there (curl -fsSL ${url} | sh).`)).toContain(url)
  })

  it('ciplak alan adi oldugu gibi kaliyor', () => {
    expect(brandText('See hermes-agent.nousresearch.com for docs')).toContain(
      'hermes-agent.nousresearch.com'
    )
  })

  it('URL DISINDAKI metin markalanmaya devam ediyor', () => {
    const out = brandText('Hermes Desktop is ready; visit https://hermes-agent.example.com/docs')

    expect(out).toContain('The Fool Desktop is ready')
    expect(out).toContain('https://hermes-agent.example.com/docs')
  })

  it('veri dizini kurali korunuyor -- o bir URL degil', () => {
    expect(brandText('Open ~/.hermes/config.yaml')).toBe('Open ~/.fool/config.yaml')
  })
})

describe('katalogtaki kurulum adresi GERCEK', () => {
  it('hicbir dilde olu bir alan adi gostermiyor', () => {
    for (const option of LOCALE_OPTIONS) {
      const copy = catalogFor(option.id).settings.gateway.sshErrNotInstalled

      expect(typeof copy, `${option.id}: metin yok`).toBe('string')
      // Marka donusumunun urettigi hayali alan adi.
      expect(copy, `${option.id}`).not.toContain('fool-agent.nousresearch.com')
    }
  })

  it('bu deponun kendi kurulum betigine isaret ediyor', () => {
    expect(catalogFor('en').settings.gateway.sshErrNotInstalled).toContain(
      'https://raw.githubusercontent.com/zaorenn/fool-agent/main/scripts/install.sh'
    )
  })
})
