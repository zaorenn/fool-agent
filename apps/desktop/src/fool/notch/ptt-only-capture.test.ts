/**
 * Bas-konuş kipinde TEK giriş tuştur.
 *
 * Kullanıcının bildirdiği: "notch açıkken bas-konuş özelliği çalışıyor
 * çalışmasına, ama basmadan konuşursak bile algılıyor."
 *
 * Sebep: araya girme izleyicisi dinleme kipine BAKMADAN çalışıyordu --
 * ``shouldMonitorBargeIn(status)`` yalnızca duruma bakıyor, yani model
 * düşünürken ya da konuşurken mikrofon açık kalıyor ve ses algılanınca tuşa
 * basılmadan yakalanıp gönderiliyordu.
 *
 * Kuralı kullanıcı koydu ve doğrusu da bu: "notch direkt olarak conversation
 * modu olmamalı, conversation modunun bas-konuş hâli olmalı."
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { shouldMonitorBargeIn } from './barge-in'

const HOOK = readFileSync(join(__dirname, 'use-notch-voice.ts'), 'utf8')

describe('izleyici KIPE bagli', () => {
  it('kapi dinleme kipini OKUYOR', () => {
    // Regresyonun kendisi: kosul eskiden yalnizca duruma bakiyordu.
    expect(HOOK).toContain("const handsFree = listenMode === 'hands-free'")
    expect(HOOK).toContain('(handsFree && shouldMonitorBargeIn(status)) || capturing')
    // Kipsiz eski hali geri gelirse burasi duser.
    expect(HOOK).not.toContain('const monitorActive = shouldMonitorBargeIn(status) || capturing')
  })

  it('SUREN yakalama izleyiciyi acik tutuyor', () => {
    // ``capturing`` kasitli olarak kaliyor: eller serbest kipte baslamis bir
    // yakalama surerken izleyici kapanirsa cumlenin gerisi kaybolur.
    expect(HOOK).toContain('|| capturing')
  })

  it('durum kapisi DEGISMEDI -- yalnizca kip eklendi', () => {
    // ``shouldMonitorBargeIn``in kendisi hala ayni soruyu cevapliyor: model
    // dusunuyor ya da konusuyor mu? Kip karari onun USTUNE bindi, icine
    // gomulmedi -- boylece eller serbest kipte davranis aynen korunuyor.
    expect(shouldMonitorBargeIn('thinking')).toBe(true)
    expect(shouldMonitorBargeIn('speaking')).toBe(true)
    expect(shouldMonitorBargeIn('idle')).toBe(false)
    expect(shouldMonitorBargeIn('listening')).toBe(false)
    expect(shouldMonitorBargeIn('transcribing')).toBe(false)
  })
})
