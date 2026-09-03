/**
 * Çentikteki düğme GERÇEKTEN tıklanabilir olmalı — ve çentik ekranın üstünü
 * yutmamalı.
 *
 * Ölçülen kırıklık: ana süreç çentiği koşulsuz tıkla-geçir yapıyor ve bir daha
 * hiç kapatmıyordu. PTT düğmesi çiziliyor, hover efekti veriyor, ipucu
 * gösteriyor -- tıklanınca hiçbir şey olmuyordu. Yanındaki yorum
 * ``pointerEvents: 'auto'`` ile bunun çözüldüğünü söylüyordu; çözmüyor, çünkü
 * o SAYFA düzeyinde bir özellik ve tıklama sayfaya hiç ulaşmıyor.
 *
 * İkinci kural birincisi kadar önemli: çentik ekranın en üst kenarında duruyor
 * ve orada tarayıcı sekmeleri, menü çubuğu, pencere düğmeleri var. Düğmeyi
 * çalışır kılmak uğruna oraları yutmak, çözülenden büyük bir hata olurdu.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { NOTCH_INTERACTIVE_ATTR, notchIgnoresMouse } from './click-through'

/** Gerçek DOM: ``closest`` zinciri tam da sınanan şey. */
const mark = (html: string): Element => {
  const host = document.createElement('div')
  host.innerHTML = html

  return host.firstElementChild as Element
}

describe('karar', () => {
  it('ISARETLI ogenin uzerinde pencere KATI', () => {
    const button = mark(`<button ${NOTCH_INTERACTIVE_ATTR}>PTT</button>`)

    expect(notchIgnoresMouse(button)).toBe(false)
  })

  it('isaretli ogenin ICINDEKI oge de katilastiriyor', () => {
    // Dugmenin icinde bir ikon ya da metin dugumu olabilir; hit-test onu
    // dondurur ve ``closest`` zinciri yukari yurumezse dugme yine olurdu.
    const wrapper = mark(`<div ${NOTCH_INTERACTIVE_ATTR}><span><b>PTT</b></span></div>`)
    const inner = wrapper.querySelector('b')

    expect(notchIgnoresMouse(inner)).toBe(false)
  })

  it('ISARETSIZ her sey GECIRGEN', () => {
    // Centigin govdesi, dalga formu, durum metni -- hicbiri tiklanmiyor ve
    // hicbiri altindakini engellememeli.
    expect(notchIgnoresMouse(mark('<div class="waveform"></div>'))).toBe(true)
    expect(notchIgnoresMouse(mark('<p>listening</p>'))).toBe(true)
  })

  it('IMLEC bilinmiyorsa GECIRGEN', () => {
    // Bilinmeyende kati kalmak, centigin ekranin ust kenarini suresiz
    // yutmasi demek olurdu -- imlec baska bir uygulamaya gectikten sonra bile.
    expect(notchIgnoresMouse(null)).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// Dikisler
// ---------------------------------------------------------------------------

const read = (...parts: string[]) => readFileSync(join(__dirname, ...parts), 'utf8')

describe('dikisler bagli', () => {
  it('ana surecin bir KAPISI var', () => {
    // Pet overlay ve HUD'un vardi, centigin YOKTU: cagri bir kez yapilip bir
    // daha hic kapatilmiyordu.
    const main = read('..', '..', '..', 'electron', 'main.ts')

    expect(main).toContain("ipcMain.on('fool:notch:ignore-mouse'")
    // ``forward`` sart: gecirgenken de mousemove gelmeye devam etmeli, yoksa
    // imlec dugmeye geldiginde yeniden katilasmayi tetikleyecek olay olmaz.
    const handler = main.slice(main.indexOf("ipcMain.on('fool:notch:ignore-mouse'"))

    expect(handler.slice(0, 400)).toContain('forward: true')
  })

  it('kapi YALNIZCA centigin kendi rendererindan surulebiliyor', () => {
    // Baska bir pencere centigi katilastirabilseydi, ekranin ust kenarini
    // yutan bir serit birakabilirdi.
    const main = read('..', '..', '..', 'electron', 'main.ts')
    const handler = main.slice(main.indexOf("ipcMain.on('fool:notch:ignore-mouse'"))

    expect(handler.slice(0, 400)).toContain('event.sender === notchWindow.webContents')
  })

  it('ISARETLI ogeler icin kapi ACIK kaliyor', () => {
    // Centikte SU AN isaretli bir oge yok: kip dugmesi kaldirildi, cunku
    // dinleme hali kucuk kaliyor ve ona yer yok. Mekanizma yerinde duruyor ve
    // bir dugme geri geldiginde calisacak -- kapi ISLETIM SISTEMI katmaninda
    // ve ``pointerEvents`` tek basina hicbir sey yapmiyordu.
    const module = readFileSync(join(__dirname, 'click-through.ts'), 'utf8')

    expect(module).toContain('NOTCH_INTERACTIVE_ATTR')
    expect(module).toContain('setIgnoreMouseEvents')
  })

  it('kanca centige TAKILI', () => {
    expect(read('notch-shell.tsx')).toContain('useNotchClickThrough()')
  })

  it('pencere GECIRGEN basliyor', () => {
    // Katı başlamak, renderer daha hiçbir şey çizmeden ekranın üst kenarını
    // yutmak olurdu.
    const main = read('..', '..', '..', 'electron', 'main.ts')
    const spawn = main.slice(main.indexOf('function spawnNotchWindow'))

    expect(spawn.slice(0, 3000)).toContain('win.setIgnoreMouseEvents(true, { forward: true })')
  })
})
