// Full-duplex VAD monitor: watch the mic across the agent turn — while the
// model is generating (no audio yet) AND while TTS plays — fire the moment the
// user talks over either phase, and CAPTURE what they say. Detection alone
// loses the first words — by the time sustained speech trips the trigger and a
// fresh recorder spins up, "stop, actually—" has become "actually—". So a
// MediaRecorder runs on the monitor's stream the whole time (pre-roll), and
// once tripped it keeps rolling until the user goes quiet, delivering the
// complete utterance.
//
// Phase-aware trigger (mirrors tools/voice_mode.full_duplex_listen on the
// Python surfaces):
// - The noise floor is calibrated from QUIET samples only — while no TTS audio
//   is flowing — and HELD through playback. Calibrating while the speaker is
//   audible bakes bleed into the floor and makes the trigger unreachable
//   (echoCancellation does not reliably cancel same-app playback on Windows).
// - During playback the trigger is additionally clamped up to a minimum so
//   bleed alone can't trip it, and capped so speech always remains reachable.
// - A short grace window after playback onset suppresses the start transient.
// - Detection is a windowed majority (>=80% of the last SUSTAINED_MS above
//   trigger) so intra-word energy dips don't reset progress.

const CALIBRATION_MS = 400
const SUSTAINED_MS = 300
const SUSTAINED_MAJORITY = 0.8
const MIN_TRIGGER_LEVEL = 0.075 // matches the voice loop's silenceLevel
const FLOOR_MULTIPLIER = 3.5
// Playback clamps, scaled from the Python constants (int16 RMS 1500 / 4000
// ≈ byte-domain level 0.14 / 0.37 with the /42 normalization below).
const PLAYBACK_MIN_TRIGGER_LEVEL = 0.14
const TRIGGER_CEILING_LEVEL = 0.37
const PLAYBACK_GRACE_MS = 500
const PLAYBACK_GAP_FOR_GRACE_MS = 1_000
const FLOOR_SAMPLE_CAP = 200 // ~3s of quiet-phase levels at rAF cadence
// Gurultu tabani ortancasi kac ornekte bir yeniden hesaplaniyor. 8 ornek
// ~350 ms: ortam gurultusunun degisme hizinin cok altinda, ama her tikteki
// kopyala+sirala isini 8'de bire indiriyor.
const FLOOR_MEDIAN_EVERY = 8
const PRE_ROLL_RESTART_MS = 5_000 // cap pre-roll: restart the recorder while quiet
const UTTERANCE_SILENCE_MS = 1_250 // matches the voice loop's silenceMs
const UTTERANCE_MAX_MS = 30_000

export interface BargeMonitorCallbacks {
  /** Sustained speech detected — cut playback / interrupt the turn now. */
  onSpeech: () => void
  /**
   * The interrupting utterance, complete from its first syllable (pre-roll
   * included), delivered once the user goes quiet. `null` when capture was
   * unavailable — fall back to normal listening.
   */
  onUtterance?: (audio: Blob | null) => void
  /**
   * Is TTS audio flowing RIGHT NOW? Drives the phase-aware trigger. Omitted
   * (legacy playback-only callers) means "always playing", which preserves
   * the old behavior of a monitor opened at playback start.
   */
  isPlaying?: () => boolean
}

