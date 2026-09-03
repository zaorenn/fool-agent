import { resolveGatewayWsUrl } from '@fool/shared'

import { getApiRequestProfile, speakText } from '@/hermes'
import {
  $voicePlayback,
  setVoicePlaybackState,
  type VoicePlaybackSource,
  type VoicePlaybackState
} from '@/store/voice-playback'

import { sanitizeTextForSpeech } from './speech-text'

// Free Edge TTS occasionally hands back audio that never fires `playing`/`ended`
// nor `error` — leaving voice mode stuck "speaking" forever. Reject if playback
// fails to start or stalls mid-stream for this long (rearmed on each progress
// tick, so legitimately long speech is never cut off).
const PLAYBACK_STALL_MS = 15_000
// İlk ses karesi için üst sınır. ``PLAYBACK_STALL_MS`` bunu KAPSAMIYORDU:
// o, ``timeupdate`` olayına kuruluyor, yani ancak ses BAŞLADIKTAN sonra
// işliyor. Sentezin kendisi asılırsa hiçbir olay gelmiyor -- ne ``end``, ne
// ``close``, ne ``error`` -- ve ekran sonsuza kadar "Preparing audio"da
// kalıyor. Kullanıcının bildirdiği hâl tam buydu.
//
// Değer ÖLÇÜME dayanıyor: soğuk bir motor (sidecar süreci + model yükleme)
// kokoro'da 29,4 sn sürüyor. Bunun altına koymak meşru bir soğuk başlangıcı
// kesip gereksiz yere yedek yola düşürürdü. 45 sn, o en kötü hâlin üstünde
// ama asılmayı sonsuzdan çıkarıyor.
const FIRST_AUDIO_MS = 45_000

/**
 * BİR cevap, BİR ses.
 *
 * Sahiplik (``fool/voice-owner.ts``) YÜZEYLER arasını çözüyor ama aynı
 * yüzeyin içindeki iki çağıranı çözmüyor: sohbet panelinin hem otomatik
 * okuması hem sesli turu var ve ikisi de ``canSpeak('composer')`` sorusundan
 * geçiyor -- ``canSpeak`` sahip yokken de ``true`` dönüyor, çünkü sahiplik
 * konuşmayı engellemek için değil ÇAKIŞMAYI engellemek için.
 *
 * Kullanıcının bildirdiği hâli: Friend sessize alınınca sohbet paneli cevabı
 * okuyor -- ve AYNI cevabı iki kez okuyor.
 *
 * Bunun doğru yeri burası: her seslendiren yol bu iki işlevden geçiyor, yani
 * kaç çağıran olursa olsun bir mesaj bir kez seslendiriliyor. Kayıt kimliğe
 * göre; kimliksiz metin (uyanma cümlesi, aşama satırları) her zaman geçiyor.
 */
const spokenMessages = new Set<string>()

/** Bu mesajı ilk talep eden kazanır. ``false`` = başkası zaten seslendiriyor. */
function claimSpeech(messageId: null | string | undefined): boolean {
  if (!messageId) {
    return true
  }

  if (spokenMessages.has(messageId)) {
    return false
  }

  spokenMessages.add(messageId)

  // Sınırsız büyümesin: uzun bir oturumda her mesaj kimliği burada
  // birikirdi. Son 200 yeterli -- bir cevap ancak geldiği anda iki kez
  // seslendirilmeye çalışılıyor, saatler sonra değil.
  if (spokenMessages.size > 200) {
    const oldest = spokenMessages.values().next().value

    if (oldest !== undefined) {
      spokenMessages.delete(oldest)
    }
  }

  return true
}

/** Kullanıcı AÇIKÇA yeniden okutmak isterse kaydı bırak. */
export function forgetSpokenMessage(messageId: null | string | undefined): void {
  if (messageId) {
    spokenMessages.delete(messageId)
  }
}

let currentAudio: HTMLAudioElement | null = null
let currentStop: (() => void) | null = null
let sequence = 0

