import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { bindingMatches, parsePttBinding } from '@/fool/notch/ptt-binding'
import { $pttCode } from '@/fool/notch/ptt-store'
import { useI18n } from '@/i18n'
import { chatMessageText, collectUnspokenTurnSpeech, normalizeWs } from '@/lib/chat-messages'
import { triggerHaptic } from '@/lib/haptics'
import { clearWakeIndicator, syncWakeIndicatorWithVoice } from '@/lib/wake-indicator'
import { $voiceConversationStartRequest, takeVoiceConversationStart } from '@/store/composer'
import { resetBrowseState } from '@/store/composer-input-history'
import { $gateway } from '@/store/gateway'
import { notify, notifyError } from '@/store/notifications'
import { $autoSpeakReplies, $voiceStopPhrase, setAutoSpeakReplies } from '@/store/voice-prefs'
import { resumeWakeAfterVoice } from '@/store/wake-word'

import type { ComposerTarget } from '../focus'
import { onComposerVoiceToggleRequest } from '../focus'
import { useComposerScope } from '../scope'
import type { ChatBarProps } from '../types'

import { useAutoSpeakReplies } from './use-auto-speak-replies'
import { useVoiceConversation } from './use-voice-conversation'
import { useVoiceRecorder } from './use-voice-recorder'

interface UseComposerVoiceArgs {
  busy: boolean
  clearDraft: () => void
  disabled: boolean
  focusInput: () => void
  insertText: (text: string) => void
  maxRecordingSeconds: number
  /** Interrupt the in-flight agent turn (Stop-button seam) — fired when the
   *  user speaks over the model while it is still generating. */
  onInterrupt?: () => Promise<void> | void
  onSubmit: ChatBarProps['onSubmit']
  onTranscribeAudio: ChatBarProps['onTranscribeAudio']
  sessionId: string | null | undefined
  /** This composer's focus-bus key — voice toggles targeting another
   *  composer (or the active one, when not us) are ignored. */
  target: ComposerTarget
}

/**
 * The composer's voice engine: push-to-talk dictation (transcript → draft), the
 * full voice-conversation loop, and auto-speak of replies. Self-contained — it
 * consumes the draft/submit primitives passed in but nothing depends back on it,
 * so it lifts cleanly out of ChatBar.
 */
