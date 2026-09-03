/**
 * Otomatik sesli okumanın YEDEK yolu yoktu — ses üretilmezse tam sessizlik.
 *
 * Ölçülen hata
 * ------------
 * ``useAutoSpeakReplies`` yalnızca AKIŞ yolunu tanıyordu::
 *
 *     if (!session) {
 *       streamRef.current = null
 *       return            // <- burada biten yol yok
 *     }
 *
 * Yorumu "cevap tamamlandığında tek seferlik yol devreye giriyor" diyordu ama
 * dosyada ``playSpeechText`` HİÇ geçmiyordu: yorum ile kod ayrışmıştı. İki
 * somut hâl sessiz kalıyordu:
 *
 *   1. Ağ geçidi akış ucunu sunmuyor (``startSpeechStream`` -> ``null``).
 *   2. Akış açıldı ama sentez hiç ses üretmedi (``done`` -> ``'fallback'``).
 *
 * İkincisi asıl tehlikelisi: kullanıcı "Cevapları sesli oku"yu AÇMIŞ, ekranda
 * cevap akıyor, hiçbir hata görünmüyor ve hiçbir ses çıkmıyor.
 *
 * Sesli sohbet döngüsü (``use-voice-conversation.ts``) ve çentik bu yedeği
 * zaten taşıyordu; eksik olan tek yüzey burasıydı.
 */

import { cleanup, render, waitFor } from '@testing-library/react'
import { atom } from 'nanostores'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ChatMessage } from '@/lib/chat-messages'

const playSpeechText = vi.fn<(text: string, options: unknown) => Promise<boolean>>(async () => true)
const startSpeechStream = vi.fn()

vi.mock('@/lib/voice-playback', () => ({
  playSpeechText: (text: string, options: unknown) => playSpeechText(text, options),
  startSpeechStream: (options: unknown) => startSpeechStream(options)
}))

vi.mock('@/fool/voice-api', () => ({
  voiceApi: { warmVoice: vi.fn(async () => undefined) }
}))

vi.mock('@/fool/voice-owner', () => ({ canSpeak: () => true }))

vi.mock('@/store/ambient', () => ({
  ownsAmbientCue: vi.fn(async () => true),
  // Talep TURU kapsayacak kadar tutuluyor; taklidin de bu disa aktarimi
  // vermesi gerekiyor, yoksa modul hic yuklenmiyor.
  SPEECH_CLAIM_TTL_MS: 600_000
}))

const notifyError = vi.fn()

vi.mock('@/store/notifications', () => ({ notifyError: (...args: unknown[]) => notifyError(...args) }))

const $messages = atom<ChatMessage[]>([])

vi.mock('../scope', () => ({ useComposerScope: () => ({ $messages }) }))

const { $autoSpeakReplies } = await import('@/store/voice-prefs')
const { $voicePlayback } = await import('@/store/voice-playback')
const { useAutoSpeakReplies } = await import('./use-auto-speak-replies')

/** Ekranda büyüyen cevap. */
let reply: { id: string; pending: boolean; text: string } | null = null

function Harness() {
  useAutoSpeakReplies({
    conversationActive: false,
    failureLabel: 'okuma basarisiz',
    markSpoken: () => undefined,
    pendingReply: () => reply,
    sessionId: 'session-1'
  })

  return null
}

/** Kancayı ``$messages`` tikiyle uyandır. */
function tick() {
  $messages.set([...$messages.get()])
}

beforeEach(() => {
  playSpeechText.mockClear()
  startSpeechStream.mockReset()
  notifyError.mockClear()
  reply = null
  $messages.set([])
  $voicePlayback.set({ audioElement: null, messageId: null, sequence: 0, source: null, status: 'idle' })
  $autoSpeakReplies.set(true)
})

afterEach(() => {
  cleanup()
  $autoSpeakReplies.set(false)
})

describe('akis ucu YOKSA', () => {
  it('cevap tamamlaninca tek seferlik yoldan okuyor', async () => {
    startSpeechStream.mockResolvedValue(null)

    render(<Harness />)

    reply = { id: 'm1', pending: true, text: 'merhaba' }
    tick()

    await waitFor(() => expect(startSpeechStream).toHaveBeenCalled())

    // Cevap tamamlandi.
    reply = { id: 'm1', pending: false, text: 'merhaba dunya' }
    tick()

    await waitFor(() => expect(playSpeechText).toHaveBeenCalledTimes(1))
    expect(playSpeechText.mock.calls[0]?.[0]).toBe('merhaba dunya')
  })
})

describe('akis acildi ama HIC ses uretmedi', () => {
  it('cevap tamamlaninca tek seferlik yoldan okuyor', async () => {
    let settle: (value: 'done' | 'fallback') => void = () => undefined

    const session = {
      append: vi.fn(),
      finish: vi.fn(),
      done: new Promise<'done' | 'fallback'>(resolve => {
        settle = resolve
      })
    }

    startSpeechStream.mockResolvedValue(session)

    render(<Harness />)

    reply = { id: 'm2', pending: true, text: 'merhaba' }
    tick()

    await waitFor(() => expect(session.append).toHaveBeenCalled())

    // Sentez dustu: hic ses uretilmedi.
    settle('fallback')

    reply = { id: 'm2', pending: false, text: 'merhaba dunya' }
    tick()

    await waitFor(() => expect(playSpeechText).toHaveBeenCalledTimes(1))
    expect(playSpeechText.mock.calls[0]?.[0]).toBe('merhaba dunya')
  })
})

describe('akis SES URETTIYSE', () => {
  it('tek seferlik yol devreye GIRMIYOR -- ayni cevap iki kez okunmaz', async () => {
    let settle: (value: 'done' | 'fallback') => void = () => undefined

    const session = {
      append: vi.fn(),
      finish: vi.fn(),
      done: new Promise<'done' | 'fallback'>(resolve => {
        settle = resolve
      })
    }

    startSpeechStream.mockResolvedValue(session)

    render(<Harness />)

    reply = { id: 'm3', pending: true, text: 'merhaba' }
    tick()

    await waitFor(() => expect(session.append).toHaveBeenCalled())

    settle('done')

    reply = { id: 'm3', pending: false, text: 'merhaba dunya' }
    tick()

    await new Promise(resolve => setTimeout(resolve, 50))

    expect(playSpeechText).not.toHaveBeenCalled()
  })
})
