import { useEffect, useRef, useState } from 'react'

type BrowserAudioContext = typeof AudioContext

export interface MicRecorderOptions {
  onLevel?: (level: number) => void
  onError?: (error: Error) => void
  onSilence?: () => void
  silenceLevel?: number
  silenceMs?: number
  idleSilenceMs?: number
}

export interface MicRecording {
  audio: Blob
  durationMs: number
  heardSpeech: boolean
}

export interface MicRecorderErrorCopy {
  microphoneAccessDenied: string
  microphoneConstraintsUnsupported: string
  microphoneInUse: string
  microphonePermissionDenied: string
  microphoneStartFailed: string
  microphoneUnsupported: string
  noMicrophone: string
}

interface MicRecorderHandle {
  start: (options?: MicRecorderOptions) => Promise<void>
  stop: () => Promise<MicRecording | null>
  cancel: () => void
}

/**
 * ``MediaRecorder.stop()`` cagrisindan sonra ``onstop`` icin beklenecek en
 * uzun sure.
 *
 * Deger: kapanma bir arabellek bosaltma islemi, sentez ya da ag degil.
 * Chromium'da olculen 20-80 ms; 4 saniye en kotu halin cok ustunde ve
 * asilmayi sonsuzdan cikariyor.
 */
const STOP_TIMEOUT_MS = 4_000

/**
 * Seviye kac basamaga yuvarlanarak React durumuna yaziliyor.
 *
 * Tuketici bes cubukluk bir dalga formu; 24 basamak gozun ayirt edebilecegi
 * her seyi tasiyor ve sessizlikte degeri sabit tutarak gereksiz renderi
 * tumden kaldiriyor.
 */
const LEVEL_STEPS = 24

function micError(error: unknown, copy: MicRecorderErrorCopy): Error {
  const name = error instanceof DOMException ? error.name : ''

  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return new Error(copy.microphonePermissionDenied)
  }

  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return new Error(copy.noMicrophone)
  }

  if (name === 'NotReadableError' || name === 'TrackStartError') {
    return new Error(copy.microphoneInUse)
  }

  if (name === 'OverconstrainedError') {
    return new Error(copy.microphoneConstraintsUnsupported)
  }

  if (error instanceof Error) {
    return error
  }

  return new Error(copy.microphoneStartFailed)
}

