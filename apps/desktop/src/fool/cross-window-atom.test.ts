/**
 * Paylaşılan atomlar BAŞKA pencerenin yazdığını benimsiyor mu?
 *
 * Bu testler var çünkü hata sessizdi: değer diske yazılıyordu, ikinci pencere
 * yazmayı hiç duymuyordu ve her iki taraftaki yorum da duyduğunu söylüyordu.
 * Ölçülen hâli: depo ``KeyQ``, notch penceresindeki atom ``ControlRight``.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { afterEach, beforeEach, describe, expect, it } from 'vitest'

/** Başka bir pencere bu anahtarı yazdı: tarayıcının BİZE yolladığı olay. */
function writeFromAnotherWindow(key: string, newValue: null | string): void {
  if (newValue === null) {
    window.localStorage.removeItem(key)
  } else {
    window.localStorage.setItem(key, newValue)
  }

  window.dispatchEvent(
    new StorageEvent('storage', { key, newValue, storageArea: window.localStorage })
  )
}

describe('pencereler arasi paylasilan atom', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('bas-konus baglamasi diger pencereden geliyor', async () => {
    const { $pttCode } = await import('./notch/ptt-store')

    writeFromAnotherWindow('fool.desktop.notch.pushToTalkCode', 'KeyQ')

    expect($pttCode.get()).toBe('KeyQ')
  })


  it('dinleme kipi diger pencereden geliyor', async () => {
    const { $listenMode } = await import('./notch/listen-mode')

    writeFromAnotherWindow('fool.desktop.voice.listen-mode', 'push-to-talk')

    expect($listenMode.get()).toBe('push-to-talk')
  })


  it('anahtar SILINDIYSE varsayilana donuyor', async () => {
    const { $pttCode } = await import('./notch/ptt-store')

    $pttCode.set('KeyQ')
    writeFromAnotherWindow('fool.desktop.notch.pushToTalkCode', null)

    expect($pttCode.get()).toBe('ControlRight')
  })

  it('ILGISIZ anahtar atomu kimildatmiyor', async () => {
    const { $pttCode } = await import('./notch/ptt-store')

    $pttCode.set('KeyQ')
    writeFromAnotherWindow('bambaska.bir.anahtar', 'KeyZ')

    expect($pttCode.get()).toBe('KeyQ')
  })
})

/**
 * Asıl koruma: notch penceresinden OKUNAN her kalıcı fool atomu paylaşılmalı.
 *
 * Yukarıdaki testler üç atomu tek tek sınıyor. Dördüncüsü eklenip
 * ``persistentAtom`` ile yazılırsa hiçbiri kırılmaz -- ilk hata da böyle
 * girmişti. Bu test kaynağı okuyor.
 */
