/**
 * Çentik modelin CEVABINI da yazmalı.
 *
 * Ölçülen boşluk: ``use-notch-voice`` ``reply``i baştan beri tutuyordu, arayüze
 * veriyordu (``NotchVoice.reply``) ve model konuştukça cümle cümle
 * güncelliyordu (``onSentence: sentence => setReply(sentence)``). Ama
 * ``notch-shell.tsx`` onu HİÇ çizmiyordu: çentik senin ne dediğini gösterip
 * modelin ne cevapladığını hiç göstermiyordu.
 *
 * Sessiz değil, KULLANILAMAZ bir boşluk. Ses kaçtığı anda (gürültü, kulaklık
 * çıkmış, ses kapalı, hoparlör başka cihazda) turdan geriye hiçbir şey
 * kalmıyor -- kullanıcı modelin cevap verip vermediğini bile bilemiyor. Bir
 * sesli arayüzün metni, duyulmayan her cevabın tek kaydıdır.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const read = (name: string) => readFileSync(join(__dirname, name), 'utf8')

const SHELL = read('notch-shell.tsx')
const HOOK = read('use-notch-voice.ts')

const COMPOSER = readFileSync(
  join(__dirname, '..', '..', 'app', 'chat', 'composer', 'hooks', 'use-auto-speak-replies.ts'),
  'utf8'
)

describe('centik modelin cevabini gosteriyor', () => {
  it('cevap PAYLASILAN atomdan geliyor', () => {
    // Centik kendi ``$messages``inden karar veriyordu ve o liste ana
    // pencerenin bir tur gerisindeydi: seritte ESKI cevap goruluyordu.
    // Konusan taraf kim ise serit metnini de o yayinliyor.
    expect(HOOK).toContain('reply: string')
    expect(HOOK).toContain('useStore($spokenSubtitle)')
  })

  it('cevap KONUSULDUKCA guncelleniyor', () => {
    // Tur bitince tek seferde yazmak, uzun bir cevabin tamamlanmasini
    // beklemek demekti. Serit artik cumlenin DUYULMUS kismi kadar aciliyor ve
    // yayinlayan taraf KONUSAN taraf: ana pencere.
    expect(COMPOSER).toContain('onSentenceProgress: (sentence, ratio) =>')
    expect(COMPOSER).toContain('setSpokenSubtitle(spokenSubtitle(sentence, ratio))')
  })

  it('SERIT dogrudan metni ciziyor', () => {
    // ``NotchText`` kaldirildi: dalga formu + durum + dugme yigini 22
    // piksellik kucuk hale sigmiyordu ve zaten istenmiyordu. Serit artik tek
    // is yapiyor -- konusulani yazmak.
    expect(SHELL).toContain('{voice.reply}')
    expect(SHELL).not.toContain('<NotchText')
  })

  it('SOYLENECEK bir sey yokken serit ACILMIYOR', () => {
    expect(SHELL).toContain('const subtitleMode = Boolean(voice.reply)')
  })
})
