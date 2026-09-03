/**
 * ``stop()`` HER ZAMAN çözülüyor — ne fırlatıyor ne asılı kalıyor.
 *
 * Ölçülen hata
 * ------------
 * Kaydedicinin sözleşmesi "bir kayıt ya da ``null`` döner" diyordu ama
 * uygulanmıyordu::
 *
 *     stopResolverRef.current = resolve
 *     recorder.stop()                    // <- korumasız
 *
 * İki somut hâl bu sözü bozuyor ve ikisi de SESSİZ:
 *
 *   - ``MediaRecorder.stop()`` aygıt/sürücü değişiminde
 *     ``InvalidStateError`` fırlatıyor. Söz yürütücüsünün içinden fırlayan
 *     hata sözü REDDEDİYOR.
 *   - ``onstop`` hiç gelmiyor (aygıt koptu, arabellek boşaltma takıldı). O
 *     zaman söz hiç çözülmüyor.
 *
 * İkisinin de bedeli aynı: çağıran taraf turu ``transcribing``de bırakıyor,
 * mikrofon bir daha hiç açılmıyor ve kullanıcı hiçbir hata görmüyor.
 *
 * Bu sınav sözleşmeyi KAYDEDİCİNİN üstünde tutuyor — düzeltmenin yaşadığı
 * yer orası, yani her iki ses yüzeyi de (besteci ve çentik) aynı anda
 * korunuyor.
 */

import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useMicRecorder } from './use-mic-recorder'

const COPY = {
  microphoneAccessDenied: 'denied',
  microphoneConstraintsUnsupported: 'constraints',
  microphoneInUse: 'in use',
  microphonePermissionDenied: 'permission',
  microphoneStartFailed: 'start failed',
  microphoneUnsupported: 'unsupported',
  noMicrophone: 'no mic'
}

/** Kaydı hiç bitirmeyen / kapanışta fırlatan sahte kaydedici. */
class FakeRecorder {
  static isTypeSupported() {
    return true
  }

  static behavior: 'hang' | 'throw' = 'hang'

  state: 'recording' | 'inactive' = 'inactive'
  mimeType = 'audio/webm'
  ondataavailable: ((event: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  onerror: ((event: Event) => void) | null = null

  start() {
    this.state = 'recording'
  }

  stop() {
    if (FakeRecorder.behavior === 'throw') {
      throw new DOMException('failed', 'InvalidStateError')
    }

    // ``hang``: durum degisiyor ama ``onstop`` HIC gelmiyor.
    this.state = 'inactive'
  }
}

beforeEach(() => {
  vi.stubGlobal('MediaRecorder', FakeRecorder)
  vi.stubGlobal('AudioContext', undefined)

  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: async () => ({ getTracks: () => [] }) }
  })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

async function startRecording() {
  const hook = renderHook(() => useMicRecorder(COPY))

  await act(async () => {
    await hook.result.current.handle.start()
  })

  return hook
}

describe('kapanis FIRLATIRSA', () => {
  it('soz REDDEDILMIYOR -- null ile cozuluyor', async () => {
    FakeRecorder.behavior = 'throw'

    const hook = await startRecording()

    let result: unknown = 'unset'

    await act(async () => {
      result = await hook.result.current.handle.stop()
    })

    expect(result).toBeNull()
  })
})

describe('onstop HIC gelmezse', () => {
  it('sinirli bir sure sonra cozuluyor', async () => {
    FakeRecorder.behavior = 'hang'
    vi.useFakeTimers()

    const hook = renderHook(() => useMicRecorder(COPY))

    await act(async () => {
      await hook.result.current.handle.start()
    })

    let settled = false

    const pending = hook.result.current.handle.stop().then(value => {
      settled = true

      return value
    })

    // Once GERCEKTEN bekliyor: hemen cozulseydi kayit kaybi olurdu.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000)
    })
    expect(settled).toBe(false)

    // Sinira gelince BIRAKIYOR.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000)
    })

    expect(settled).toBe(true)
    expect(await pending).toBeNull()
  })
})