describe('notch penceresindeki atomlar paylasilan kaynaktan', () => {
  const HERE = import.meta.dirname
  const NOTCH_FILES = ['notch/notch-shell.tsx', 'notch/use-notch-voice.ts']

  it('notch hicbir yerde ciplak persistentAtom kullanmiyor', () => {
    for (const relative of NOTCH_FILES) {
      const source = readFileSync(join(HERE, relative), 'utf8')
      const stores = [...source.matchAll(/from '(\.[^']*)'/g)].map(match => match[1])

      for (const store of stores) {
        const path = join(HERE, 'notch', `${store}.ts`)
        let storeSource: string

        try {
          storeSource = readFileSync(path, 'utf8')
        } catch {
          continue
        }

        expect(
          /persistentAtom\s*[<(]/.test(storeSource),
          `${store} kalici degeri persistentAtom ile tutuyor: notch penceresine ulasmaz`
        ).toBe(false)
      }
    }
  })
})

// ---------------------------------------------------------------------------
// FOOL-SEAM: shared-window-values
//
// ``localStorage`` gelistirmede paylasiliyor (ayni ``http`` kokeni) ama
// paketlenmis surumde DEGIL: iki pencere de ``file://`` yukluyor ve Chromium
// ``file:`` belgelerine ayri depolar veriyor. Yani bu kopru tam da YAYINLANAN
// uygulamada oluydu -- centik acik sohbeti bulamiyordu.
// ---------------------------------------------------------------------------

describe('masaustu koprusu', () => {
  const codec = { decode: (raw: string) => raw, encode: (value: string) => value }

  function bridge() {
    const listeners: ((p: { key: string; value: string }) => void)[] = []
    const sent: { key: string; value: string }[] = []
    let stored = ''

    return {
      sent,
      emit: (key: string, value: string) => listeners.forEach(fn => fn({ key, value })),
      seed: (value: string) => (stored = value),
      api: {
        get: async () => stored,
        set: async (key: string, value: string) => {
          sent.push({ key, value })

          return { ok: true }
        },
        onChange: (fn: (p: { key: string; value: string }) => void) => {
          listeners.push(fn)

          return () => undefined
        }
      }
    }
  }

  afterEach(() => {
    delete (window as unknown as { foolDesktop?: unknown }).foolDesktop
  })

  it('ACILISTA mevcut degeri aliyor', async () => {
    // Centik SONRADAN aciliyor ve oturum kimligi genellikle ONCE yazilmis
    // oluyor; yalnizca degisimleri dinlemek o degeri hic gormemek demekti.
    const b = bridge()

    b.seed('live-1')
    ;(window as unknown as { foolDesktop: unknown }).foolDesktop = { shared: b.api }

    const { sharedAtom } = await import('./cross-window-atom')

    const $atom = sharedAtom<string>('fool.test.seed', '', codec)

    await new Promise(resolve => setTimeout(resolve, 0))

    expect($atom.get()).toBe('live-1')
  })

  it('DISARIDAN gelen degisimi benimsiyor', async () => {
    const b = bridge()

    ;(window as unknown as { foolDesktop: unknown }).foolDesktop = { shared: b.api }

    const { sharedAtom } = await import('./cross-window-atom')

    const $atom = sharedAtom<string>('fool.test.incoming', '', codec)

    await new Promise(resolve => setTimeout(resolve, 0))
    b.emit('fool.test.incoming', 'from-other-window')

    expect($atom.get()).toBe('from-other-window')
  })

  it('KENDI yazisini koprue gonderiyor', async () => {
    const b = bridge()

    ;(window as unknown as { foolDesktop: unknown }).foolDesktop = { shared: b.api }

    const { sharedAtom } = await import('./cross-window-atom')

    const $atom = sharedAtom<string>('fool.test.outgoing', '', codec)

    await new Promise(resolve => setTimeout(resolve, 0))
    $atom.set('mine')

    expect(b.sent.at(-1)).toEqual({ key: 'fool.test.outgoing', value: 'mine' })
  })

  it('gelen degeri GERI yayinlamiyor', async () => {
    // Yoksa iki pencere birbirinin yazisini sonsuza kadar geri yollardi.
    const b = bridge()

    ;(window as unknown as { foolDesktop: unknown }).foolDesktop = { shared: b.api }

    const { sharedAtom } = await import('./cross-window-atom')

    const $atom = sharedAtom<string>('fool.test.echo', '', codec)

    await new Promise(resolve => setTimeout(resolve, 0))
    const before = b.sent.length

    b.emit('fool.test.echo', 'incoming')

    expect(b.sent.length).toBe(before)
  })

  it('ILGISIZ anahtari yok sayiyor', async () => {
    const b = bridge()

    ;(window as unknown as { foolDesktop: unknown }).foolDesktop = { shared: b.api }

    const { sharedAtom } = await import('./cross-window-atom')

    const $atom = sharedAtom<string>('fool.test.mine', 'start', codec)

    await new Promise(resolve => setTimeout(resolve, 0))
    b.emit('fool.test.other', 'nope')

    expect($atom.get()).toBe('start')
  })
})