export function useComposerVoice({
  busy,
  clearDraft,
  disabled,
  focusInput,
  insertText,
  maxRecordingSeconds,
  onInterrupt,
  onSubmit,
  onTranscribeAudio,
  sessionId,
  target
}: UseComposerVoiceArgs) {
  const { t } = useI18n()
  // A tile's composer speaks ITS transcript, not the primary chat's.
  const { $messages } = useComposerScope()
  const [voiceConversationActive, setVoiceConversationActive] = useState(false)

  /**
   * Bu yüzeyin en son okuduğu cevap -- HANGİ OTURUMDA olduğuyla birlikte.
   *
   * Oturum da tutuluyor, çünkü işaretçi tek başına oturumlar arasında
   * anlamsız: başka bir sohbetin kimliğiyle karşılaştırılan bir cevap her
   * zaman "okunmamış" çıkar.
   *
   * Ölçülen hata: kullanıcının bildirdiği "bir yerden sonra yeni cevap yerine
   * önceki cevabı okumaya başladı". Çentik bu dersi çoktan öğrenmişti
   * (``use-notch-voice.ts`` montajda tohumluyor) ama besteci atlanmıştı --
   * bu depoda tekrar eden kalıbın bir örneği daha.
   */
  const lastSpokenIdRef = useRef<null | {
    id: null | string
    session: null | string
    /** Okunan METİN. Kimlik tek başına yetmiyor -- aşağıdaki nota bakın. */
    text: string
  }>(null)

  const ownsWakeIndicatorRef = useRef(false)
  const voiceStartRequest = useStore($voiceConversationStartRequest)

  const { dictate, voiceActivityState, voiceStatus } = useVoiceRecorder({
    focusInput,
    maxRecordingSeconds,
    onTranscript: insertText,
    onTranscribeAudio
  })

  /**
   * İşaretçiyi bu OTURUM için hazırla ve döndür.
   *
   * Tohumlama bir EFEKT DEĞİL, okumanın kendisinde: atomdan ref'e efektle
   * kopyalamak bir render geriden gelir (deponun lint kuralı da tam bunu
   * yasaklıyor) ve o bir render, geçmişteki cevabın "okunmamış" görünmesine
   * yetiyordu.
   *
   * Bir oturum AÇILDIĞINDA geçmişteki son cevap ekranda duruyor ve kullanıcı
   * onu çoktan görmüş; sesli okumak, sohbeti açar açmaz eski bir cevabın
   * konuşmaya başlaması demekti. Oturum DEĞİŞİNCE de yeniden tohumlanıyor --
   * yoksa yeni oturumun geçmişindeki son cevap, eski oturumun işaretçisiyle
   * karşılaştırılıp "okunmamış" çıkardı.
   */
  const spokenMarker = (): null | string => {
    const current = lastSpokenIdRef.current

    if (current && current.session === sessionId) {
      return current.id
    }

    const messages = $messages.get()
    const last = messages.findLast(m => m.role === 'assistant' && !m.hidden)
    const seeded = last?.id ?? null

    lastSpokenIdRef.current = {
      id: seeded,
      session: sessionId ?? null,
      text: last ? normalizeWs(chatMessageText(last)) : ''
    }

    return seeded
  }

  /** Auto-speak selector: the latest unspoken reply only — a backlog collapses to the newest. */
  const pendingResponse = () => {
    const spoken = spokenMarker()
    const messages = $messages.get()
    const last = messages.findLast(m => m.role === 'assistant' && !m.hidden)

    if (!last || last.id === spoken) {
      return null
    }

    const text = chatMessageText(last).trim()

    if (!text) {
      return null
    }

    // KİMLİK YETMİYOR: aynı cevap iki FARKLI kimlikle geliyor.
    //
    // Ölçüldü, günlükten (aynı metin, aynı yüzey, 30 saniye arayla)::
    //
    //   mid=assistant-stream-1788389050001-1        <- akış sırasındaki kimlik
    //   mid=1788389052.1867251-76-assistant         <- kalıcı arka uç kimliği
    //
    // Kalıcı satır yazılınca mesajın ``id``si değişiyor; akış kimliğini
    // "okundu" diye işaretlemek, yeni kimlikle gelen AYNI cevabı okunmamış
    // yapıyordu. Kullanıcının dört turdur bildirdiği "aynı cevabı 2 kere
    // okuyor" tam olarak buydu -- ve kimliğe dayanan her muhafaza (talep
    // anahtarı dahil) aynı delikten geçiyordu.
    //
    // İÇERİK kimlik şemasından bağımsız: aynı metni arka arkaya iki kez
    // okumamak, kimlik nasıl değişirse değişsin doğru davranış.
    if (lastSpokenIdRef.current && normalizeWs(text) === lastSpokenIdRef.current.text) {
      return null
    }

    return {
      id: last.id,
      pending: Boolean(last.pending),
      text
    }
  }

  /**
   * Voice-conversation selector: every unspoken assistant bubble of the turn,
   * in order — narration interims AND the final answer, not just whichever
   * bubble happens to be last. See `collectUnspokenTurnSpeech`.
   */
  const pendingTurnResponse = () => collectUnspokenTurnSpeech($messages.get(), spokenMarker())

  const consumePendingResponse = () => {
    const messages = $messages.get()
    const last = messages.findLast(m => m.role === 'assistant' && !m.hidden)

    if (last) {
      lastSpokenIdRef.current = {
        id: last.id,
        session: sessionId ?? null,
        text: normalizeWs(chatMessageText(last))
      }
    }
  }

  const submitVoiceTurn = async (text: string) => {
    if (busy) {
      return
    }

    triggerHaptic('submit')
    resetBrowseState(sessionId)
    clearDraft()
    await onSubmit(text)
  }

  const wakePausedRef = useRef(false)
  // Resolves once the in-flight wake.pause round-trip completes (mic released by
  // the wake listener). The conversation awaits this before opening its own mic
  // so the two never contend for the device — on Windows especially, opening the
  // capture device while the wake listener still holds it makes getUserMedia
  // fail and the conversation never starts listening.
  const wakePauseBarrierRef = useRef<Promise<void> | null>(null)

  const conversation = useVoiceConversation({
    busy,
    consumePendingResponse,
    enabled: voiceConversationActive,
    onFatalError: () => setVoiceConversationActive(false),
    // Speaking over the model mid-generation interrupts the in-flight turn —
    // the same seam as the Stop button — so the interjection becomes the next
    // turn instead of waiting behind a reply the user already rejected.
    onInterrupt,
    // A spoken stop command ("stop", "never mind", "goodbye", …) ends the
    // hands-free conversation. Flipping the flag is the authoritative off
    // switch — the enabled=false prop + effect below drive conversation.end()
    // teardown (mic close, wake re-arm).
    onStopWord: () => setVoiceConversationActive(false),
    onSubmit: submitVoiceTurn,
    onTranscribeAudio,
    pendingResponse: pendingTurnResponse,
    // Before the conversation opens the mic, wait for any in-flight wake.pause
    // to finish releasing the capture device (see wakePauseBarrierRef).
    beforeMicOpen: () => wakePauseBarrierRef.current ?? undefined
  })

  // eslint-disable-next-line no-restricted-syntax -- ownership token used only by unmount cleanup
  useEffect(() => {
    if (target !== 'main') {
      return
    }

    if (syncWakeIndicatorWithVoice(voiceConversationActive, conversation.status)) {
      ownsWakeIndicatorRef.current = voiceConversationActive
    }
  }, [conversation.status, target, voiceConversationActive])

  useEffect(
    () => () => {
      if (ownsWakeIndicatorRef.current) {
        clearWakeIndicator()
      }
    },
    []
  )

  // The `composer.voice` hotkey (Ctrl+B) toggles the conversation. Starting
  // with STT unconfigured lets the conversation surface its own "configure
  // speech-to-text" notice rather than silently no-opping.
  const toggleVoiceConversation = useCallback(() => {
    if (disabled) {
      return
    }

    if (voiceConversationActive) {
      setVoiceConversationActive(false)
      void conversation.end()
    } else {
      setVoiceConversationActive(true)
    }
  }, [conversation, disabled, voiceConversationActive])

  useEffect(
    () => onComposerVoiceToggleRequest(toggled => toggled === target && toggleVoiceConversation()),
    [target, toggleVoiceConversation]
  )

  useEffect(() => {
    if (target === 'main' && !disabled && takeVoiceConversationStart(voiceStartRequest) && !voiceConversationActive) {
      setVoiceConversationActive(true)
    }
  }, [disabled, target, voiceConversationActive, voiceStartRequest])

  const resumeWakeIfPaused = useCallback(() => {
    if (!wakePausedRef.current) {
      return
    }

    wakePausedRef.current = false
    wakePauseBarrierRef.current = null
    // Reconcile, don't just resume: the wake word is a persistent setting, so
    // ending a voice chat must re-arm the listener whenever config says
    // enabled — including when the raw resume loses the mic-release race.
    void resumeWakeAfterVoice()
  }, [])

  // The ref is a request token (did WE issue wake.pause?), not an atom mirror —
  // it guards resumeWakeIfPaused from resuming a detector another surface owns.
  const pauseWakeForVoice = useCallback(() => {
    wakePausedRef.current = true

    const barrier = (async () => {
      try {
        await $gateway.get()?.request('wake.pause', {})
      } catch {
        // No wake listener / older backend — nothing held the mic.
      }
    })()

    wakePauseBarrierRef.current = barrier

    return barrier
  }, [])

  useEffect(() => {
    if (voiceConversationActive) {
      pauseWakeForVoice()
    } else {
      resumeWakeIfPaused()
    }
  }, [pauseWakeForVoice, resumeWakeIfPaused, voiceConversationActive])

  // 'Say "stop" to end the voice chat.' notice when the conversation starts.
  // Phrase comes from voice.stop_phrases (first entry) so a custom phrase
  // renders correctly; a null phrase (stop_phrases: []) shows no notice.
  useEffect(() => {
    if (!voiceConversationActive) {
      return
    }

    const phrase = $voiceStopPhrase.get()

    if (phrase) {
      notify({
        id: 'voice-stop-hint',
        kind: 'info',
        icon: 'mic',
        message: t.notifications.voice.sayStopToEnd(phrase)
      })
    }
  }, [t, voiceConversationActive])

  useEffect(() => resumeWakeIfPaused, [resumeWakeIfPaused])

  // Explicit start/end for the on-screen conversation controls (the hotkey uses
  // the gated toggle above).
  const startConversation = useCallback(() => setVoiceConversationActive(true), [])

  const endConversation = useCallback(() => {
    setVoiceConversationActive(false)
    void conversation.end()
  }, [conversation])

  const handleToggleAutoSpeak = useCallback(() => {
    void setAutoSpeakReplies(!$autoSpeakReplies.get()).catch(error =>
      notifyError(error, t.settings.config.autosaveFailed)
    )
  }, [t])

  useAutoSpeakReplies({
    conversationActive: voiceConversationActive,
    failureLabel: t.assistant.thread.readAloudFailed,
    markSpoken: consumePendingResponse,
    pendingReply: pendingResponse,
    sessionId
  })

  /**
   * Sesli tur açıkken SAĞ CTRL bas-konuş.
   *
   * Kullanıcının isteği: "start conversation butonunu da isteğe bağlı
   * bas-konuşa alalım, sağ ctrl ile konuşabilelim, hem direkt cevap versin
   * hem konuşursak direkt interrupt olsun."
   *
   * Tuş kodu çentikle ORTAK depodan (``$pttCode``): iki yüzeyin farklı tuş
   * beklemesi, kullanıcının ayarı bir yerde değiştirip diğerinde çalışmadığını
   * görmesi olurdu.
   *
   * Sesle araya girme KAPANMIYOR -- ikisi aynı kapıyı paylaşıyor
   * (``fool/notch/barge-in.ts``), yani konuşmak da tuşa basmak da işe yarıyor
   * ve aynı cümle iki kez gönderilmiyor.
   */
  const pttCode = useStore($pttCode)

  useEffect(() => {
    if (!voiceConversationActive) {
      return
    }

    // Saklanan deger bir KOMBO olabilir (``Shift+ControlRight``): duz dize
    // karsilastirmasi onu hicbir olayla eslestiremezdi -- kullanici ayardan
    // komboyu kaydeder, centikte calisir, burada sessizce olurdu.
    const binding = parsePttBinding(pttCode)

    const onDown = (event: KeyboardEvent) => {
      if (!bindingMatches(binding, event) || event.repeat) {
        return
      }

      event.preventDefault()
      conversation.pttDown()
    }

    const onUp = (event: KeyboardEvent) => {
      // Birakmada YALNIZCA ``code``: kullanici Shift'i once birakirsa
      // ``ControlRight``in keyup'i ``shiftKey: false`` ile gelir ve tam
      // eslesme istemek mikrofonu sonsuza kadar acik birakirdi.
      if (event.code !== binding.code) {
        return
      }

      conversation.pttUp()
    }

    // Odak kaybi birakma sayiliyor: tus hala basili olsa bile ``keyup`` artik
    // bize gelmeyecek ve mikrofon sonsuza kadar acik kalirdi.
    const onBlur = () => conversation.pttUp()

    window.addEventListener('keydown', onDown)
    window.addEventListener('keyup', onUp)
    window.addEventListener('blur', onBlur)

    return () => {
      window.removeEventListener('keydown', onDown)
      window.removeEventListener('keyup', onUp)
      window.removeEventListener('blur', onBlur)
    }
  }, [conversation, pttCode, voiceConversationActive])

  return {
    conversation,
    dictate,
    endConversation,
    handleToggleAutoSpeak,
    startConversation,
    voiceActivityState,
    voiceConversationActive,
    voiceStatus
  }
}
