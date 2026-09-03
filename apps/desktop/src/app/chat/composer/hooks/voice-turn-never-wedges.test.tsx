/**
 * Mikrofon KAPANMAZSA sesli tur sonsuza kadar kilitlenmemeli.
 *
 * Ölçülen hata
 * ------------
 * ``handleTurn`` kaydı şöyle kapatıyordu::
 *
 *     turnClosingRef.current = true
 *     setStatus('transcribing')
 *     const result = await handle.stop()      // <- korumasız
 *
 * ``MediaRecorder.stop()`` her zaman düzgün kapanmıyor: sürücü/aygıt
 * değişiminde ``InvalidStateError`` fırlatıyor ya da ``onstop`` hiç
 * gelmiyor. İkisinin de sonucu aynı ve ikisi de SESSİZ:
 *
 *   - Fırlatırsa: söz ``handleTurn``dan dışarı sızıyor (``void handleTurn()``
 *     ile çağrıldığı için yakalayan kimse yok), durum ``transcribing``de
 *     kalıyor. ``startListening`` yalnızca ``idle``de açıyor, yani mikrofon
 *     bir daha ASLA açılmıyor.
 *   - Hiç çözülmezse: aynı yer, üstüne ``turnClosingRef`` da ``true`` kalıyor
 *     ve sonraki her tur girişimi ilk satırda geri dönüyor.
 *
 * Kullanıcının gördüğü: sesli sohbet "açık" duruyor, hiçbir hata yok, hiçbir
 * şey olmuyor. Uygulamayı yeniden başlatmaktan başka çıkış yok.
 *
 * Sözleşme: kayıt kapatma NE OLURSA OLSUN tur ``idle``e dönüyor ve döngü
 * yeniden kuruluyor.
 */

import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { MicRecording } from './use-mic-recorder'

vi.mock('@/lib/voice-barge-in', () => ({
  monitorSpeechDuringPlayback: () => () => undefined
}))

vi.mock('@/lib/voice-playback', () => ({
  interruptVoicePlayback: vi.fn(),
  markVoicePlaybackInterrupted: vi.fn(),
  playSpeechText: vi.fn(async () => true),
  startSpeechStream: vi.fn(async () => null),
  stopVoicePlayback: vi.fn()
}))

vi.mock('@/lib/thinking-sound', () => ({
  startThinkingSound: vi.fn(),
  stopThinkingSound: vi.fn()
}))

const micHandle = {
  cancel: vi.fn(),
  start: vi.fn(async () => undefined),
  stop: vi.fn<() => Promise<MicRecording | null>>(async () => null)
}

vi.mock('./use-mic-recorder', () => ({
  useMicRecorder: () => ({ handle: micHandle, level: 0, recording: false })
}))

vi.mock('@/i18n', () => ({
  useI18n: () => ({
    t: {
      notifications: {
        voice: {
          configureSpeechToText: 'configure STT',
          couldNotStartSession: 'could not start',
          microphoneFailed: 'mic failed',
          playbackFailed: 'playback failed',
          transcriptionFailed: 'transcription failed',
          unavailable: 'unavailable'
        }
      }
    }
  })
}))

vi.mock('@/store/notifications', () => ({ notify: vi.fn(), notifyError: vi.fn() }))

const { useVoiceConversation } = await import('./use-voice-conversation')

function renderConversation() {
  return renderHook(() =>
    useVoiceConversation({
      busy: false,
      consumePendingResponse: vi.fn(),
      enabled: true,
      onSubmit: vi.fn(async () => undefined),
      onTranscribeAudio: vi.fn(async () => 'merhaba'),
      pendingResponse: () => null
    })
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  micHandle.start.mockResolvedValue(undefined)
  micHandle.stop.mockResolvedValue(null)
})

afterEach(cleanup)

describe('kayit kapatma FIRLATIRSA', () => {
  it('tur idle e donuyor ve dongu yeniden kuruluyor', async () => {
    const hook = renderConversation()

    await act(async () => {
      await hook.result.current.start()
    })
    await waitFor(() => expect(hook.result.current.status).toBe('listening'))

    micHandle.stop.mockRejectedValueOnce(new DOMException('failed', 'InvalidStateError'))

    await act(async () => {
      hook.result.current.stopTurn()
    })

    // Kilitli kalmadi.
    await waitFor(() => expect(hook.result.current.status).not.toBe('transcribing'))

    // Ve dongu GERCEKTEN yeniden kuruldu: mikrofon tekrar aciliyor.
    await waitFor(() => expect(micHandle.start.mock.calls.length).toBeGreaterThan(1))
  })
})
