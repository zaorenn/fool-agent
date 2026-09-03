/**
 * Kurulumda ses indirme kararları.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { describe, expect, it } from 'vitest'

import type { VoiceItem, VoiceJob } from '../voice-api'

import { installDevice, overallPercent, pendingInstalls, recommendedPair, setupState } from './voice-setup'

function item(overrides: Partial<VoiceItem> = {}): VoiceItem {
  return {
    active: false,
    assets_installed: true,
    clone: '',
    clone_capable: false,
    clone_help: '',
    cpu_warning: '',
    cuda_available: false,
    cuda_ready: false,
    device: 'auto',
    devices: ['cpu'],
    engine_error: '',
    engine_installed: true,
    id: 'piper',
    installed: true,
    job: null,
    kind: 'tts',
    knobs: [],
    label: 'Piper',
    provider_id: 'piper',
    recommended: false,
    size_label: '~63 MB',
    summary: '',
    usable: true,
    voice: '',
    voices: [],
    ...overrides
  }
}

function job(overrides: Partial<VoiceJob> = {}): VoiceJob {
  return {
    detail: '',
    device: 'cpu',
    elapsed: 0,
    entry_id: 'piper',
    error: '',
    id: 'j1',
    percent: 0,
    stage: '',
    state: 'running',
    ...overrides
  }
}

describe('recommendedPair', () => {
  it('her turden BIR tane seciyor', () => {
    const pair = recommendedPair([
      item({ id: 'piper', kind: 'tts', installed: false, recommended: true }),
      item({ id: 'kokoro', kind: 'tts', installed: false }),
      item({ id: 'whisper', kind: 'stt', installed: false, recommended: true })
    ])

    expect(pair.map(p => p.id)).toEqual(['whisper', 'piper'])
  })

  it('KURULU olan onerilene tercih ediliyor', () => {
    // Diskte duran 1,3 GB'i tekrar indirtmek "bir kac tikla hallolsun"un tersi.
    const pair = recommendedPair([
      item({ id: 'kokoro', kind: 'tts', installed: true }),
      item({ id: 'piper', kind: 'tts', installed: false, recommended: true })
    ])

    expect(pair.map(p => p.id)).toEqual(['kokoro'])
  })

  it('secili VE kurulu olan once geliyor', () => {
    const pair = recommendedPair([
      item({ id: 'kokoro', kind: 'tts', installed: true }),
      item({ id: 'chatterbox', kind: 'tts', installed: true, active: true })
    ])

    expect(pair.map(p => p.id)).toEqual(['chatterbox'])
  })

  it('o turden hicbir sey yoksa BOS', () => {
    expect(recommendedPair([])).toEqual([])
  })
})

describe('overallPercent', () => {
  it('kurulu olan YUZDE YUZ sayiliyor', () => {
    // Cubuk "ne kadar kaldi" sorusunu cevaplamali.
    const pair = [item({ id: 'a', installed: true }), item({ id: 'b', kind: 'stt', installed: false })]

    expect(overallPercent(pair, { b: job({ percent: 50 }) })).toBe(75)
  })

  it('is yokken sifir', () => {
    expect(overallPercent([item({ installed: false })], {})).toBe(0)
  })

  it('biten is YUZDE YUZ, yuzdesi ne olursa olsun', () => {
    // Bir is ``done`` bildirip yuzdeyi 98'de birakabiliyor.
    const one = [item({ id: 'a', installed: false })]

    expect(overallPercent(one, { a: job({ percent: 98, state: 'done' }) })).toBe(100)
  })

  it('bos listede sifir', () => {
    expect(overallPercent([], {})).toBe(0)
  })
})

describe('setupState', () => {
  it('hicbiri kurulu degilse BOSTA', () => {
    expect(setupState([item({ installed: false })], {})).toBe('idle')
  })

  it('suren is varsa KURULUYOR', () => {
    expect(setupState([item({ id: 'a', installed: false })], { a: job() })).toBe('installing')
  })

  it('hepsi kuruluysa HAZIR', () => {
    expect(setupState([item({ installed: true })], {})).toBe('ready')
  })

  it('dusen is varsa BASARISIZ', () => {
    expect(setupState([item({ id: 'a', installed: false })], { a: job({ state: 'failed' }) })).toBe('failed')
  })

  it('HIC denenmemis kurulum basarisiz DEGIL', () => {
    // Olmayan bir hatayi bildirmek, kullaniciyi ilk dakikasinda korkutur.
    expect(setupState([item({ installed: false })], {})).not.toBe('failed')
  })
})

describe('pendingInstalls', () => {
  it('kurulu olani ATLIYOR', () => {
    const items = [item({ id: 'a', installed: true }), item({ id: 'b', installed: false })]

    expect(pendingInstalls(items).map(p => p.id)).toEqual(['b'])
  })
})

describe('installDevice', () => {
  it('kart varsa ve motor kullanabiliyorsa CUDA', () => {
    expect(installDevice(item({ devices: ['cpu', 'cuda'] }), true)).toBe('cuda')
  })

  it('kart yoksa CPU', () => {
    expect(installDevice(item({ devices: ['cpu', 'cuda'] }), false)).toBe('cpu')
  })

  it('motor CUDA bilmiyorsa CPU', () => {
    expect(installDevice(item({ devices: ['cpu'] }), true)).toBe('cpu')
  })
})
