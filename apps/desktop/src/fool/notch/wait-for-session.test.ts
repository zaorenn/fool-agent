/**
 * Oturum kimliği geç gelirse cümle ÇÖPE gitmemeli.
 *
 * Ölçülen yarış
 * -------------
 * ``$voiceSessionId``i ANA pencere yayınlıyor (``store/active-work.ts``).
 * Çentik onu yalnızca okuyor. Kullanıcı Ctrl+Alt+V'ye ana pencere daha
 * oturumunu açmadan basarsa çentik ``''`` okuyup HEMEN hata veriyordu:
 * kullanıcı cümlesini söylüyor, kayıt alınıyor, yazıya dökülüyor -- ve sonra
 * "Could not open a voice session" deyip atılıyor.
 *
 * O mesaj sebebi de çareyi de söylemiyordu. İkisi birden düzeltildi: kısa bir
 * bekleme, sonra NE YAPILACAĞINI söyleyen bir satır.
 */

import { beforeEach, describe, expect, it } from 'vitest'

import { $voiceSessionId, waitForVoiceSession } from './active-session'

beforeEach(() => $voiceSessionId.set(''))

describe('oturum kimligini bekleme', () => {
  it('deger ZATEN varsa hic beklemiyor', async () => {
    $voiceSessionId.set('abc')

    const started = Date.now()

    await expect(waitForVoiceSession(5_000)).resolves.toBe('abc')
    // Normal yol bu: bekleme olmamali.
    expect(Date.now() - started).toBeLessThan(100)
  })

  it('SONRADAN gelen degeri yakaliyor', async () => {
    const pending = waitForVoiceSession(2_000)

    setTimeout(() => $voiceSessionId.set('gec-gelen'), 20)

    await expect(pending).resolves.toBe('gec-gelen')
  })

  it('sure dolarsa BOS donuyor -- sonsuza kadar beklemiyor', async () => {
    // Sonsuz beklemek mikrofonu acik birakirdi.
    await expect(waitForVoiceSession(30)).resolves.toBe('')
  })

  it('bos yazilar beklemeyi BITIRMIYOR', async () => {
    const pending = waitForVoiceSession(300)

    // Ana pencere oturum kapatinca '' yayinliyor; bunu "geldi" saymak
    // beklemeyi bosa cikarirdi.
    setTimeout(() => $voiceSessionId.set(''), 10)
    setTimeout(() => $voiceSessionId.set('sonunda'), 40)

    await expect(pending).resolves.toBe('sonunda')
  })
})

describe('centik bekleyen cozucuyu kullaniyor', () => {
  it('dogrudan .get() DEGIL', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')

    const source = readFileSync(join(import.meta.dirname, 'use-notch-voice.ts'), 'utf8')

    // Artik yalnizca BEKLEMEKLE kalmiyor, oturum yoksa bir tane de ISTIYOR
    // (bkz. ``active-session.ts``). Sinanan sey ayni: dogrudan ``.get()``
    // okumak, henuz yayinlanmamis kimligi kacirmak demek.
    expect(source.includes('waitForVoiceSessionOrOpen()')).toBe(true)

    // ``haltTurn`` icindeki dogrudan okuma BILINCLI ve gerekcesi orada
    // yazili: suren bir turu durduruyor, oturum yoksa durduracak sey de yok.
    // Sinanan sey GONDERIM yolu.
    const resolver = source.slice(source.indexOf('const resolveSessionId'))

    expect(resolver.slice(0, 200)).not.toContain('$voiceSessionId.get()')
  })

  it('GONDERIM yolu artik oturum BEKLEMIYOR', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')

    const source = readFileSync(join(import.meta.dirname, 'use-notch-voice.ts'), 'utf8')

    // Centik ARTIK gondermiyor: metni yaziyor, gonderimi ana pencere yapiyor
    // (``use-voice-submit-requests``). Istenen buydu -- "centik ayni akisin
    // birebir aynisi, sadece atanan tus ile bas-konus hali."
    expect(source.includes('requestVoiceSubmit(text, interrupted)')).toBe(true)
    // Kendi ``prompt.submit``i kalmadi: o, composer'in IYIMSER kullanici
    // balonunu atliyordu ve kullanici konustugunda ekranda hicbir sey
    // olmuyordu.
    expect(source.includes("requestGateway('prompt.submit'")).toBe(false)

    // Gonderimden ONCE oturum beklenmiyor. Beklenirdi ve gecikmenin asil
    // kaynagi oydu: acik oturum yoksa 12 saniyeye kadar bir tane acilmasi
    // bekleniyordu -- konusma bittikten SONRA.
    const submit = source.slice(source.indexOf('const submitAudio'))

    expect(submit.slice(0, submit.indexOf('requestVoiceSubmit'))).not.toContain('await resolveSessionId()')

    // Eski, sebebi de caresi de vermeyen mesajlar geri gelmemeli.
    expect(source.includes('Could not open a voice session')).toBe(false)
    expect(source.includes('open one in the main window')).toBe(false)
  })
})
