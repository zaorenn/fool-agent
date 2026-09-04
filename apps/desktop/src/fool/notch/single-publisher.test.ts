/**
 * Çentik AYNI bundle'ı yüklüyor — yayın yapan her modül bunu bilmeli.
 *
 * Bu bir HATA SINIFI, tek bir hata değil. Çentik ayrı bir ``BrowserWindow``
 * ama ``?win=notch`` ile aynı paketi çalıştırıyor (bkz.
 * ``electron/fool-notch.ts::buildNotchWindowUrl`` ve
 * ``app/contrib/controller.tsx``). Yani içe aktarma anında yan etkisi olan
 * her modül İKİ KEZ koşuyor: bir kez ana pencerede, bir kez çentikte.
 *
 * Değer PENCEREYE ÖZELSE bu zararsız (düzen, besteci, gözden geçirme).
 * Değer PAYLAŞILAN bir yere yazılıyorsa -- pencereler arası ``sharedAtom`` ya
 * da ana süreç -- çentiğin boş kopyası ana pencerenin gerçeğini EZİYOR.
 *
 * İki kez yaşandı:
 *
 *   1. ``$voiceSessionId``: çentik kendi boş ``$activeSessionId``ini
 *      yayınlayıp ana pencerenin açık oturumunu eziyordu. Ses ``session_id:
 *      null`` ile gidiyor, cevap bot panelinde çıkıyordu.
 *   2. ``setActiveWork``: çentikte ``$sessions`` boş, yani ``count: 0``
 *      yayınlıyor. Çıkış muhafızı süren turu görmüyor ve
 *      ``electron/stream-throttle.ts`` pencereleri akış ortasında yeniden
 *      kısıyor.
 *
 * Bu sınav kaynağı okuyor. Yeni bir yayıncı guard'sız eklenirse burada
 * kırılır -- kullanıcının ekranında değil.
 */

import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const STORE_DIR = join(import.meta.dirname, '../../store')

/** Pencere sınırını GEÇEN yazma yolları. */
const CROSS_BOUNDARY = [
  // Ana surece giden yayinlar.
  'foolDesktop?.setActiveWork',
  'foolDesktop?.setKeepAwake',
  'foolDesktop?.setTranslucency',
  // Pencereler arasi paylasilan atom.
  '$voiceSessionId.set'
]

function storeFiles(): string[] {
  return readdirSync(STORE_DIR)
    .filter(name => name.endsWith('.ts') && !name.endsWith('.test.ts'))
    .map(name => join(STORE_DIR, name))
}

describe('sinir gecen yayinci YALNIZCA ana pencerede', () => {
  it('her yayinci centikte susuyor', () => {
    const offenders: string[] = []

    for (const path of storeFiles()) {
      const source = readFileSync(path, 'utf8')
      const publishes = CROSS_BOUNDARY.some(sink => source.includes(sink))

      if (!publishes) {
        continue
      }

      // Ortak yardimci ya da dogrudan guard -- ikisi de kabul.
      if (!source.includes('whenMainWindow') && !source.includes('isNotchWindow')) {
        offenders.push(path.split(/[\\/]/).pop() ?? path)
      }
    }

    expect(
      offenders,
      `Bu modul(ler) pencere sinirini gecen bir yayin yapiyor ama centikte ` +
        `susmuyor: ${offenders.join(', ')}. Centik ayni bundle'i yukluyor, ` +
        `yani bos kopyasi ana pencerenin degerini ezer.`
    ).toEqual([])
  })

  /** Sınavın dayandığı olgu: çentik gerçekten aynı paketi çalıştırıyor. */
  it('centik AYNI bundle ile aciliyor', () => {
    const controller = readFileSync(join(import.meta.dirname, '../../app/contrib/controller.tsx'), 'utf8')

    expect(controller.includes('isNotchWindow()')).toBe(true)
    expect(controller.includes('<NotchShell />')).toBe(true)
  })

  it('bilinen iki yayinci guardli', () => {
    const activeWork = readFileSync(join(STORE_DIR, 'active-work.ts'), 'utf8')

    // Oturum koprusu VE is ozeti -- ikisi de.
    expect(activeWork.includes('$voiceSessionId')).toBe(true)
    expect(activeWork.includes('setActiveWork')).toBe(true)
    expect((activeWork.match(/whenMainWindow/g) ?? []).length).toBeGreaterThanOrEqual(2)
  })
})
