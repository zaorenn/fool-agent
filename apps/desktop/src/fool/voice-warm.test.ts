/**
 * Seslendirme motoru AÇILIŞTA ısınmalı, ve ısınana kadar bas-konuş açılmamalı.
 *
 * Ölçüldü (bu makine, Chatterbox + CUDA): soğuk 36,8 sn / sıcak 0,8 sn.
 * Isıtma bugüne kadar yalnızca tepkiseldi -- mikrofon açılınca, çentik oturumu
 * açılınca -- yani soğuk yükleme her zaman kullanıcının bekleyişine biniyordu.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const SOURCE = readFileSync(join(__dirname, 'voice-warm.ts'), 'utf8')
const NOTCH = readFileSync(join(__dirname, 'notch', 'use-notch-voice.ts'), 'utf8')
const MAIN = readFileSync(join(__dirname, '..', 'main.tsx'), 'utf8')

describe('acilista isitma', () => {
  it('uygulama acilirken TETIKLENIYOR', () => {
    expect(MAIN).toContain("import './fool/voice-warm'")
  })

  it('yalnizca ANA pencere isitiyor', () => {
    // Iki pencere ayni motoru iki kez yuklemeye calisirsa tek-motor kurali
    // yuzunden yukle-bosalt dongusune girer.
    expect(SOURCE).toContain('whenMainWindow(')
  })

  it('durum PAYLASILAN degerden geciyor', () => {
    // Centik arka uca kendi sormuyor; isitmayi BIR taraf yurutuyor.
    expect(SOURCE).toContain("sharedAtom<VoiceWarmState>('fool.desktop.voice.warm'")
  })

  it('SURESIZ yoklamiyor', () => {
    // Motoru hic kurulmamis bir makinede sonsuza kadar istek atmak olurdu.
    expect(SOURCE).toContain('GIVE_UP_MS')
  })
})

describe('bas-konus kapisi', () => {
  it('ISINIRKEN acilmiyor ve SEBEBINI yaziyor', () => {
    const begin = NOTCH.slice(NOTCH.indexOf('const begin = useCallback'))

    expect(begin.slice(0, 1400)).toContain("$voiceWarm.get() === 'warming'")
    expect(begin.slice(0, 1400)).toContain('Warming up the voice')
  })

  it('BASARISIZ isinma bas-konusu ENGELLEMIYOR', () => {
    // Isinmayi bekleyemedigimiz icin kullaniciyi susturmak, isinmamis bir
    // motorla konusmasina izin vermekten kotu.
    const begin = NOTCH.slice(NOTCH.indexOf('const begin = useCallback'), NOTCH.indexOf('forceClaimBarge'))

    expect(begin).not.toContain("=== 'failed'")
    expect(begin).not.toContain("!== 'ready'")
  })
})
