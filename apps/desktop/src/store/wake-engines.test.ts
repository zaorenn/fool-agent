/**
 * Uyandırma motoru seçimi, kurulumu ve sınaması.
 *
 * Kullanıcının üç isteği:
 *
 *   * "o ayarlardaki neyse o sözcük wake wordümüz olmalı" -- gösterilen ifade
 *     motorun GERÇEKTEN dinlediği ifade.
 *   * "wake word belirlediğimiz yerin yanında ... bir test butonu."
 *   * "kullanıcı wake word için gerekli motorları da gerekiyorsa
 *     kurabilmeli ... uygulamadan doğrudan indirilebilir olmalı."
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  $wakeEngines,
  applyWakeTestResult,
  installWakeEngine,
  loadWakeEngines,
  resetWakeTest,
  setWakeEngine,
  startWakeTest,
  type WakeEngine
} from './wake-engines'
import { $wakeWord } from './wake-word'

const engine = (over: Partial<WakeEngine> = {}): WakeEngine => ({
  active: false,
  blocked_reason: '',
  custom_phrase: false,
  description: '',
  env_key: '',
  id: 'openwakeword',
  installed: true,
  label: 'Built-in',
  phrases: [],
  usable: true,
  ...over
})

beforeEach(() => {
  $wakeEngines.set({
    effectivePhrase: '',
    engines: [],
    installs: {},
    loaded: false,
    notice: '',
    test: { phase: 'idle' }
  })
})

describe('katalog', () => {
  it('GERCEK ifadeyi tutuyor', () => {
    const request = vi.fn().mockResolvedValue({
      effective_phrase: 'hey hermes',
      engines: [engine({ active: true })]
    })

    return loadWakeEngines(request).then(() => {
      expect($wakeEngines.get().effectivePhrase).toBe('hey hermes')
      expect($wakeEngines.get().engines).toHaveLength(1)
    })
  })

  it('ESKI arka ucta ayarlar ekrani karartilmiyor', async () => {
    // ``wake.engines`` olmayan bir arka uca baglanmak, ses ayarlarinin
    // tamamini bos birakabilirdi. Sebep yaziliyor ve devam ediliyor.
    const request = vi.fn().mockRejectedValue(new Error('unknown method'))

    await loadWakeEngines(request)

    expect($wakeEngines.get().loaded).toBe(true)
    expect($wakeEngines.get().notice).toContain('unknown method')
  })
})

describe('motor secimi', () => {
  it('secimden sonra katalog TAZELENIYOR', async () => {
    // Tazelemezsek "aktif" isareti eski motorda kalirdi.
    const request = vi.fn(async (method: string) =>
      method === 'wake.engine'
        ? { effective_phrase: 'merhaba dostum' }
        : { effective_phrase: 'merhaba dostum', engines: [engine({ active: true, id: 'sherpa' })] }
    ) as unknown as Parameters<typeof setWakeEngine>[1]

    await setWakeEngine('sherpa', request)

    expect($wakeEngines.get().effectivePhrase).toBe('merhaba dostum')
    expect($wakeEngines.get().engines[0]?.id).toBe('sherpa')
  })
})

describe('dinleyici YENIDEN kuruluyor', () => {
  it('motor degisince yeniden kurma cagriliyor', async () => {
    // Olculen hata: kullanicinin bildirdigi "hey hermes disindaki hicbiri
    // calismiyor". Gunlukte motor degisimleri vardi ama ardindan TEK BIR
    // ``wake.start`` yoktu -- kulak ilk kuruldugu modelde kalmisti.
    $wakeWord.set({ ...$wakeWord.get(), enabled: true, listening: true })

    const seen: string[] = []

    const request = vi.fn(async (method: string) => {
      seen.push(method)

      if (method === 'wake.status') {
        return { available: true, enabled: true, listening: false }
      }

      if (method === 'wake.start') {
        return { started: true }
      }

      return { effective_phrase: 'merhaba', engines: [] }
    }) as unknown as Parameters<typeof setWakeEngine>[1]

    await setWakeEngine('sherpa', request)

    expect(seen).toContain('wake.status')
    expect(seen).toContain('wake.start')
  })

  it('uyandirma KAPALIYKEN kulak acilmiyor', async () => {
    // Kullanici kulagi kapali tutuyorsa motor degistirmek onu ACMAMALI.
    $wakeWord.set({ ...$wakeWord.get(), enabled: false, listening: false })

    const seen: string[] = []

    const request = vi.fn(async (method: string) => {
      seen.push(method)

      return { effective_phrase: '', engines: [] }
    }) as unknown as Parameters<typeof setWakeEngine>[1]

    await setWakeEngine('sherpa', request)

    expect(seen).not.toContain('wake.start')
  })
})

describe('kurulum', () => {
  it('is BITENE kadar yoklaniyor', async () => {
    vi.useFakeTimers()

    const request = vi.fn(async (method: string) => {
      if (method === 'wake.install') {
        return { detail: '', elapsed: 0, engine_id: 'sherpa', error: '', id: 'j1', stage: 'starting', state: 'running' }
      }

      if (method === 'wake.install_status') {
        return { detail: 'ready', elapsed: 2, engine_id: 'sherpa', error: '', id: 'j1', stage: 'done', state: 'done' }
      }

      return { effective_phrase: '', engines: [engine({ id: 'sherpa', installed: true })] }
    }) as unknown as Parameters<typeof installWakeEngine>[1]

    const pending = installWakeEngine('sherpa', request)

    await vi.advanceTimersByTimeAsync(1_000)

    const job = await pending

    expect(job.state).toBe('done')
    // Kurulum bitince katalog tazeleniyor: motorun secilebilir hale geldigini
    // gormek icin kullanicinin ayarlari kapatip acmasi gerekmemeli.
    expect($wakeEngines.get().engines[0]?.installed).toBe(true)

    vi.useRealTimers()
  })
})

describe('sinama', () => {
  it('SEBEBI soyluyor, yalnizca basarisiz demiyor', async () => {
    // En sik sebep: dinleyici kapali. "Basarisiz" demek kullaniciya hicbir
    // sey anlatmazdi.
    const request = vi.fn().mockRejectedValue(new Error('the wake word is not listening right now'))

    await startWakeTest(request)

    const state = $wakeEngines.get().test

    expect(state.phase).toBe('failed')
    expect(state.phase === 'failed' && state.reason).toContain('not listening')
  })

  it('olay sonucu duruma cevriliyor', () => {
    applyWakeTestResult({ detected: true })
    expect($wakeEngines.get().test.phase).toBe('detected')

    applyWakeTestResult({ detected: false, timed_out: true })
    expect($wakeEngines.get().test.phase).toBe('timeout')

    applyWakeTestResult({ cancelled: true })
    expect($wakeEngines.get().test.phase).toBe('idle')
  })

  it('sifirlanabiliyor', () => {
    applyWakeTestResult({ detected: true })
    resetWakeTest()

    expect($wakeEngines.get().test.phase).toBe('idle')
  })
})

describe('dikisler', () => {
  const read = (...parts: string[]) => readFileSync(join(__dirname, ...parts), 'utf8')

  const SETTINGS = read('..', 'fool', 'voice-settings.tsx')
  const WIRING = read('..', 'app', 'contrib', 'wiring.tsx')
  const WAKE = read('wake-word.ts')

  it('ayarlar GERCEK ifadeyi gosteriyor', () => {
    // Ham ``phrase`` alani yalnizca ``sherpa``da anahtar; digerlerinde
    // kozmetik bir etiket ve tam olarak bu yuzden ekran yalan soyluyordu.
    expect(WAKE).toContain('status?.effective_phrase?.trim()')
    expect(SETTINGS).toContain('engines.effectivePhrase || wake.phrase')
  })

  it('dinleyici ARMLANIRKEN de gercek ifade yaziliyor', () => {
    // Ikinci kapi: ``wake.start`` yaniti da ifade tasiyor ve masaustu onu
    // depoya yaziyor. Ham alani okusaydi ekranda duzeltilen ifade HER armda
    // "hey fool"a geri donerdi -- ayni hatanin ikinci yolu.
    expect(WAKE).toContain('result.effective_phrase?.trim()')
  })

  it('SABIT dagarcikli motorda serbest metin YOK', () => {
    // Model ne egitildiyse onu duyuyor; serbest metin sunmak, yazilanin
    // hicbir zaman taninmamasi demekti.
    expect(SETTINGS).toContain('custom ? (')
    expect(SETTINGS).toContain('setWakeModel')
  })

  it('KURULU OLMAYAN motor secilemiyor ama KURULABILIYOR', () => {
    expect(SETTINGS).toContain('!engine.installed')
    expect(SETTINGS).toContain('installWakeEngine')
    // Kapi ``usable``da: paketi kurulu ama anahtari olmayan motor da
    // secilememeli.
    expect(SETTINGS).toContain('disabled={!engine.usable')
  })

  it('basarisiz kurulum SEBEBINI soyluyor', () => {
    // Olculen kiriklik: bildirimde hem baslik hem govde "Could not install
    // the engine" yaziyordu. Arka uc tam olarak neyin cozulemedigini
    // soylemisti ("no version of pypinyin==0.57.0") ama kullaniciya
    // ulasmiyordu -- sebepsiz bir hata, ayni dugmeye tekrar basmaktan baska
    // bir seye goturmuyor.
    expect(SETTINGS).toContain('job.error ||')
    // Ve EKRANDA kaliyor: bildirim kapanip gidince sebep bir daha
    // gorulemiyordu.
    expect(SETTINGS).toContain("state.installs).find(job => job.state === 'failed')")
  })

  it('sinama sonucu OLAY olarak baglaniyor', () => {
    expect(WIRING).toContain("event.type === 'wake.test.result'")
    expect(WIRING).toContain('applyWakeTestResult(event.payload)')
  })

  it('sinama dinleyici KAPALIYKEN sunulmuyor', () => {
    // Sinama canli dinleyiciyi kullaniyor; kulak kapaliyken sinanacak bir sey
    // yok ve dugmenin calisiyormus gibi durmasi yaniltirdi.
    expect(SETTINGS).toContain('disabled={testing || !wake.listening}')
  })
})
