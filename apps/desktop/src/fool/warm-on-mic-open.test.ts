/**
 * Motor, mikrofon AÇILDIĞI anda ısıtılıyor.
 *
 * Ölçülen hata
 * ------------
 * Isıtma yalnızca çentik OTURUMU açılırken bir kez çağrılıyordu. İki boşluk
 * bırakıyordu:
 *
 *   1. Çentiği hiç açmadan sohbet panelinden sesli tur başlatan kullanıcı
 *      soğuk bedelin tamamını ödüyordu.
 *   2. Motor boşta 300 sn sonra boşaltılıyor (kullanıcının kendi isteği), yani
 *      her uzun aradan sonra bedel geri geliyordu ve yeniden ısıtan yoktu.
 *
 * Ölçüldü: kokoro soğuk 29,43 sn / sıcak 1,07 sn.
 *
 * Zamanlayıcıyla sıcak tutmak yanlış cevap: kullanıcı motorun 5 dakika sonra
 * kapanmasını açıkça istedi. Doğru an mikrofonun açıldığı an -- yükleme,
 * kullanıcının konuşmakla geçirdiği saniyelerin arkasına gizleniyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const NOTCH = readFileSync(join(import.meta.dirname, 'notch/use-notch-voice.ts'), 'utf8')

const COMPOSER = readFileSync(join(import.meta.dirname, '../app/chat/composer/hooks/use-voice-conversation.ts'), 'utf8')

describe('mikrofon acilinca isitiliyor', () => {
  it('centikte bas-konus baslangicinda', () => {
    const begin = NOTCH.slice(NOTCH.indexOf('const begin = useCallback'), NOTCH.indexOf('const endSession'))

    expect(begin.includes('warmVoice()')).toBe(true)
  })

  it('bestecide sesli tur baslangicinda', () => {
    expect(COMPOSER.includes('warmVoice()')).toBe(true)
    // Mikrofonun ACILMASINDAN once gelmeli: sonra cagirmak kazanci yer.
    expect(COMPOSER.indexOf('warmVoice()')).toBeLessThan(COMPOSER.indexOf('handle.start({'))
  })

  it('hata YUTULUYOR -- isitma bir iyilestirme, gereklilik degil', () => {
    // Ag gecidi henuz ayakta degilse tur yine baslamali.
    expect(NOTCH.includes('warmVoice().catch(() => undefined)')).toBe(true)
    expect(COMPOSER.includes('warmVoice().catch(() => undefined)')).toBe(true)
  })

  it('centik oturum acilisindaki isitma DURUYOR', () => {
    // Bu, kullanici hic konusmadan once odenen en erken firsat.
    const shell = readFileSync(join(import.meta.dirname, 'notch/notch-shell.tsx'), 'utf8')

    expect(shell.includes('warmVoice()')).toBe(true)
  })
})

describe('yazili sohbet de isitiyor', () => {
  it('otomatik okuma acilinca motor isitiliyor', () => {
    // Klavyeden yazan kullanicida mikrofon HIC acilmiyor: mikrofona bagli
    // isitma bu yolu kapsamiyordu ve ilk cumle soguk yuklemeyi bekliyordu
    // (olculdu: kokoro soguk 26,1 sn / sicak 0,55 sn).
    const hook = readFileSync(join(import.meta.dirname, '../app/chat/composer/hooks/use-auto-speak-replies.ts'), 'utf8')

    expect(hook.includes('warmVoice()')).toBe(true)
  })
})
