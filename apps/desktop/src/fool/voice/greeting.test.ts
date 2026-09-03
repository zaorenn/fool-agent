/**
 * Açılışta konuşma ve ısınma anlatımı.
 *
 * Ölçülen süreler (bu makine, RTX 4070 Ti SUPER):
 *   styletts2  soğuk 22,5 sn / sıcak 0,52 sn
 *   kokoro     soğuk 24,2 sn / sıcak 0,32 sn
 *   Whisper    soğuk  6,9 sn / sıcak 0,37 sn
 */

import { describe, expect, it } from 'vitest'

import {
  greeting,
  hasFailed,
  isWarm,
  needsWaking,
  stageLine,
  warmupCaption,
  warmupSettled
} from './greeting'

const ASCII_ONLY = /^[ -~]+$/

const warm = { status: 'warm' }
const cold = { status: 'cold' }
const failed = { status: 'failed' }

describe('greeting', () => {
  /** Bir sohbeti soruyla açmak onu görevleştiriyor. */
  it('SORU sormuyor', () => {
    expect(greeting().includes('?')).toBe(false)
  })

  it('kullaniciya gorunen metin INGILIZCE', () => {
    expect(ASCII_ONLY.test(greeting())).toBe(true)
  })

  it('bos degil', () => {
    expect(greeting().trim().length).toBeGreaterThan(0)
  })
})

describe('isinma durumu', () => {
  it('sicak olani taniyor', () => {
    expect(isWarm(warm)).toBe(true)
    expect(isWarm(cold)).toBe(false)
    expect(isWarm(undefined)).toBe(false)
  })

  it('basarisizi taniyor', () => {
    expect(hasFailed(failed)).toBe(true)
    expect(hasFailed(cold)).toBe(false)
  })

  it('ikisi de hazirsa bekleme biter', () => {
    expect(warmupSettled({ stt: warm, tts: warm })).toBe(true)
  })

  /**
   * Kilitli kalmış bir açılış ekranında sonsuza kadar beklemek, geç
   * konuşmaktan kötü. İlk gerçek cümle modeli zaten kendisi yükler.
   */
  it('BASARISIZ da beklemeyi bitiriyor', () => {
    expect(warmupSettled({ stt: failed, tts: failed })).toBe(true)
    expect(warmupSettled({ stt: warm, tts: failed })).toBe(true)
  })

  it('biri hala isinirken bekleme surmeli', () => {
    expect(warmupSettled({ stt: warm, tts: { status: 'warming' } })).toBe(false)
    expect(warmupSettled({})).toBe(false)
  })

  it('seslendirme soguksa uyanma cumlesi gerekiyor', () => {
    expect(needsWaking({ tts: cold })).toBe(true)
    expect(needsWaking({ tts: warm })).toBe(false)
  })
})

describe('stageLine', () => {
  it('SOGUKTAN sicaga gecince konusuyor', () => {
    expect(stageLine('tts', { tts: cold }, { tts: warm })).toBe('Voice ready.')
    expect(stageLine('stt', { stt: cold }, { stt: warm })).toBe('Hearing ready.')
  })

  /** Zaten sıcak olan için "hazır" demek hiçbir şey söylemeyen bir cümle. */
  it('ZATEN sicaksa susuyor', () => {
    expect(stageLine('tts', { tts: warm }, { tts: warm })).toBe('')
  })

  it('hala soguksa susuyor', () => {
    expect(stageLine('tts', { tts: cold }, { tts: cold })).toBe('')
  })

  it('basarisiz olani hazir diye ANONS ETMIYOR', () => {
    expect(stageLine('tts', { tts: cold }, { tts: failed })).toBe('')
  })
})

describe('warmupCaption', () => {
  /** 22 saniyelik sessiz bekleme "bozuldu" gibi görünüyor. */
  it('bekleyen yuzeyleri ve SUREYI soyluyor', () => {
    const caption = warmupCaption({ stt: cold, tts: cold })

    expect(caption).toContain('voice and hearing')
    expect(caption).toContain('half a minute')
  })

  it('yalnizca bekleyeni sayiyor', () => {
    expect(warmupCaption({ stt: warm, tts: cold })).toContain('Loading voice ')
    expect(warmupCaption({ stt: cold, tts: warm })).toContain('Loading hearing ')
  })

  it('her sey hazirsa GOSTERILMIYOR', () => {
    expect(warmupCaption({ stt: warm, tts: warm })).toBe('')
  })
})
