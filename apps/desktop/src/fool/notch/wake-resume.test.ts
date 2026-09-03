/**
 * Uyandırma sözcüğü BİR KEZ değil, HER SEFERİNDE çalışmalı.
 *
 * Kullanıcının bildirdiği birebir: "ilk hey hermesten sonra notch açıkken bir
 * daha hey hermes demem bir işe yaramıyor" ve "wake word dinlemesi açılıp
 * kapanana ya da notch açılıp kapanana kadar tekrardan wake word çalışmıyor."
 * Kuralı da o koydu: "bu sorunu hermes için değil GENEL wake word için çöz."
 *
 * Ölçülen sebep
 * -------------
 * SAPTAMA dinleyiciyi DURAKLATIYOR: sunucu ``wake.detected``i yayınlamadan
 * hemen önce ``pause_listening`` çağırıyor. Kendi geri açması yalnızca SUNUCU
 * tarafındaki ses döngüsünün geri çağrılarında (``_resume_voice_wake``);
 * masaüstü yakalamayı tarayıcı tarafında yaptığı için o döngü hiç koşmuyor.
 *
 * Composer'ın konuşma kipi borcu ödüyordu. Uyandırmayı çentiğe yönlendirmek
 * o yolu devre dışı bıraktı ve ödeyen kimse kalmadı -- yani kulak ilk
 * uyandırmadan sonra kapalı kalıyordu.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { WAKE_TURN_START_GRACE_MS, wakeTurnStep } from './wake-turn'

const read = (...parts: string[]) => readFileSync(join(__dirname, ...parts), 'utf8')

const FLAG = read('use-wake-turn-flag.ts')
const RESUME = read('use-wake-turn-resume.ts')
const SHELL = read('notch-shell.tsx')
const WIRING = read('..', '..', 'app', 'contrib', 'wiring.tsx')

describe('turun bittigine karar verme', () => {
  it('durum etkinken tur SURUYOR', () => {
    for (const status of ['listening', 'transcribing', 'thinking', 'speaking'] as const) {
      expect(wakeTurnStep(false, status)).toBe('running')
      expect(wakeTurnStep(true, status)).toBe('running')
    }
  })

  it('bir kez etkin gorulduyse ``idle`` BITTI demek', () => {
    expect(wakeTurnStep(true, 'idle')).toBe('ended')
  })

  it('tur BASLARKEN ``idle`` bitis SAYILMIYOR', () => {
    // Tuzak: tur baslarken durum zaten ``idle`` -- onay sesi caliyor, mikrofon
    // henuz acilmadi. Naif kural turu daha baslamadan bitmis sayar ve
    // dinleyici kendi TTS onayimizi duyardi.
    expect(wakeTurnStep(false, 'idle')).toBe('waiting-start')
  })

  it('hic baslayamayan tur icin MUHLET var', () => {
    // Mikrofon acilamazsa (izin yok, aygit mesgul) durum ``idle`` DISINA hic
    // cikmiyor. Muhlet olmasa bayrak sonsuza kadar takili kalir ve kulak
    // KALICI olarak sagir olurdu -- duzeltilen hatanin ta kendisi.
    expect(WAKE_TURN_START_GRACE_MS).toBeGreaterThan(0)
    expect(FLAG).toContain('setTimeout(end, WAKE_TURN_START_GRACE_MS)')
  })

  it('muhlet konusma suresine gore KISA', () => {
    // Yalnizca baslayamamis bir turu kurtariyor; konusma surerken durum
    // ``idle`` degil, o yuzden turun ORTASINDA dolamaz.
    expect(WAKE_TURN_START_GRACE_MS).toBeLessThanOrEqual(10_000)
  })
})

describe('centik turu BILDIRIYOR', () => {
  it('uyandirma dalinda tur BASLATILIYOR', () => {
    const wake = SHELL.slice(SHELL.indexOf("request?.mode === 'wake'"), SHELL.indexOf('setSessionActive(previous'))

    expect(wake).toContain('startWakeTurn()')
  })

  it('bas-konus turu bildirim URETMIYOR', () => {
    // Bas-konus dinleyiciyi hic duraklatmiyor: orada odenecek bir borc yok ve
    // her turda uzlastirma cagirmak gereksiz ag trafigi olurdu.
    const ptt = SHELL.slice(SHELL.indexOf('setSessionActive(previous'))

    expect(ptt).not.toContain('startWakeTurn()')
  })

  it('centik giderse bayrak ARKADA BIRAKILMIYOR', () => {
    expect(FLAG).toContain('useEffect(() => () => setWakeTurnActive(false), [])')
  })
})

describe('geri acmayi ANA PENCERE yapiyor', () => {
  it('kanca ana pencerede bagli', () => {
    expect(WIRING).toContain('useWakeTurnResume()')
  })

  it('centik penceresinde KOSMUYOR', () => {
    // Kira ana pencerede (``surface: 'gui'``). Centik ayri bir
    // ``BrowserWindow`` ve oradan istemek kirayi baska bir tasiyiciya
    // devrederdi -- dinleyici ana pencerenin elinden cikardi.
    expect(RESUME).toContain('isNotchWindow()')
  })

  it('UZLASTIRAN cagriyi kullaniyor, ham ``wake.resume`` DEGIL', () => {
    // ``resumeWakeAfterVoice`` yapilandirmayi otorite sayiyor, mikrofonun
    // birakilmasini bekleyip tekrar deniyor ve hicbir zaman ``persist``
    // yazmiyor. Ham bir ``wake.resume`` o yarisi kaybedince kulak yine
    // sessizce kapali kalirdi.
    expect(RESUME).toContain('resumeWakeAfterVoice()')
    expect(RESUME).not.toContain("request('wake.resume'")
  })

  it('yalnizca tur BITISINDE, acilista DEGIL', () => {
    // ``subscribe`` acilista mevcut degeri de veriyor; onu bir gecis saymak
    // her acilista gereksiz uzlastirma tetiklerdi.
    expect(RESUME).toContain('let first = true')
    expect(RESUME).toContain('previous && !active')
  })
})