export function monitorSpeechDuringPlayback(callbacks: BargeMonitorCallbacks): () => void {
  let disposed = false
  let stream: MediaStream | null = null
  let context: AudioContext | null = null
  let meter: ScriptProcessorNode | null = null
  let recorder: MediaRecorder | null = null
  let chunks: Blob[] = []
  let mimeType = ''

  const cleanup = () => {
    disposed = true

    if (meter) {
      meter.onaudioprocess = null
      meter.disconnect()
      meter = null
    }

    if (recorder && recorder.state !== 'inactive') {
      recorder.ondataavailable = null
      recorder.onstop = null

      try {
        recorder.stop()
      } catch {
        // already stopped
      }
    }

    recorder = null
    chunks = []
    void context?.close().catch(() => undefined)
    context = null
    stream?.getTracks().forEach(track => track.stop())
    stream = null
  }

  const startSegment = () => {
    if (!stream || typeof MediaRecorder === 'undefined') {
      return
    }

    mimeType =
      ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'].find(type =>
        MediaRecorder.isTypeSupported(type)
      ) ?? ''

    try {
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    } catch {
      recorder = null

      return
    }

    chunks = []

    recorder.ondataavailable = event => {
      if (event.data.size > 0) {
        chunks.push(event.data)
      }
    }

    recorder.start(250)
  }

  /** Restart the recorder to drop stale pre-roll — only valid while quiet. */
  const rotateSegment = () => {
    if (!recorder || recorder.state === 'inactive') {
      return
    }

    recorder.ondataavailable = null
    recorder.onstop = null

    try {
      recorder.stop()
    } catch {
      // already stopped
    }

    startSegment()
  }

  const finishCapture = () => {
    const active = recorder
    const type = active?.mimeType || mimeType || 'audio/webm'

    if (!active || active.state === 'inactive') {
      cleanup()
      callbacks.onUtterance?.(chunks.length ? new Blob(chunks, { type }) : null)

      return
    }

    active.onstop = () => {
      const audio = chunks.length ? new Blob(chunks, { type }) : null

      cleanup()
      callbacks.onUtterance?.(audio)
    }

    active.stop()
  }
  void (async () => {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true }
      })

      if (disposed) {
        cleanup()

        return
      }

      startSegment()

      context = new AudioContext()

      // Seviye ölçümü SES İŞ PARÇACIĞINDA koşuyor, ``requestAnimationFrame``
      // ile DEĞİL.
      //
      // Ölçülen sorun: rAF sayfa görünürlüğüne bağlı ve Chromium blurlanmış /
      // örtülmüş / küçültülmüş bir pencerede onu saniyede bire kadar
      // kısıyor. Araya girme tespiti son ``SUSTAINED_MS`` (300 ms) içindeki
      // örneklerin %80'ini istiyor; saniyede tek örnekle ``spanMs`` hiçbir
      // zaman 240 ms'e ulaşmıyor ve tetik ASLA çalışmıyor.
      //
      // Bu tam olarak notch'un var olma durumu: kullanıcı başka bir şeye
      // bakıyor, pencere ön planda değil. Yani araya girme, en çok gerektiği
      // anda ölüydü. (Uygulama akış sırasında kısmayı açıyor --
      // ``electron/stream-throttle.ts`` -- ama bu, bir turun "meşgul" diye
      // bildirilmesine bağlı bir zincir; ses ölçümünün ona bağlı olmaması
      // gerekiyor.)
      //
      // ``ScriptProcessorNode`` ses iş parçacığında çalışıyor ve sayfa
      // görünürlüğünden ETKİLENMİYOR. Eski (ama her yerde çalışan) bir düğüm;
      // ``AudioWorklet`` ayrı bir modül dosyası indirmeyi gerektiriyor ve
      // Electron'un CSP'si altında ek bir kırılganlık olurdu.
      const source = context.createMediaStreamSource(stream)

      meter = context.createScriptProcessor(2048, 1, 1)

      // ``onaudioprocess`` yalnızca düğüm bir hedefe BAĞLIYSA çalışıyor.
      // Hedef doğrudan hoparlör olamaz -- mikrofonu geri çalmak demek olurdu,
      // yani anında geri besleme. Kazancı sıfır bir düğümden geçiriliyor.
      const sink = context.createGain()

      sink.gain.value = 0
      source.connect(meter)
      meter.connect(sink)
      sink.connect(context.destination)

      const floorSamples: number[] = []
      const recentAbove: { above: boolean; at: number }[] = []
      let calibratedSince: number | null = null
      let floorLocked = false
      let quietFloor = 0
      let segmentStartedAt = Date.now()
      let wasPlaying = false
      let playbackSeen = false
      let lastPlayingAt = 0
      let graceUntil = 0
      let tripped = false
      let trippedAt = 0
      let quietSince: number | null = null

      // Ortanca her ORNEKTE degil, her ``FLOOR_MEDIAN_EVERY`` orneginde bir
      // hesaplaniyor.
      //
      // Eski hali her tikte 200 elemanlik bir dizi KOPYALAYIP siraliyordu ve
      // bu tik ses is parcaciginda, saniyede ~23 kez kosuyor -- yani sesli
      // turun her saniyesinde 23 tahsis + 23 siralama, sirf yavas suruklenen
      // bir gurultu tabani icin. Taban ortamin gurultusu: saniyeler
      // olceginde degisiyor, milisaniyeler olceginde degil.
      let sinceMedian = 0

      const recomputeFloor = () => {
        quietFloor = [...floorSamples].sort((a, b) => a - b)[floorSamples.length >> 1] ?? 0
      }

      const pushFloorSample = (level: number) => {
        floorSamples.push(level)

        if (floorSamples.length > FLOOR_SAMPLE_CAP) {
          floorSamples.shift()
        }

        sinceMedian += 1

        // Kalibrasyon penceresi kisa (400 ms): orada HER ornekte guncelleniyor,
        // yoksa ilk tetik yanlis bir tabanla karar verirdi.
        if (!floorLocked || sinceMedian >= FLOOR_MEDIAN_EVERY) {
          sinceMedian = 0
          recomputeFloor()
        }
      }

      const tick = (level: number) => {
        if (disposed) {
          return
        }

        const now = Date.now()
        const playing = callbacks.isPlaying ? callbacks.isPlaying() : true

        if (!tripped) {
          // Quiet-floor calibration: quiet-phase samples only. The floor is
          // HELD while audio plays — never recalibrated against speaker bleed.
          if (!floorLocked) {
            if (!playing) {
              calibratedSince ??= now
              pushFloorSample(level)
            }

            if (playing || (calibratedSince !== null && now - calibratedSince >= CALIBRATION_MS)) {
              floorLocked = true
            }
          }

          // Grace only when playback starts after a real gap, so flapping of
          // the playing flag between sentences can't chain grace windows.
          if (playing && !wasPlaying) {
            if (!playbackSeen || now - lastPlayingAt >= PLAYBACK_GAP_FOR_GRACE_MS) {
              graceUntil = now + PLAYBACK_GRACE_MS
            }

            playbackSeen = true
          }

          wasPlaying = playing

          if (playing) {
            lastPlayingAt = now
          }

          // Phase-aware trigger: quiet baseline x multiplier; playback clamps
          // it up (bleed alone can't trip) but a ceiling keeps speech
          // reachable even over loud playback.
          let trigger = Math.max(MIN_TRIGGER_LEVEL, quietFloor * FLOOR_MULTIPLIER)

          if (playing) {
            trigger = Math.min(Math.max(trigger, PLAYBACK_MIN_TRIGGER_LEVEL), TRIGGER_CEILING_LEVEL)
          }

          // Track ambient drift while quiet and below trigger.
          if (floorLocked && !playing && level < trigger) {
            pushFloorSample(level)
          }

          const above = floorLocked && level >= trigger && now >= graceUntil

          recentAbove.push({ above, at: now })

          while (recentAbove.length && now - recentAbove[0].at > SUSTAINED_MS) {
            recentAbove.shift()
          }

          const aboveCount = recentAbove.reduce((count, sample) => count + (sample.above ? 1 : 0), 0)
          const spanMs = recentAbove.length ? now - recentAbove[0].at : 0

          if (
            above &&
            spanMs >= SUSTAINED_MS * SUSTAINED_MAJORITY &&
            aboveCount >= recentAbove.length * SUSTAINED_MAJORITY
          ) {
            tripped = true
            trippedAt = now
            quietSince = null
            callbacks.onSpeech()

            if (!callbacks.onUtterance || !recorder) {
              cleanup()
              callbacks.onUtterance?.(null)

              return
            }
          } else if (!above) {
            // Bound the pre-roll while quiet so the utterance blob doesn't
            // accumulate the whole turn (rotating mid-speech would lose the
            // onset — the whole point).
            if (now - segmentStartedAt >= PRE_ROLL_RESTART_MS) {
              rotateSegment()
              segmentStartedAt = now
            }
          }
        } else {
          // Tripped: keep recording until the user goes quiet (endpoint).
          // Playback/generation was already cut, so silence-vs-speech works.
          if (level >= MIN_TRIGGER_LEVEL) {
            quietSince = null
          } else {
            quietSince ??= now
          }

          if ((quietSince && now - quietSince >= UTTERANCE_SILENCE_MS) || now - trippedAt >= UTTERANCE_MAX_MS) {
            finishCapture()

            return
          }
        }
      }

      meter.onaudioprocess = event => {
        if (disposed) {
          return
        }

        const samples = event.inputBuffer.getChannelData(0)

        let sum = 0

        for (const value of samples) {
          sum += value * value
        }

        // Eşiklerin hepsi eski BAYT alanına göre ayarlıydı (128 merkezli
        // Uint8, /42 ile normalize). Float32 (-1..1) aynı ölçeğe taşınıyor:
        // rms * 128 / 42. Böylece MIN_TRIGGER_LEVEL ve oynatma kenetleri
        // ölçüldükleri anlamlarını koruyor.
        const level = Math.min(1, (Math.sqrt(sum / samples.length) * 128) / 42)

        tick(level)
      }
    } catch {
      cleanup()
    }
  })()

  return cleanup
}