// A shared, lazily-created AudioContext used only to nudge the browser's
// autoplay state out of "suspended". A wake-word-started voice turn has no
// preceding user gesture, so the first HTMLAudioElement.play() can be rejected
// with NotAllowedError. resume()-ing a context is the documented way to recover
// once the app is allowed to make sound; on Electron chat windows the
// no-user-gesture-required policy means this is already unlocked, so this is a
// cheap no-op fallback for other surfaces.
let unlockCtx: AudioContext | null = null

async function unlockAutoplay(): Promise<void> {
  if (typeof window === 'undefined') {
    return
  }

  const Ctor =
    window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext

  if (!Ctor) {
    return
  }

  if (!unlockCtx) {
    unlockCtx = new Ctor()
  }

  if (unlockCtx.state === 'suspended') {
    await unlockCtx.resume()
  }
}

function currentState(
  status: VoicePlaybackState['status'],
  options?: VoicePlaybackOptions,
  audioElement: HTMLAudioElement | null = null
): VoicePlaybackState {
  return {
    audioElement,
    messageId: options?.messageId ?? null,
    sequence,
    source: options?.source ?? null,
    status
  }
}

export interface VoicePlaybackOptions {
  messageId?: string | null
  /**
   * Bir cümle DUYULMAYA başladığında çağrılır.
   *
   * İstenen: konuşulan cümle ekranda "transcript gibi sırayla ve ses ile
   * eşzamanlı" görünsün. Sunucu hangi cümleyi sentezlediğini biliyor ve ses
   * karesinden hemen önce bildiriyor; buradaki çağrı, o sesin GERÇEKTEN
   * başladığı ana ertelenmiş hâli.
   */
  onSentence?: (sentence: string) => void
  /**
   * Konuşulan cümlenin NEREYE kadar duyulduğu (0..1).
   *
   * İstenen: "modelin söyledikleri eş zamanlı, alt yazı geçer gibi... parça
   * parça gözükmeli, hem az yer kaplar hem de modelin neyi seslendirdiği
   * görülür."
   *
   * Oran TAHMİN DEĞİL: sesin kendi saatinden (``AudioContext.currentTime``)
   * ve o cümle için ZAMANLANMIŞ ses uzunluğundan geliyor. Bir cümlenin sesi
   * birden çok çerçevede gelebildiği için bitiş noktası çerçeve geldikçe
   * uzuyor; oran da onunla birlikte yeniden ölçekleniyor.
   */
  onSentenceProgress?: (sentence: string, ratio: number) => void
  source: VoicePlaybackSource
}

export function stopVoicePlayback() {
  sequence += 1
  currentStop?.()
  currentStop = null

  if (currentAudio) {
    currentAudio.pause()
    currentAudio.src = ''
    currentAudio.load()
    currentAudio = null
  }

  setVoicePlaybackState({
    audioElement: null,
    messageId: null,
    sequence,
    source: null,
    status: 'idle'
  })
}

// ---------------------------------------------------------------------------
// Streaming path — /api/audio/speak-stream WebSocket, raw int16 PCM frames
// scheduled through Web Audio. Speech starts on the provider's first chunk
// instead of after full synthesis + base64 transfer.
// ---------------------------------------------------------------------------

async function resolveSpeakStreamUrl(options?: VoicePlaybackOptions): Promise<null | string> {
  const desktop = window.foolDesktop

  if (!desktop?.getConnection) {
    return null
  }

  try {
    // Mint a fresh credential (single-use ticket in OAuth mode) for the
    // ACTIVE profile's backend, then swap the gateway endpoint for the PCM
    // one — auth is shared across WS routes.
    const profile = getApiRequestProfile()
    const wsUrl = await resolveGatewayWsUrl(desktop, await desktop.getConnection(profile))
    const url = new URL(wsUrl)

    if (!url.pathname.endsWith('/api/ws')) {
      return null
    }

    url.pathname = url.pathname.replace(/\/api\/ws$/, '/api/audio/speak-stream')

    // The backend resolves the TTS provider chain from this profile's
    // config/.env (same seam as /api/pty?profile=).
    if (profile) {
      url.searchParams.set('profile', profile)
    }

    // KIM konusuyor ve HANGI cevabi -- yalnizca gunluk icin.
    //
    // "Ayni cevap iki kez okunuyor" hatasi uc turdur kaynak okuyarak
    // bulunamadi. Sunucu tarafinda iki sentez gorunuyordu ama hangi yuzeyin
    // actigi hicbir yerde yazmiyordu, yani gunluk soruyu cevaplamiyordu.
    // Ucuz ve kalici bir ayirt edici: sorgu parametresi.
    if (options?.source) {
      url.searchParams.set('source', options.source)
    }

    if (options?.messageId) {
      url.searchParams.set('mid', options.messageId)
    }

    return url.toString()
  } catch {
    return null
  }
}

