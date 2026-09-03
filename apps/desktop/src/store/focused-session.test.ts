/**
 * Ses ODAKTAKI sohbete gitmeli.
 *
 * Kullanıcının bildirdiği: "notch her zaman odaktaki sessiona bağlı olmalı,
 * kullanıcı yeni sessionda notchu kullanırsa o sessiona gitmeli mesaj."
 *
 * Ölçülen sebep: köprü (``store/active-work.ts``) ``$activeSessionId``i olduğu
 * gibi yayınlıyordu ve o, ÇALIŞMA ALANI bölmesinin oturumu. Kullanıcı başka
 * bir kutucuğa geçince ses hâlâ eski oturuma gidiyordu; yeni açılmış ama henüz
 * başlamamış bir sohbette ise bir öncekinin kimliği yayında kalıyor ve mesaj
 * oraya düşüyordu.
 *
 * HUD aynı tuzağa düşmüş, öğrenmiş ve kendi çözümleyicisini yazmıştı; ders
 * kardeşine geçmemişti.
 *
 * İKİ KİMLİK UZAYI en kritik nokta ve bu dosya onu ayrı ayrı tutuyor:
 * saklanan kimlik yönlendirme için, canlı (``runtimeId``) ağ geçidi için.
 * Karıştırmak göndermeyi tümden bozar.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { beforeEach, describe, expect, it, vi } from 'vitest'

const activeComposer = vi.fn<() => string>(() => 'main')

vi.mock('@/app/chat/composer/focus', () => ({
  getActiveComposer: () => activeComposer()
}))

const { $activeSessionId, $selectedStoredSessionId } = await import('@/store/session')
const { $sessionTiles } = await import('@/store/session-states')
const { focusedRuntimeSessionId, focusedSessionId } = await import('@/store/focused-session')

beforeEach(() => {
  activeComposer.mockReturnValue('main')
  $activeSessionId.set(null)
  $selectedStoredSessionId.set(null)
  $sessionTiles.set([])
})

describe('canli (ag gecidi) oturum', () => {
  it('ana bolme odaktayken calisma alaninin canli oturumu', () => {
    $activeSessionId.set('runtime-main')

    expect(focusedRuntimeSessionId()).toBe('runtime-main')
  })

  it('KUTUCUK odaktayken O kutucugun canli oturumu', () => {
    // Regresyonun kendisi: burasi eskiden ``runtime-main`` donerdi ve ses
    // kullanicinin bakmadigi sohbete giderdi.
    $activeSessionId.set('runtime-main')
    $sessionTiles.set([{ runtimeId: 'runtime-tile', storedSessionId: 'stored-tile' }])
    activeComposer.mockReturnValue('tile:stored-tile')

    expect(focusedRuntimeSessionId()).toBe('runtime-tile')
  })

  it('kutucuk HENUZ baslamadiysa CALISMA ALANINA dusuyor', () => {
    // Once bos donuyordu ve o, centigi "yeni oturum ac" yoluna sokuyordu:
    // kullanicinin ekranda ACIK bir sohbeti dururken mesaj bambaska bir yere
    // gidiyordu. Kullanicinin kurali: "kullanici halihazirda bir session
    // penceresindeyse o sessiona gitmeli mesaj."
    $activeSessionId.set('runtime-main')
    $sessionTiles.set([{ storedSessionId: 'stored-tile' }])
    activeComposer.mockReturnValue('tile:stored-tile')

    expect(focusedRuntimeSessionId()).toBe('runtime-main')
  })

  it('TANINMAYAN kutucuk da calisma alanina dusuyor', () => {
    $activeSessionId.set('runtime-main')
    activeComposer.mockReturnValue('tile:hic-yok')

    expect(focusedRuntimeSessionId()).toBe('runtime-main')
  })

  it('CANLI kutucuk calisma alanini EZIYOR', () => {
    // Dusme yalnizca son care: odaktaki kutucuk canliysa mesaj ONA gider.
    $activeSessionId.set('runtime-main')
    $sessionTiles.set([{ runtimeId: 'runtime-tile', storedSessionId: 'stored-tile' }])
    activeComposer.mockReturnValue('tile:stored-tile')

    expect(focusedRuntimeSessionId()).toBe('runtime-tile')
  })

  it('hicbir yerde canli oturum yoksa BOS', () => {
    // Yalnizca burada bos: gercekten gidilecek bir oturum yok ve centik
    // "once bir tane ac" yolunu haklı olarak tetikliyor.
    expect(focusedRuntimeSessionId()).toBe('')
  })
})

describe('saklanan oturum -- AYRI kimlik uzayi', () => {
  it('kutucuk odaktayken kutucugun SAKLANAN kimligi', () => {
    $selectedStoredSessionId.set('stored-main')
    activeComposer.mockReturnValue('tile:stored-tile')

    expect(focusedSessionId()).toBe('stored-tile')
  })

  it('ana bolme odaktayken calisma alaninin saklanan kimligi', () => {
    $selectedStoredSessionId.set('stored-main')

    expect(focusedSessionId()).toBe('stored-main')
  })

  it('IKI cozumleyici ayni degeri DONDURMUYOR', () => {
    // Karistirmak gonderme yolunu bozar: ag gecidi canli kimlik istiyor,
    // yonlendirme saklanan kimlik. Bu test ikisinin ayri kaldigini gosteriyor.
    $activeSessionId.set('runtime-main')
    $selectedStoredSessionId.set('stored-main')

    expect(focusedRuntimeSessionId()).toBe('runtime-main')
    expect(focusedSessionId()).toBe('stored-main')
  })
})

describe('dikisler', () => {
  const read = (...parts: string[]) => readFileSync(join(__dirname, ...parts), 'utf8')

  it('ses koprusu CALISMA ALANINI degil ODAKTAKINI yayinliyor', () => {
    const bridge = read('active-work.ts')

    expect(bridge).toContain('focusedRuntimeSessionId()')
    // Eski hali geri gelirse burasi duser.
    expect(bridge).not.toContain("$activeSessionId.subscribe(id => $voiceSessionId.set(id ?? ''))")
  })

  it('kopru odak DEGISIMINI de dinliyor', () => {
    // Besteci odak yolu bir atom DEGIL: sekme/kutucuk gecisi hicbir atomu
    // degistirmeden odagi tasiyabiliyor. ``focusin`` tek reaktif sinyal.
    const bridge = read('active-work.ts')

    expect(bridge).toContain("addEventListener('focusin'")
  })

  it('HUD ayni kaynaktan okuyor -- ikinci kopya yok', () => {
    const hud = readFileSync(join(__dirname, '..', 'app', 'hud', 'handoff.ts'), 'utf8')

    expect(hud).toContain('focusedSessionId()')
    // Kendi kopyasi kalmamali.
    expect(hud).not.toContain("const TILE_TARGET_PREFIX = 'tile:'")
  })
})
