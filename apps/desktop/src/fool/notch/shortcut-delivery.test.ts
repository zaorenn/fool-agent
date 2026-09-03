/**
 * Kısayol niyeti KAYBOLMAMALI ve İKİ KEZ işlenmemeli.
 *
 * Ölçülen hata: ``spawnNotchWindow()`` pencereyi oluşturup hemen dönüyor ve
 * ``webContents.send('fool:notch:listen')`` renderer daha
 * ``ipcRenderer.on(...)`` çağırmadan gidiyor. İlk basışta mesaj DÜŞÜYOR.
 *
 * Kullanıcının gördüğü tam olarak buydu: "ctrl alt v 2. kez basışımda ses
 * algılıyor". Üstüne renderer'daki aç/kapa mantığı doğruydu ama ilk mesaj
 * kaybolunca sayaç BİR KAYIYORDU -- ilk basış hiçbir şey, ikinci açma,
 * üçüncü kapama.
 *
 * Çözüm çekme yöntemi: renderer montajda bekleyen niyeti alıyor. Gönderme
 * yöntemi yarışıyor -- ``did-finish-load`` bile React'in efektini
 * çalıştırdığını garanti etmiyor.
 *
 * Bu sınav kaynağı okuyor: Electron ana süreci burada ayağa kaldırılamaz.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const MAIN = readFileSync(join(import.meta.dirname, '../../../electron/main.ts'), 'utf8')
const SHELL = readFileSync(join(import.meta.dirname, 'notch-shell.tsx'), 'utf8')
const PRELOAD = readFileSync(join(import.meta.dirname, '../../../electron/preload.ts'), 'utf8')

/** ``fireNotchShortcut`` gövdesi. */
const FIRE = MAIN.slice(
  // Imza artik KIP aliyor (uyandirma 'wake' ile cagiriyor), o yuzden capa
  // parantezsiz.
  MAIN.indexOf('function fireNotchShortcut('),
  MAIN.indexOf('ipcMain.handle(\'fool:notch:take-intent\'')
)

describe('kisayol niyeti', () => {
  it('yeni acilan pencerede BEKLETILIYOR', () => {
    expect(FIRE.includes('pendingNotchIntent = intent')).toBe(true)
  })

  /**
   * Hem gönderip hem bekletmek niyetin iki kez işlenmesi olurdu -- yani
   * aç/kapa'nın aynı basışta gerçekleşmesi, kullanıcı için "hiçbir şey
   * olmuyor".
   */
  it('TEK teslimat yolu seciliyor -- gonderme ve bekletme birlikte DEGIL', () => {
    const sendIndex = FIRE.indexOf("webContents.send('fool:notch:listen'")
    const pendIndex = FIRE.indexOf('pendingNotchIntent = intent')

    expect(sendIndex).toBeGreaterThan(-1)
    expect(pendIndex).toBeGreaterThan(-1)
    // Gonderme dali ERKEN donuyor, yani ikisi ayni yolda degil.
    expect(FIRE.slice(sendIndex, pendIndex)).toContain('return')
  })

  it('gonderme yalnizca pencere HAZIRKEN yapiliyor', () => {
    expect(FIRE.includes('isLoading()')).toBe(true)
  })

  it('bekleyen niyet alinabiliyor ve TUKETILIYOR', () => {
    const handler = MAIN.slice(MAIN.indexOf("ipcMain.handle('fool:notch:take-intent'"))

    expect(handler.slice(0, 400)).toContain('pendingNotchIntent = null')
  })

  it('preload cekme yolunu aciyor', () => {
    expect(PRELOAD).toContain('fool:notch:take-intent')
    expect(PRELOAD).toContain('takeListenRequest')
  })

  it('notch montajda bekleyen niyeti aliyor', () => {
    expect(SHELL).toContain('takeListenRequest')
  })

  /**
   * İki yol da AYNI işleyiciye gitmeli: ayrı yazmak, birinin aç/kapa
   * sayacını kaçırması demek olurdu.
   */
  it('iki yol da AYNI isleyiciyi cagiriyor', () => {
    expect(SHELL).toContain('onListenRequest?.(handleListenRequest)')
    expect(SHELL).toContain('handleListenRequest(pending)')
  })
})