export interface SpeechStreamSession {
  /** Feed more reply text as it streams in. Safe after `finish` (no-op). */
  append: (text: string) => void
  /** No more text coming — resolves `done` once the audio drains. */
  finish: () => void
  /**
   * 'done'    — audio fully played (or barged via stopVoicePlayback)
   * 'fallback'— no audio ever produced; caller should speak the accumulated
   *             text through `playSpeechText` instead.
   */
  done: Promise<'done' | 'fallback'>
}

/**
 * Open a live speech session: one WebSocket + one AudioContext for a whole
 * reply. Text is appended as LLM deltas arrive; the server cuts sentences and
 * streams PCM back while generation continues, so speech overlaps the text
 * stream (ChatGPT-style) with no per-sentence connection or synthesis gaps.
 */
function openSpeechStream(wsUrl: string, options: VoicePlaybackOptions): SpeechStreamSession {
  const ws = new WebSocket(wsUrl)
  ws.binaryType = 'arraybuffer'

  let context: AudioContext | null = null
  let streamRate = 24_000
  let nextStartAt = 0
  //: Duyulmakta olan cümle ve sesinin ZAMANLANMIŞ sınırları. Alt yazının
  //: ilerleyişi buradan hesaplanıyor -- kelime hızı tahmininden değil.
  let spoken: null | { endsAt: number; startAt: number; text: string } = null
  let progressFrame = 0
  //: Sunucunun bildirdigi, HENUZ duyulmamis cumle.
  let pendingSentence: null | string = null
  let carry: null | Uint8Array = null
  let started = false
  let settled = false
  let finished = false
  const pendingSends: string[] = []

  let firstAudioTimer: null | number = null
  let settle: (value: 'done' | 'fallback') => void = () => undefined

  /** BU oturumun durdurma tutamaci -- kimligi ile karsilastirilabilsin diye. */
  const ownStop = () => settle('done')

  const done = new Promise<'done' | 'fallback'>(resolve => {
    settle = value => {
      if (settled) {
        return
      }

      settled = true

      // Alt yazi dongusunu birak: akis bittikten sonra donen bir kare
      // dongusu, hicbir sey gostermeden pil yakardi.
      if (progressFrame) {
        window.cancelAnimationFrame(progressFrame)
        progressFrame = 0
      }

      spoken = null

      // Yalnizca KENDI tutamacini birak.
      //
      // ``currentStop`` kuresel: o an konusan tek oturumu gosteriyor. Kosulsuz
      // ``null`` yazmak, gec kapanan ESKI bir oturumun YENI oturumun durdurma
      // tutamacini silmesi demekti -- ondan sonra ``stopVoicePlayback()``
      // sirayi ilerletip durumu 'idle' yaziyor ama soket ve ses baglami ayakta
      // kaliyor: kullanici Durdur'a basiyor, ekran susuyor, ses konusmaya
      // devam ediyor.
      if (currentStop === ownStop) {
        currentStop = null
      }

      if (firstAudioTimer !== null) {
        window.clearTimeout(firstAudioTimer)
        firstAudioTimer = null
      }

      try {
        ws.close()
      } catch {
        // already closed
      }

      void context?.close().catch(() => undefined)
      context = null
      resolve(value)
    }
  })

  const send = (frame: object) => {
    const data = JSON.stringify(frame)

    if (ws.readyState === WebSocket.OPEN) {
      ws.send(data)
    } else if (ws.readyState === WebSocket.CONNECTING) {
      pendingSends.push(data)
    }
  }

  // stopVoicePlayback() → immediate barge-in: kill the socket (the server
  // aborts synthesis on disconnect) and the audio context (cuts sound now).
  currentStop = ownStop

  const finishWhenDrained = () => {
    const remainingMs = context ? Math.max(0, nextStartAt - context.currentTime) * 1_000 : 0
    window.setTimeout(() => settle('done'), remainingMs + 100)
  }

  const schedule = (data: ArrayBuffer) => {
    if (!context) {
      return
    }

    // Provider chunks are not sample-aligned — carry any odd byte over.
    let bytes = new Uint8Array(data)

    if (carry) {
      const joined = new Uint8Array(carry.length + bytes.length)
      joined.set(carry)
      joined.set(bytes, carry.length)
      bytes = joined
      carry = null
    }

    const usable = bytes.length - (bytes.length % 2)

    if (bytes.length !== usable) {
      carry = bytes.slice(usable)
    }

    if (!usable) {
      return
    }

    const pcm = new Int16Array(bytes.buffer, bytes.byteOffset, usable / 2)
    const buffer = context.createBuffer(1, pcm.length, streamRate)
    const channel = buffer.getChannelData(0)

    for (let index = 0; index < pcm.length; index += 1) {
      channel[index] = pcm[index] / 32_768
    }

    const source = context.createBufferSource()
    source.buffer = buffer
    source.connect(context.destination)

    const startAt = Math.max(context.currentTime + 0.05, nextStartAt)
    source.start(startAt)

    // Cumleyi GELDIGI anda degil, DUYULDUGU anda bildir.
    //
    // Ses ileriye donuk zamanlaniyor (``nextStartAt``): sunucu bir sonraki
    // cumleyi biz oncekini dinlerken gonderiyor. Cerceve gelir gelmez yazmak,
    // henuz duyulmamis cumleyi ekrana koymak olurdu -- istenen tam tersi,
    // "ses ile eszamanli".
    if (pendingSentence !== null) {
      const sentence = pendingSentence
      const delayMs = Math.max(0, (startAt - context.currentTime) * 1000)

      pendingSentence = null
      window.setTimeout(() => options.onSentence?.(sentence), delayMs)

      // Alt yazının dayanağı: bu cümlenin sesi NEREDE başlıyor ve şu ana
      // kadar nereye kadar zamanlanmış. Sonraki çerçeveler geldikçe bitiş
      // uzuyor (aşağıda), oran da onunla ölçekleniyor.
      spoken = { endsAt: startAt + buffer.duration, startAt, text: sentence }
      startProgressLoop()
    } else if (spoken) {
      // Aynı cümlenin devamı: sesi uzadı.
      spoken.endsAt = startAt + buffer.duration
    }

    nextStartAt = startAt + buffer.duration

    if (!started) {
      started = true
      setVoicePlaybackState(currentState('speaking', options))
    }
  }

  /**
   * Alt yazı döngüsü: konuşulan cümlenin ne kadarının DUYULDUĞUNU bildirir.
   *
   * Kare başına bir kez, sesin kendi saatinden. Bir zamanlayıcıyla kelime
   * saymak sürüklenirdi -- ses hızlanıp yavaşlamıyor ama ağ gecikmesi
   * cümleler arasına boşluk koyuyor ve tahmin oradan kayardı.
   */
  function startProgressLoop(): void {
    if (progressFrame || !options.onSentenceProgress) {
      return
    }

    const tick = () => {
      progressFrame = 0

      const active = spoken

      if (!active || !context) {
        return
      }

      const span = active.endsAt - active.startAt

      const ratio =
        span > 0 ? (context.currentTime - active.startAt) / span : 1

      options.onSentenceProgress?.(active.text, Math.min(Math.max(ratio, 0), 1))

      if (ratio < 1) {
        progressFrame = window.requestAnimationFrame(tick)
      }
    }

    progressFrame = window.requestAnimationFrame(tick)
  }

  ws.onopen = () => {
    pendingSends.splice(0).forEach(data => ws.send(data))
  }

  ws.onmessage = event => {
    if (typeof event.data !== 'string') {
      schedule(event.data as ArrayBuffer)

      return
    }

    let frame: { channels?: number; sample_rate?: number; text?: string; type?: string }

    try {
      frame = JSON.parse(event.data) as typeof frame
    } catch {
      return
    }

    if (frame.type === 'sentence') {
      // Ses karesinden HEMEN once geliyor; ekrana yazilmasi o sesin baslama
      // anina erteleniyor (bkz. ``schedule``).
      pendingSentence = typeof frame.text === 'string' ? frame.text : null

      return
    }

    if (frame.type === 'start') {
      streamRate = frame.sample_rate || 24_000
      context = new AudioContext()

      // Autoplay policy can hand back a suspended context when playback wasn't
      // started by a user gesture (e.g. a wake-word-started voice turn). Resume
      // it so the first reply is audible instead of silently buffering. Electron
      // chat windows also set autoplayPolicy: no-user-gesture-required, but the
      // dashboard-embedded surface relies on this resume.
      if (context.state === 'suspended') {
        void context.resume().catch(() => undefined)
      }

      nextStartAt = 0
    } else if (frame.type === 'end') {
      // Synthesis can fail on the very first sentence (a crashed sidecar, a
      // transient engine timeout) with zero audio ever produced. The server
      // still closes the session cleanly with `end` in that case — nothing
      // is technically wrong with the WS itself. Treating that as `done`
      // told the caller "played successfully" when NOTHING was ever heard,
      // so a synthesis failure produced total silence with no fallback and
      // no retry. Same rule as onerror/onclose below: only a session that
      // actually started audio counts as done — and a started one must
      // still wait for the scheduled buffers to finish (`finishWhenDrained`),
      // not settle immediately and cut the last sentence off.
      if (started) {
        finishWhenDrained()
      } else {
        settle('fallback')
      }
    } else if (frame.type === 'fallback') {
      settle(started ? 'done' : 'fallback')
    }
  }

  // A drop before any audio means the endpoint is unavailable (old backend,
  // auth, network) → fall back. After audio started, replaying the whole
  // message via POST would stutter — treat what played as the playback.
  ws.onerror = () => settle(started ? 'done' : 'fallback')
  ws.onclose = () => (started ? finishWhenDrained() : settle('fallback'))

  return {
    // Raw deltas — the server strips markdown/emoji per *sentence*, which is
    // the only safe granularity when constructs span delta boundaries.
    append: text => {
      if (text && !finished && !settled) {
        // Bekçi İLK metinle kuruluyor, oturum açılırken değil: metin
        // gelmeden sentez başlamaz, o yüzden beklemenin sayacı burada başlar.
        if (firstAudioTimer === null && !started) {
          firstAudioTimer = window.setTimeout(() => {
            firstAudioTimer = null

            if (!started) {
              // ``fallback``: çağıran tek seferlik POST yoluna düşüyor. Sessiz
              // kalmaktansa geç konuşmak iyidir -- ve ``settle`` yalnızca bir
              // kez işlediği için çift sentez riski yok.
              settle('fallback')
            }
          }, FIRST_AUDIO_MS)
        }

        send({ text })
      }
    },
    finish: () => {
      if (!finished && !settled) {
        finished = true
        send({ done: true })
      }
    },
    done
  }
}

