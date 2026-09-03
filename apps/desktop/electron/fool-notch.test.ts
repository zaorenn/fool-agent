/**
 * Notch geometrisi ve URL sözleşmesinin testleri.
 *
 * ``hud-url.test.ts`` ile aynı gerekçe: bu sözleşmeler bozulana kadar görünmez.
 * Yanlış bir sorgu dizesi pencereyi sessizce ANA uygulama olarak açar — notch
 * yerine tam bir sohbet penceresi ekranın üstüne yapışır.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  buildNotchWindowUrl,
  NOTCH_WINDOW_HEIGHT,
  NOTCH_WINDOW_WIDTH,
  notchBounds
} from './fool-notch'

describe('notchBounds', () => {
  it('ekranın üst kenarına yapışır', () => {
    // Havada asılı bir çentik, çentik değildir.
    const bounds = notchBounds({ height: 1080, width: 1920, x: 0, y: 0 })

    expect(bounds.y).toBe(0)
  })

  it('ekranin TAMAMINI kapliyor', () => {
    // Kullanicinin karari: alt yazi "monitorun en ust kenarinin tamamina
    // kadar genisleyebilsin, boylece modelin cevabi tamamen sigar". Pencereyi
    // tura gore buyutmek Windows'ta kare atlatiyor, o yuzden bastan genis.
    const bounds = notchBounds({ height: 1080, width: 1920, x: 0, y: 0 })

    expect(bounds.x).toBe(0)
    expect(bounds.width).toBe(1920)
    expect(bounds.height).toBe(NOTCH_WINDOW_HEIGHT)
  })

  it('olcu okunamazsa SABIT genislige dusuyor', () => {
    // Sifir genislikte bir pencere centigi tamamen gorunmez yapardi.
    const bounds = notchBounds({ height: 0, width: 0, x: 0, y: 0 })

    expect(bounds.width).toBe(NOTCH_WINDOW_WIDTH)
  })

  it('ikinci ekranın kendi başlangıcına göre ortalar', () => {
    // Soldaki ekranın x'i negatif olabiliyor; mutlak koordinat kullanmak
    // notch'u yanlış monitöre koyardı.
    const bounds = notchBounds({ height: 1080, width: 1920, x: -1920, y: 0 })

    expect(bounds.x).toBe(-1920)
  })

  it('dikey ofseti olan ekranın üstüne oturur', () => {
    const bounds = notchBounds({ height: 1440, width: 2560, x: 0, y: -1440 })

    expect(bounds.y).toBe(-1440)
  })
})

describe('buildNotchWindowUrl', () => {
  it("dev sunucuda ?win=notch'u '#' ÖNCESİNE koyar", () => {
    // Sorgu '#' sonrasına düşerse HashRouter onu rotanın parçası sanar ve
    // pencere kendini notch olarak tanımaz.
    const url = buildNotchWindowUrl({ devServer: 'http://127.0.0.1:5174' })

    expect(url).toBe('http://127.0.0.1:5174/?win=notch#/')
    expect(url.indexOf('win=notch')).toBeLessThan(url.indexOf('#'))
  })

  it('dev sunucunun sondaki eğik çizgisini iki katına çıkarmaz', () => {
    expect(buildNotchWindowUrl({ devServer: 'http://127.0.0.1:5174/' })).toBe(
      'http://127.0.0.1:5174/?win=notch#/'
    )
  })

  it('profili sorgu dizesinde taşır', () => {
    const url = buildNotchWindowUrl({ devServer: 'http://x', profile: 'iş' })

    expect(url).toContain(`profile=${encodeURIComponent('iş')}`)
    expect(url.indexOf('profile=')).toBeLessThan(url.indexOf('#'))
  })

  it('boş profil eklemez', () => {
    expect(buildNotchWindowUrl({ devServer: 'http://x', profile: '   ' })).toBe('http://x/?win=notch#/')
  })

  it('paketlenmiş yapıda file:// URL üretir', () => {
    const url = buildNotchWindowUrl({ rendererIndexPath: 'C:/app/dist/index.html' })

    expect(url.startsWith('file:///')).toBe(true)
    expect(url).toContain('?win=notch#/')
  })
})

// ---------------------------------------------------------------------------
// FOOL-SEAM: notch-profile
// ---------------------------------------------------------------------------

describe('centik profili', () => {
  it('profil verildiginde sorgu dizesinde TASINIYOR', () => {
    const url = buildNotchWindowUrl({ devServer: 'http://127.0.0.1:5174', profile: 'companion' })

    expect(url).toContain('profile=companion')
    expect(url.indexOf('profile=')).toBeLessThan(url.indexOf('#'))
  })

  it('profil adi KACISLANIYOR', () => {
    const url = buildNotchWindowUrl({ devServer: 'http://x', profile: 'a b&c' })

    expect(url).toContain('profile=a%20b%26c')
  })

  it('cagiran taraf profili GERCEKTEN veriyor', () => {
    // Olculen hata: ``buildNotchWindowUrl`` parametreyi kabul ediyordu ama tek
    // cagiran onu hic gecmiyordu. Centik birincil arka uca baglaniyor,
    // kullanicinin acik sohbetini goremiyor ve ekranda sohbet dururken
    // "No chat is open yet" yaziyordu.
    const chr10 = String.fromCharCode(10)
    const SLASHES = '//'
    const main = readFileSync(join(__dirname, 'main.ts'), 'utf8')
    // Yorumlar cikariliyor: sinanan sey ARGUMANIN gecilmesi, cagrinin kac
    // karakter uzun oldugu degil.
    const code = main.split(chr10).filter(line => !line.trim().startsWith(SLASHES)).join(chr10)
    const call = code.slice(code.indexOf('buildNotchWindowUrl({'))
    const args = call.slice(0, call.indexOf('})') + 2)

    expect(args).toContain('profile:')
  })
})
