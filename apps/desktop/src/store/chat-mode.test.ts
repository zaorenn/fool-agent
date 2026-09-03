/**
 * Chat ↔ Cowork kipi arayüz tarafı.
 *
 * Kip oturumun ``source`` alanında yaşıyor ve ağ geçidi zaten onu okuyup araç
 * kapsamını seçiyor. Bu dosya yeni bir hakikat kaynağı eklemediğini -- var
 * olanı doğru okuduğunu -- tutuyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { beforeEach, describe, expect, it } from 'vitest'

import { $selectedStoredSessionId, $sessions } from '@/store/session'

import {
  $chatSimpleSidebar,
  $newChatMode,
  CHAT_SOURCE,
  COWORK_SOURCE,
  modeOfSession,
  modeOfSource
} from './chat-mode'

const session = (id: string, source: null | string) =>
  ({ id, source, title: id }) as unknown as (typeof $sessions.value)[number]

beforeEach(() => {
  $sessions.set([])
  $selectedStoredSessionId.set(null)
  $newChatMode.set('cowork')
})

describe('kaynaktan kip', () => {
  it('chat kaynagi Chat kipi', () => {
    expect(modeOfSource('chat')).toBe('chat')
    expect(modeOfSource('CHAT')).toBe('chat')
    expect(modeOfSource('  chat  ')).toBe('chat')
  })

  it('diger her sey Cowork', () => {
    // KISITLAMAYI VARSAYMAK yanlis yon: tanimadigimiz bir kaynagi Chat sayip
    // kullanicinin aracini sessizce elinden almak, tersinden cok daha kotu.
    for (const source of ['desktop', 'tui', 'cli', 'telegram', '', null, undefined]) {
      expect(modeOfSource(source)).toBe('cowork')
    }
  })
})

describe('oturumdan kip', () => {
  it('oturumun kaynagini okuyor', () => {
    $sessions.set([session('s1', CHAT_SOURCE), session('s2', COWORK_SOURCE)])

    expect(modeOfSession('s1')).toBe('chat')
    expect(modeOfSession('s2')).toBe('cowork')
  })

  it('HENUZ LISTEDE OLMAYAN oturum yeni sohbet tercihini izliyor', () => {
    // Olculen kiriklik: kullanici Chat kipinde yeni sohbet ekranindayken
    // centikten konusuyor, ana pencere oturumu olusturuyor ve secim ona
    // geciyor -- ama ``$sessions`` henuz tazelenmemis oluyor. Liste onu
    // tanimadigi icin anahtar bir anda Cowork'e atliyordu.
    $newChatMode.set('chat')

    expect(modeOfSession('henuz-yok')).toBe('chat')
    expect(modeOfSession(null)).toBe('chat')

    $newChatMode.set('cowork')

    expect(modeOfSession('henuz-yok')).toBe('cowork')
  })

  it('BILINEN oturumun kaynagi kazaniyor', () => {
    // Dusme yalnizca liste onu gorene kadar gecerli.
    $newChatMode.set('chat')
    $sessions.set([session('s1', COWORK_SOURCE)])

    expect(modeOfSession('s1')).toBe('cowork')
  })
})

describe('kenar cubugu sadelesmesi', () => {
  it('Chat kipindeki sohbette ACIK', () => {
    $sessions.set([session('s1', CHAT_SOURCE)])
    $selectedStoredSessionId.set('s1')

    expect($chatSimpleSidebar.get()).toBe(true)
  })

  it('Cowork sohbetinde KAPALI', () => {
    $sessions.set([session('s1', COWORK_SOURCE)])
    $selectedStoredSessionId.set('s1')

    expect($chatSimpleSidebar.get()).toBe(false)
  })

  it('HIC sohbet acik degilse yeni sohbet tercihini izliyor', () => {
    expect($chatSimpleSidebar.get()).toBe(false)

    $newChatMode.set('chat')

    // Kullanici Chat kipini sectiyse kenar cubugu onu GOSTERMELI, ilk mesaji
    // beklemeden.
    expect($chatSimpleSidebar.get()).toBe(true)
  })

  it('YENI olusan oturumda Cowork tarafina ATLAMIYOR', () => {
    // Liste henuz tazelenmemisken kenar cubugu bir an acilip kapaniyordu.
    $newChatMode.set('chat')
    $selectedStoredSessionId.set('henuz-listede-yok')

    expect($chatSimpleSidebar.get()).toBe(true)
  })

  it('sohbet degisince TAKIP ediyor', () => {
    $sessions.set([session('s1', CHAT_SOURCE), session('s2', COWORK_SOURCE)])
    $selectedStoredSessionId.set('s1')

    expect($chatSimpleSidebar.get()).toBe(true)

    $selectedStoredSessionId.set('s2')

    expect($chatSimpleSidebar.get()).toBe(false)
  })
})

describe('Cowork kaynagi', () => {
  it("``'cowork'`` DEGIL, ``desktop``", () => {
    // Ag gecidi ``source``u kapsam cozumlemesinde kullaniyor ve ``desktop``
    // masaustunun olagan kapsami. ``'cowork'`` yazmak taninmayan bir kapsam
    // uretirdi -- bugun zararsiz, ama ileride biri o adi gercek bir kapsam
    // yaptiginda kip anlamini degistirirdi.
    expect(COWORK_SOURCE).toBe('desktop')
    expect(CHAT_SOURCE).toBe('chat')
  })
})

describe('dikisler', () => {
  const read = (...parts: string[]) => readFileSync(join(__dirname, ...parts), 'utf8')

  it('kenar cubugu kapiyi UYGULUYOR', () => {
    const sidebar = read('..', 'app', 'chat', 'sidebar', 'index.tsx')

    expect(sidebar).toContain('$chatSimpleSidebar')
    // Gruplama Chat kipinde kapali: proje seritleri "sadece sohbetler"in
    // tam tersi.
    expect(sidebar).toContain("grouping === 'project' && !chatSimple")
    // Zamanlanmis isler ve pinler de gizleniyor.
    expect(sidebar).toContain('!chatSimple && cronJobs.length > 0')
  })

  it('anahtar kenar cubugunun TEPESINDE', () => {
    const sidebar = read('..', 'app', 'chat', 'sidebar', 'index.tsx')
    const at = sidebar.indexOf('<ChatModeSwitch />')
    const menu = sidebar.indexOf('<SidebarMenu className="gap-px">')

    expect(at).toBeGreaterThan(-1)
    expect(at).toBeLessThan(menu)
  })

  it('degisim ONAY istiyor', () => {
    // Sessizce yapmak, kullanicinin sebebini anlamadigi yavas bir tur demekti.
    const switcher = read('..', 'app', 'chat', 'sidebar', 'chat-mode-switch.tsx')

    expect(switcher).toContain('ConfirmDialog')
    expect(switcher).toContain('setSessionMode')
  })

  it('ses hapi COMPOSERDA ve her kipte', () => {
    // Ilk yazimda durum cubuguna koydum ve kullanici bulamadi: "ekranimda
    // herhangi bir yerde yok". Baktigi yer composer -- model secimini de
    // oradan yapiyor. Kipe bagli DEGIL: "hem cowork hem chatte".
    const controls = read('..', 'app', 'chat', 'composer', 'controls.tsx')

    expect(controls).toContain('<VoicePill')
    expect(controls).not.toContain('chatSimple')
  })

  it('CALISMAYAN motor ve sesleri secilemiyor', () => {
    // Kullanicinin kurali: "kesinlikle calistigi emin olunmayan ses tipleri
    // calisiyormus gibi secim acik olmamali."
    const pill = read('..', 'fool', 'voice-pill.tsx')

    expect(pill).toContain('blockedReason')
    // Kapi ``installed`` degil ``usable``: paket yerinde ama motor ice
    // aktarilamiyorsa secim sessizce calismayan bir motora gecmek olurdu.
    expect(pill).toContain('item.usable')
    // Sesler yalnizca CALISAN motordan.
    expect(pill).toContain('!blockedReason(activeTts)')
  })
})
