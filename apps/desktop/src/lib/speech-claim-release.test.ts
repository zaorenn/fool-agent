/**
 * Hiç ses çıkmadıysa "bu mesaj okundu" KAYDI kalmamalı.
 *
 * Ölçülen hata
 * ------------
 * ``claimSpeech`` "bir cevap, bir ses" için var: aynı mesaj kimliğini ikinci
 * kez seslendirmek isteyen çağıran sessizce vazgeçiyor. Doğru kural. Ama kayıt
 * akış oturumu AÇILIRKEN atılıyordu, ses ÜRETİLDİĞİNDE değil.
 *
 * Sonuç, sessiz sınıfın ders kitabı hâli::
 *
 *     startSpeechStream({ messageId: 'm1' })   // kaydı atar
 *       -> akış kurulamaz / hiç ses üretmez    // 'fallback'
 *     playSpeechText(text, { messageId: 'm1' }) // KENDİ kaydına takılır
 *       -> false                                // hiç ses çıkmaz
 *
 * Yani "ses çıkmazsa metni yine oku" diye yazılmış yedek yol, tam da devreye
 * girmesi gereken anda kendi kaydı tarafından susturuluyordu. Çentiğin yedek
 * yolu (``use-notch-voice.ts``) birebir bu şekilde ölüydü.
 *
 * Kural TEK cümle: kayıt "seslendirildi" demek. Hiç ses üretmemiş bir oturum
 * mesajı seslendirmemiştir, o yüzden kaydını BIRAKMALI.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const speakText = vi.fn()

vi.mock('@/hermes', () => ({
  getApiRequestProfile: () => null,
  speakText: (text: string) => speakText(text)
}))

vi.mock('@fool/shared', () => ({
  resolveGatewayWsUrl: async () => 'ws://127.0.0.1:9/api/ws'
}))

/** Testin sürdüğü sırada açılan sahte soketler. */
let sockets: FakeSocket[] = []

class FakeSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1

  binaryType = 'arraybuffer'
  readyState = 1
  onopen: (() => void) | null = null
  onmessage: ((event: { data: unknown }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  readonly sent: string[] = []

  constructor(readonly url: string) {
    sockets.push(this)
  }

  send(data: string) {
    this.sent.push(data)

    // Sunucu davranisi: metin bitti bildirimi gelince oturum kapaniyor. Bu
    // sahte sunucu HIC ses uretmiyor, yani ``end`` -> 'fallback'.
    if (data.includes('"done"')) {
      queueMicrotask(() => this.endWithoutAudio())
    }
  }

  close() {
    this.readyState = 3
  }

  /** Sunucu oturumu SES ÜRETMEDEN kapattı. */
  endWithoutAudio() {
    this.onmessage?.({ data: JSON.stringify({ type: 'end' }) })
  }
}

/** jsdom ``HTMLMediaElement.play`` uygulanmamış: tek seferlik yol için
 *  anında biten bir ses öğesi gerekiyor. */
class FakeAudio {
  private readonly listeners = new Map<string, Set<(event: Event) => void>>()

  src = ''
  currentTime = 0

  constructor(source?: string) {
    this.src = source ?? ''
  }

  addEventListener(type: string, listener: (event: Event) => void) {
    const set = this.listeners.get(type) ?? new Set()

    set.add(listener)
    this.listeners.set(type, set)
  }

  removeEventListener(type: string, listener: (event: Event) => void) {
    this.listeners.get(type)?.delete(listener)
  }

  pause() {
    // no-op
  }

  load() {
    // no-op
  }

  async play() {
    queueMicrotask(() => {
      this.listeners.get('ended')?.forEach(listener => listener(new Event('ended')))
    })
  }
}

beforeEach(() => {
  sockets = []
  speakText.mockReset()
  speakText.mockResolvedValue({ data_url: 'data:audio/wav;base64,AA' })
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.stubGlobal('Audio', FakeAudio)
  vi.stubGlobal(
    'AudioContext',
    class {
      state = 'running'
      currentTime = 0
      destination = {}
      close = async () => undefined
      resume = async () => undefined
      createBuffer = () => ({ duration: 0, getChannelData: () => new Float32Array(0) })
      createBufferSource = () => ({ buffer: null, connect: () => undefined, start: () => undefined })
    }
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

/** ``window.foolDesktop`` var mı? Akış ucunun çözülüp çözülmemesini bu belirliyor. */
function withDesktopBridge(present: boolean) {
  if (present) {
    ;(window as unknown as { foolDesktop: unknown }).foolDesktop = {
      getConnection: async () => ({})
    }

    return
  }

  delete (window as unknown as { foolDesktop?: unknown }).foolDesktop
}

describe('akis KURULAMAZSA kayit birakiliyor', () => {
  it('yedek yol ayni mesaji seslendirebiliyor', async () => {
    withDesktopBridge(false)

    const { playSpeechText, startSpeechStream } = await import('./voice-playback')

    // Akis ucu cozulemedi (eski arka uc / kopru yok).
    expect(await startSpeechStream({ messageId: 'm1', source: 'read-aloud' })).toBeNull()

    // Yedek yol AYNI kimlikle cagriliyor -- cagiranin dogru davranisi bu.
    const played = await playSpeechText('merhaba', { messageId: 'm1', source: 'read-aloud' })

    expect(speakText).toHaveBeenCalledTimes(1)
    expect(played).toBe(true)
  })
})

describe('akis SES URETMEDEN kapanirsa kayit birakiliyor', () => {
  it('yedek yol ayni mesaji seslendirebiliyor', async () => {
    withDesktopBridge(true)

    const { playSpeechText, startSpeechStream } = await import('./voice-playback')

    const session = await startSpeechStream({ messageId: 'm2', source: 'voice-conversation' })

    expect(session).not.toBeNull()

    session?.append('merhaba')
    sockets[0].endWithoutAudio()

    expect(await session?.done).toBe('fallback')

    const played = await playSpeechText('merhaba', { messageId: 'm2', source: 'voice-conversation' })

    expect(speakText).toHaveBeenCalledTimes(1)
    expect(played).toBe(true)
  })
})

describe('GERCEKTEN seslendirilen mesaj ikinci kez okunmuyor', () => {
  it('kural korunuyor -- birakma yalnizca sessiz kalan yol icin', async () => {
    withDesktopBridge(false)

    const { playSpeechText } = await import('./voice-playback')

    expect(await playSpeechText('merhaba', { messageId: 'm3', source: 'read-aloud' })).toBe(true)
    expect(await playSpeechText('merhaba', { messageId: 'm3', source: 'read-aloud' })).toBe(false)
    expect(speakText).toHaveBeenCalledTimes(1)
  })
})