/**
 * Live-speak an in-progress reply: open a session, then `append` deltas and
 * `finish` when generation completes. Resolves null when streaming is
 * unavailable (old backend / non-chunked provider) — the caller falls back to
 * whole-text `playSpeechText`.
 */
export async function startSpeechStream(options: VoicePlaybackOptions): Promise<null | SpeechStreamSession> {
  // BIR cevap, BIR ses. Ikinci cagiran sessizce vazgeciyor.
  if (!claimSpeech(options.messageId)) {
    return null
  }

  const wsUrl = await resolveSpeakStreamUrl(options)

  if (!wsUrl) {
    // Kayit BIRAKILIYOR: hicbir ses uretilmedi. Bkz. asagidaki gerekce --
    // burada tutmak, cagiranin yedek yolunu kendi kaydiyla oldururdu.
    forgetSpokenMessage(options.messageId)

    return null
  }

  stopVoicePlayback()
  setVoicePlaybackState(currentState('preparing', options))

  const session = openSpeechStream(wsUrl, options)

  void session.done.then(outcome => {
    if (outcome === 'done') {
      setVoicePlaybackState(currentState('idle'))

      return
    }

    // ``fallback`` = HIC ses uretilmedi.
    //
    // Kayit "bu mesaj SESLENDIRILDI" demek; oturumun acilmis olmasi demek
    // degil. Ayrimi kaybetmek sessiz sinifin ders kitabi haliydi: cagiran
    // "ses cikmazsa metni yine oku" diye yedek yol yaziyor, o yol ayni
    // kimlikle ``playSpeechText`` cagiriyor ve KENDI kaydina takilip
    // ``false`` aliyordu. Yani yedek yol tam da devreye girmesi gereken anda
    // oluydu -- centigin yedegi (``fool/notch/use-notch-voice.ts``) birebir
    // boyleydi ve kullanici hicbir ses duymuyordu.
    //
    // Duzeltme cagri yerlerinde DEGIL burada: kural tek ve her cagiran icin
    // ayni. Her yuzeyin ayri ayri ``forgetSpokenMessage`` cagirmasi
    // gerekseydi, siradaki yuzey yine unuturdu.
    forgetSpokenMessage(options.messageId)
  })

  return session
}

