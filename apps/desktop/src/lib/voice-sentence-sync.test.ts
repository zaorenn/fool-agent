/**
 * Konuşulan cümle, DUYULDUĞU anda ekrana gelmeli.
 *
 * İstenen: "sesli okunan cümleyi transcript gibi sırayla ve ses ile eşzamanlı
 * vermeli." Ses ileriye dönük zamanlanıyor -- sunucu bir sonraki cümleyi biz
 * öncekini dinlerken gönderiyor -- yani çerçeve gelir gelmez yazmak, henüz
 * duyulmamış cümleyi ekrana koymak olurdu.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const SOURCE = readFileSync(join(__dirname, 'voice-playback.ts'), 'utf8')

describe('cumle eszamanlamasi', () => {
  it('cumle karesi TANINIYOR', () => {
    expect(SOURCE).toContain("frame.type === 'sentence'")
  })

  it('cumle GELDIGI anda yazilmiyor', () => {
    // Cerceve yalnizca beklemeye alinyor; ekrana yazma karari ses
    // zamanlanirken veriliyor.
    const handler = SOURCE.slice(SOURCE.indexOf("frame.type === 'sentence'"), SOURCE.indexOf("frame.type === 'start'"))

    expect(handler).toContain('pendingSentence =')
    expect(handler).not.toContain('onSentence')
  })

  it('cumle sesin BASLAMA anina erteleniyor', () => {
    const schedule = SOURCE.slice(SOURCE.indexOf('const startAt ='), SOURCE.indexOf('nextStartAt = startAt'))

    expect(schedule).toContain('onSentence')
    expect(schedule).toContain('startAt - context.currentTime')
  })

  it('ayni cumle IKI KEZ bildirilmiyor', () => {
    // Bir cumle icin birden cok ses karesi gelebiliyor.
    const schedule = SOURCE.slice(SOURCE.indexOf('if (pendingSentence !== null)'), SOURCE.indexOf('nextStartAt = startAt'))

    expect(schedule).toContain('pendingSentence = null')
  })

  it('geri cagirim ISTEGE BAGLI', () => {
    // Sohbet paneli bunu kullanmiyor; zorunlu olsaydi her cagiran degismek
    // zorunda kalirdi.
    expect(SOURCE).toContain('onSentence?: (sentence: string) => void')
    expect(SOURCE).toContain('options.onSentence?.(')
  })
})