export function useMicRecorder(copy: MicRecorderErrorCopy): {
  handle: MicRecorderHandle
  level: number
  recording: boolean
} {
  const [level, setLevel] = useState(0)
  const [recording, setRecording] = useState(false)

  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const audioContextRef = useRef<AudioContext | null>(null)
  const meterRef = useRef<ScriptProcessorNode | null>(null)
  const startedAtRef = useRef(0)
  const heardSpeechRef = useRef(false)
  const silenceTriggeredRef = useRef(false)
  const silenceStartedAtRef = useRef<number | null>(null)
  // Durum olarak YAZILMIS son basamak. Reaktif bir degerin aynasi degil:
  // yalnizca ``setLevel``i tekrar cagirmamak icin bir karsilastirma noktasi.
  const lastLevelRef = useRef(0)
  const stopResolverRef = useRef<((recording: MicRecording | null) => void) | null>(null)

  const cleanup = () => {
    if (meterRef.current) {
      meterRef.current.onaudioprocess = null
      meterRef.current.disconnect()
      meterRef.current = null
    }

    void audioContextRef.current?.close()
    audioContextRef.current = null
    streamRef.current?.getTracks().forEach(track => track.stop())
    streamRef.current = null
    recorderRef.current = null
    lastLevelRef.current = 0
    setLevel(0)
    setRecording(false)
    silenceTriggeredRef.current = false
  }

  useEffect(() => () => cleanup(), [])

  const startMeter = (stream: MediaStream, options: MicRecorderOptions) => {
    const audioWindow = window as Window & { webkitAudioContext?: BrowserAudioContext }
    const AudioContextCtor = window.AudioContext || audioWindow.webkitAudioContext

    if (!AudioContextCtor) {
      return
    }

    try {
      const audioContext = new AudioContextCtor()
      const analyser = audioContext.createAnalyser()
      const source = audioContext.createMediaStreamSource(stream)

      analyser.fftSize = 256
      const data = new Uint8Array(analyser.fftSize)

      source.connect(analyser)
      audioContextRef.current = audioContext

      // Ölçüm SES İŞ PARÇACIĞINDA koşuyor, ``requestAnimationFrame``da değil.
      //
      // Sessizlik saptayıcısı (``onSilence``) yalnızca bu tikte
      // değerlendiriliyor, yani turun NEREDE biteceğine karar veren şey bu.
      // rAF pencere gizlendiğinde/örtüldüğünde kısılıyor ya da tümden
      // duruyor: ana pencere küçültülmüşken eller serbest bir tur başlatan
      // kullanıcının kaydı hiç bitmiyordu -- mikrofon açık kalıyor, cümle
      // gönderilmiyor.
      //
      // ``ScriptProcessorNode`` sayfa görünürlüğünden etkilenmiyor. Aynı
      // gerekçe ve aynı düğüm ``lib/voice-barge-in.ts``de de kullanılıyor;
      // ``AudioWorklet`` ayrı bir modül dosyası indirmeyi gerektiriyor ve
      // Electron'un CSP'si altında ek bir kırılganlık olurdu.
      const meter = audioContext.createScriptProcessor(2048, 1, 1)

      // ``onaudioprocess`` yalnızca düğüm bir hedefe BAĞLIYSA çalışıyor.
      // Hedef doğrudan hoparlör olamaz: mikrofonu geri çalmak, yani anında
      // geri besleme olurdu. Kazancı sıfır bir düğümden geçiriliyor.
      const sink = audioContext.createGain()

      sink.gain.value = 0
      source.connect(meter)
      meter.connect(sink)
      sink.connect(audioContext.destination)
      meterRef.current = meter

      const tick = () => {
        if (!meterRef.current) {
          return
        }

        analyser.getByteTimeDomainData(data)

        let sum = 0

        for (const value of data) {
          const centered = value - 128
          sum += centered * centered
        }

        const rms = Math.sqrt(sum / data.length)
        const normalized = Math.min(1, rms / 42)
        const now = Date.now()

        // Seviye React durumuna BASAMAKLANDIRILARAK yaziliyor.
        //
        // Bu geri cagri ses is parcaciginda, 2048 orneklik bloklarla kosuyor:
        // 48 kHz'de saniyede ~23 kez. Her tikte ham bir kayan noktayi
        // ``setLevel``e vermek, sesli tur acik oldugu SURECE saniyede 23 kez
        // butun besteci agacini yeniden render etmek demekti -- ve seviyenin
        // tuketicisi bes cubukluk bir dalga formu, yani o hassasiyetin
        // hicbiri ekrana ulasmiyor.
        //
        // Sessizlikte deger neredeyse sabit oldugu icin basamak degismiyor ve
        // render HIC olmuyor; konusma sirasinda degisiyor ve dalga formu
        // gorunurde ayni kaliyor.
        const stepped = Math.round(normalized * LEVEL_STEPS) / LEVEL_STEPS

        if (stepped !== lastLevelRef.current) {
          lastLevelRef.current = stepped
          setLevel(stepped)
        }

        // Geri cagri HAM degeri aliyor: sessizlik esigi burada degerlendiriliyor
        // ve basamaklandirmak turun nerede bittigini kaydirirdi.
        options.onLevel?.(normalized)

        const speechThreshold = options.silenceLevel ?? 0
        const silenceMs = options.silenceMs ?? 0
        const idleSilenceMs = options.idleSilenceMs ?? 0

        if (speechThreshold > 0 && options.onSilence && !silenceTriggeredRef.current) {
          if (normalized >= speechThreshold) {
            heardSpeechRef.current = true
            silenceStartedAtRef.current = null
          } else if (heardSpeechRef.current && silenceMs > 0) {
            silenceStartedAtRef.current ??= now

            if (now - silenceStartedAtRef.current >= silenceMs) {
              silenceTriggeredRef.current = true
              options.onSilence()

              return
            }
          } else if (!heardSpeechRef.current && idleSilenceMs > 0 && now - startedAtRef.current >= idleSilenceMs) {
            silenceTriggeredRef.current = true
            options.onSilence()

            return
          }
        }
      }

      meter.onaudioprocess = tick
    } catch {
      setLevel(0)
    }
  }

  const start: MicRecorderHandle['start'] = async (options = {}) => {
    if (recorderRef.current) {
      return
    }

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      throw new Error(copy.microphoneUnsupported)
    }

    const permitted = await window.foolDesktop?.requestMicrophoneAccess?.()

    if (permitted === false) {
      throw new Error(copy.microphoneAccessDenied)
    }

    let stream: MediaStream

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true }
      })
    } catch (error) {
      throw micError(error, copy)
    }

    const mimeType =
      ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/ogg', 'audio/wav'].find(
        type => MediaRecorder.isTypeSupported(type)
      ) ?? ''

    let recorder: MediaRecorder

    try {
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    } catch (error) {
      stream.getTracks().forEach(track => track.stop())
      throw micError(error, copy)
    }

    chunksRef.current = []
    streamRef.current = stream
    recorderRef.current = recorder
    heardSpeechRef.current = false
    silenceTriggeredRef.current = false
    silenceStartedAtRef.current = null
    startedAtRef.current = Date.now()

    recorder.ondataavailable = event => {
      if (event.data.size > 0) {
        chunksRef.current.push(event.data)
      }
    }

    recorder.onstop = () => {
      const chunks = chunksRef.current
      const recordingType = recorder.mimeType || mimeType || 'audio/webm'
      const durationMs = Date.now() - startedAtRef.current
      const heardSpeech = heardSpeechRef.current

      chunksRef.current = []
      cleanup()

      const resolver = stopResolverRef.current
      stopResolverRef.current = null

      if (!chunks.length) {
        resolver?.(null)

        return
      }

      resolver?.({
        audio: new Blob(chunks, { type: recordingType }),
        durationMs,
        heardSpeech
      })
    }

    recorder.onerror = event => {
      const error = micError((event as Event & { error?: unknown }).error, copy)
      const resolver = stopResolverRef.current
      stopResolverRef.current = null
      cleanup()
      options.onError?.(error)
      resolver?.(null)
    }

    recorder.start()
    setRecording(true)
    startMeter(stream, options)
  }

  const stop: MicRecorderHandle['stop'] = () =>
    new Promise<MicRecording | null>(resolve => {
      const recorder = recorderRef.current

      if (!recorder || recorder.state === 'inactive') {
        cleanup()
        resolve(null)

        return
      }

      // ``stop()`` HER ZAMAN cozuluyor -- ne firlatiyor ne asili kaliyor.
      //
      // Cagiran bunu bekliyordu ama sozlesme yaziliydi, uygulanmiyordu.
      // Ikisi de olculdu ve ikisi de SESSIZ:
      //
      //   - ``MediaRecorder.stop()`` aygit/surucu degisiminde
      //     ``InvalidStateError`` firlatiyor. Soz yurutucusunun icinden
      //     firlayan hata sozu REDDEDIYOR ve ``void handleTurn()`` diye
      //     cagiran tarafta yakalayan kimse yok.
      //   - ``onstop`` hic gelmiyor. O zaman soz hic cozulmuyor.
      //
      // Ikisinin de sonucu ayni: sesli tur ``transcribing``de kaliyor,
      // ``startListening`` yalnizca ``idle``de actigi icin mikrofon bir daha
      // ASLA acilmiyor. Kullanicinin gordugu, hicbir hata vermeden olen bir
      // sesli sohbet.
      let settled = false
      let timer: null | number = null

      const settle = (recording: MicRecording | null) => {
        if (settled) {
          return
        }

        settled = true

        if (timer !== null) {
          window.clearTimeout(timer)
          timer = null
        }

        if (stopResolverRef.current === settle) {
          stopResolverRef.current = null
        }

        resolve(recording)
      }

      stopResolverRef.current = settle

      timer = window.setTimeout(() => {
        // ``onstop`` gelmedi. Elde ne varsa onunla don: hicbir sey yoksa
        // ``null`` -- cagiran bunu "kayit yok" diye okuyup donguyu yeniden
        // kuruyor. Sonsuza kadar beklemekten her hali iyi.
        const chunks = chunksRef.current
        const recordingType = recorder.mimeType || 'audio/webm'
        const durationMs = Date.now() - startedAtRef.current
        const heardSpeech = heardSpeechRef.current

        chunksRef.current = []
        cleanup()
        settle(chunks.length ? { audio: new Blob(chunks, { type: recordingType }), durationMs, heardSpeech } : null)
      }, STOP_TIMEOUT_MS)

      try {
        recorder.stop()
      } catch {
        // Aygit zaten kapanmis. Kaydi birak ve donguyu serbest birak.
        cleanup()
        settle(null)
      }
    })

  const cancel: MicRecorderHandle['cancel'] = () => {
    const recorder = recorderRef.current
    const resolver = stopResolverRef.current
    stopResolverRef.current = null

    if (recorder && recorder.state !== 'inactive') {
      recorder.ondataavailable = null
      recorder.onerror = null
      recorder.onstop = null
      recorder.stop()
    }

    cleanup()
    resolver?.(null)
  }

  const handle: MicRecorderHandle = { start, stop, cancel }

  return { handle, level, recording }
}