/** One-shot playback of complete text over the streaming WS. */
function playSpeechStream(wsUrl: string, text: string, options: VoicePlaybackOptions): Promise<'fallback' | 'played'> {
  const session = openSpeechStream(wsUrl, options)
  session.append(text)
  session.finish()

  return session.done.then(outcome => (outcome === 'done' ? 'played' : 'fallback'))
}

async function playSpeechDataUrl(
  speakableText: string,
  options: VoicePlaybackOptions,
  isCurrent: () => boolean
): Promise<boolean> {
  const response = await speakText(speakableText)

  if (!isCurrent()) {
    return false
  }

  const audio = new Audio(response.data_url)
  currentAudio = audio
  setVoicePlaybackState(currentState('speaking', options, audio))

  await new Promise<void>((resolve, reject) => {
    let stall: number | null = null

    /** BU oynatmanin durdurma tutamaci. */
    const ownStop = () => {
      cleanup()
      resolve()
    }

    const cleanup = () => {
      if (stall !== null) {
        window.clearTimeout(stall)
        stall = null
      }

      audio.removeEventListener('ended', onEnded)
      audio.removeEventListener('error', onError)
      audio.removeEventListener('timeupdate', armStall)

      // Yalnizca KENDI tutamacini birak -- akis yolundaki ile ayni kural.
      if (currentStop === ownStop) {
        currentStop = null
      }
    }

    const armStall = () => {
      if (stall !== null) {
        window.clearTimeout(stall)
      }

      stall = window.setTimeout(() => {
        cleanup()
        reject(new Error('Playback stalled'))
      }, PLAYBACK_STALL_MS)
    }

    const onEnded = () => {
      cleanup()
      resolve()
    }

    const onError = () => {
      cleanup()
      reject(new Error('Playback failed'))
    }

    currentStop = ownStop

    audio.addEventListener('ended', onEnded, { once: true })
    audio.addEventListener('error', onError, { once: true })
    audio.addEventListener('timeupdate', armStall)
    armStall()
    // A wake-word-started turn has no user gesture, so the autoplay policy can
    // reject the first play() with NotAllowedError. Electron chat windows set
    // autoplayPolicy: no-user-gesture-required to prevent this, but retry once
    // after resuming a shared AudioContext as a fallback for other surfaces
    // (dashboard-embedded) so the first reply isn't silently dropped.
    void audio.play().catch(async () => {
      try {
        await unlockAutoplay()
        await audio.play()
      } catch {
        onError()
      }
    })
  })

  if (!isCurrent()) {
    return false
  }

  currentAudio = null

  return true
}

export async function playSpeechText(text: string, options: VoicePlaybackOptions): Promise<boolean> {
  // BIR cevap, BIR ses. ``stopVoicePlayback``tan ONCE: ikinci cagiranin ilk
  // cagiranin sesini kesmesi, tam olarak kacinilan sonuc.
  if (!claimSpeech(options.messageId)) {
    return false
  }

  stopVoicePlayback()

  const speakableText = sanitizeTextForSpeech(text)

  if (!speakableText) {
    return false
  }

  const ownSequence = sequence
  const isCurrent = () => ownSequence === sequence

  setVoicePlaybackState(currentState('preparing', options))

  try {
    // Streaming first; the POST data-URL path is the fallback for backends
    // without the WS endpoint or providers without a chunked API.
    const streamUrl = await resolveSpeakStreamUrl(options)

    if (streamUrl && isCurrent()) {
      const outcome = await playSpeechStream(streamUrl, speakableText, options)

      if (outcome === 'played') {
        if (!isCurrent()) {
          return false
        }

        setVoicePlaybackState(currentState('idle'))

        return true
      }
    }

    if (!isCurrent()) {
      return false
    }

    const played = await playSpeechDataUrl(speakableText, options, isCurrent)

    if (played) {
      setVoicePlaybackState(currentState('idle'))
    }

    return played
  } catch (error) {
    if (isCurrent()) {
      currentStop = null
      currentAudio = null
      setVoicePlaybackState(currentState('idle'))
    }

    throw error
  }
}

export function isVoicePlaybackActive() {
  return $voicePlayback.get().status !== 'idle'
}

// ---------------------------------------------------------------------------
// Interruption latch — the next prompt.submit carries `interrupted: true` so
// the model knows its spoken reply was cut off (it can react: "rude!").
// Marked by the barge-in paths (VAD, typing over playback); TTL'd so a stale
// barge never annotates an unrelated message minutes later.
// ---------------------------------------------------------------------------

const INTERRUPT_TTL_MS = 120_000
let interruptedAt: null | number = null

export function markVoicePlaybackInterrupted() {
  interruptedAt = Date.now()
}

export function takeVoicePlaybackInterrupted(): boolean {
  const at = interruptedAt
  interruptedAt = null

  return at !== null && Date.now() - at < INTERRUPT_TTL_MS
}

/**
 * Cut a spoken reply off because the user started talking (or typing) over it.
 *
 * Silencing and latching are one act, not two, and keeping them as two let one
 * surface do half of it. The composer's voice loop paired them at both of its
 * barge sites; the notch called `stopVoicePlayback()` alone at both of its own,
 * so interrupting the notch made the voice stop and told the model nothing —
 * it would carry on as though it had finished its sentence, which for a
 * character is the whole difference between being cut off and not.
 *
 * Every barge path goes through here now, so the two surfaces cannot drift
 * apart on it again.
 */
export function interruptVoicePlayback() {
  markVoicePlaybackInterrupted()
  stopVoicePlayback()

  // SESI CALAN pencere baska olabilir.
  //
  // ``stopVoicePlayback`` cagrildigi pencerenin kendi ``AudioContext``ini
  // durduruyor. Cevabi cogu zaman ANA pencere seslendiriyor (centik
  // ``canSpeak('notch')`` ile susuyor), yani centikten araya girmek kendi
  // sessizligini kesiyor ve kullanicinin duydugu ses calmaya devam ediyordu.
  //
  // Dinamik ice aktarma: bu modul tarayici yuzeyinde de kosuyor ve orada
  // masaustu koprusu yok; ayrica ``voice-stop-bridge`` bu modulu ice
  // aktardigi icin statik olsaydi dongu olurdu.
  void import('@/fool/voice-stop-bridge')
    .then(({ requestVoiceStopEverywhere }) => requestVoiceStopEverywhere())
    .catch(() => undefined)
}
