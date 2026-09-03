import { useStore } from '@nanostores/react'
import { useEffect, useRef } from 'react'

import { setSpokenSubtitle } from '@/fool/notch/active-session'
import { spokenSubtitle } from '@/fool/notch/subtitle'
import { voiceApi } from '@/fool/voice-api'
import { canSpeak } from '@/fool/voice-owner'
import { turnSpeechKey } from '@/lib/chat-messages'
import { planReplySpeech } from '@/lib/reply-speech-plan'
import { playSpeechText, type SpeechStreamSession, startSpeechStream } from '@/lib/voice-playback'
import { ownsAmbientCue, SPEECH_CLAIM_TTL_MS } from '@/store/ambient'
import { notifyError } from '@/store/notifications'
import { $voicePlayback } from '@/store/voice-playback'
import { $autoSpeakReplies } from '@/store/voice-prefs'

import { useComposerScope } from '../scope'

/**
 * Baska bir yuzeyin ustlendigi cevap kimlikleri icin ust sinir.
 *
 * Kayit yalnizca "bu cevabi bir daha talep etme" demek ve bir cevap ancak
 * geldigi anda talep ediliyor -- saatler sonra degil. Sinirsiz birakmak, uzun
 * bir oturumda her cevabin kimligini sonsuza kadar tutmakti.
 */
const DECLINED_CAP = 200

/** Kaydi ekle ve seti sinirda tut (en eskiler dusuyor). */
function rememberDeclined(declined: Set<string>, id: string): void {
  declined.add(id)

  while (declined.size > DECLINED_CAP) {
    const oldest = declined.values().next().value

    if (oldest === undefined) {
      return
    }

    declined.delete(oldest)
  }
}

interface LiveStream {
  id: string
  /** Bu oturuma gonderilen karakter sayisi. */
  sent: number
  session: SpeechStreamSession | null
}

interface AutoSpeakReply {
  id: string
  pending: boolean
  text: string
}

interface UseAutoSpeakReplies {
  conversationActive: boolean
  failureLabel: string
  /** Mark the current last reply spoken — shared dedupe with the conversation consumer. */
  markSpoken: () => void
  /** Latest completed assistant reply, or null; `pending` true while still streaming. */
  pendingReply: () => AutoSpeakReply | null
  /** Re-arm on session switch so opening a chat never reads its existing last reply. */
  sessionId: string | null | undefined
}

/**
 * Pure-TTS auto-speak: when `voice.auto_tts` is on, read each completed assistant
 * turn aloud — no dictation, no conversation loop. Stays off while a full voice
 * conversation runs (it speaks replies itself) and never overlaps clips: a reply
 * landing mid-playback is held and spoken on the playback-idle edge. Always reads
 * the latest reply, so a backlog collapses to the newest.
 */
export function useAutoSpeakReplies({
  conversationActive,
  failureLabel,
  markSpoken,
  pendingReply,
  sessionId
}: UseAutoSpeakReplies) {
  const enabled = useStore($autoSpeakReplies)
  // Wake on THIS composer's transcript: a tile subscribed to the primary's
  // would never fire on its own replies (and would fire on someone else's).
  const { $messages } = useComposerScope()
  // Acik akis oturumu ve ona KAC karakter gonderildigi. Reaktif bir degerin
  // aynasi degil: imperatif bir WebSocket tutamaci.
  const streamRef = useRef<LiveStream | null>(null)
  // Baska bir pencerenin ustlendigi cevaplar -- her tikte yeniden talep
  // etmemek icin.
  const declinedRef = useRef<Set<string>>(new Set())
  // Akis bu cevap icin HIC ses uretmedi: kimlik burada bekliyor ve cevap
  // tamamlaninca tek seferlik yoldan okunuyor. Yeni bir zamanlayici YOK --
  // kanca zaten ``$messages`` ve ``$voicePlayback`` tiklerinde uyaniyor.
  const fallbackRef = useRef<null | string>(null)
  const latest = useRef({ conversationActive, failureLabel, markSpoken, pendingReply })
  latest.current = { conversationActive, failureLabel, markSpoken, pendingReply }

  // ``streamRef`` ve ``declinedRef`` reaktif bir degerin AYNASI degil: biri
  // acik bir WebSocket oturumu ve ona kac karakter gonderildigi, digeri baska
  // bir pencerenin ustlendigi kimlikler. State'e tasimak her token'da yeniden
  // render tetiklerdi ve oturumu her degisimde sokup atardi -- yani her
  // cumlede yeni bir sentez baglantisi. Reaktif degerler (``$messages``,
  // ``$voicePlayback``) geri cagrilarda DOGRUDAN okunuyor, ki kuralin
  // korudugu sey de bu.
  // eslint-disable-next-line no-restricted-syntax -- yukaridaki gerekce
  useEffect(() => {
    if (!enabled) {
      return undefined
    }

    // Don't read whatever reply already sits at the bottom when the toggle flips
    // on (or a chat opens) — consume it so only later replies are spoken.
    latest.current.markSpoken()

    // Motoru SIMDIDEN isit.
    //
    // Isitma daha once yalnizca MIKROFON acilinca tetikleniyordu -- ama burasi
    // klavyeden yazilan sohbet, mikrofon hic acilmiyor. Otomatik okuma acikken
    // motor bos durup 300 sn sonra bosaltiliyor ve ilk cumle soguk yuklemeyi
    // bekliyor: olculdu, kokoro soguk 26,1 sn / sicak 0,55 sn.
    //
    // Otomatik okumanin ACIK olmasi zaten "her cevabi sesli istiyorum"
    // demek, yani isitma bosa gitmiyor. Cagri ucuz ve korumali: uc nokta
    // hemen donuyor ve motor zaten ayaktaysa yeni is baslatilmiyor.
    void voiceApi.warmVoice().catch(() => undefined)

    const speakLatest = () => {
      const { conversationActive, markSpoken, pendingReply } = latest.current

      // Cevap KORUMALARDAN ONCE okunuyor.
      //
      // Olculen hata: asagidaki iki erken cikis da cevabi TUKETMEDEN
      // donuyordu. Baska bir yuzey (centik) sesi devraldiginda burasi
      // sessizce cekiliyor, ama o cevap bu yuzey icin "okunmamis" olarak
      // kuyrukta kaliyordu. Centik oturumu bitince ve herhangi bir
      // ``$messages`` tikinde -- kullanicinin YENI istem yazmasi da bir tik --
      // ``pendingReply()`` hala ONCEKI cevabi donduruyor ve burasi onu
      // okumaya basliyordu.
      //
      // Kullanicinin bildirdigi birebir: "bir yerden sonra yeni cevap yerine
      // onceki cevabi okumaya basladi... yeni cevap gelene kadar onceki
      // mesaji okumayi baslattigi icin yeni cevap geldiginde 2 ses ayni anda
      // konusuyor gibi oluyordu."
      //
      // Hakem karari verdi ama KAYBEDEN tarafi kaydetmedi: cekilen yuzeyin
      // de "bu cevap benden gecti" demesi gerekiyor.
      const declineCurrent = () => {
        const current = pendingReply()

        if (current) {
          rememberDeclined(declinedRef.current, current.id)
        }
      }

      if (conversationActive) {
        // Konusma kipi bu cevabi kendisi okuyor.
        declineCurrent()

        return
      }

      // ``$voicePlayback`` kontrolu BURADA DEGIL, planlayicida.
      //
      // Akisa gecerken bu satiri oldugu yerde biraktim ve akisi kendi elimle
      // oldurdum: ilk parca gonderiliyor, ses calmaya basliyor, durum
      // 'speaking' oluyor ve ondan SONRAKI her ``$messages`` tiki buradan
      // geri donuyordu. Kalan metin ancak oynatma bosa dustugunde gidiyor --
      // yani konusma parca parca ilerliyor ve kullanicinin bildirdigi
      // gecikme hissi ortaya cikiyor.
      //
      // Kuralin kendisi DOGRU ama yalnizca YENI bir oturum acarken gecerli:
      // onceki cevap konusurken yenisine baslamak ikisini ust uste bindirirdi.
      // ``planReplySpeech`` onu tam o noktada uyguluyor (``playbackIdle``).

      // FOOL-SEAM: voice-owner
      //
      // Friend penceresi ya da notch konusuyorsa sohbet paneli SUSMALI.
      //
      // ``ownsAmbientCue`` yalnizca PENCERELER arasi: ayni sohbet iki
      // pencerede acikken tek biri okusun diye. Yuzeyler arasinda hicbir sey
      // yoktu ve sonucu kullanicinin gunlugunde goruluyor -- ayni cumle iki
      // kez sentezleniyordu:
      //
      //   fool-speak-stream-nl_653jl.wav   (Friend'in akis yolu)
      //   cache/audio/tts_20260821_...wav  (buranin tek-seferlik yolu)
      //
      // Ustteki ``$voicePlayback`` kontrolu YETMIYOR: iki yuzey de ayni
      // ``$messages`` tikinda uyaniyor ve burasi, Friend daha 'preparing'
      // yazmadan geciyor. Sahiplik o yarisi tasimiyor -- kim konusacaksa
      // ONCEDEN yazili (bkz. ``fool/voice-owner.ts``, ki basligi tam olarak
      // bu hatayi anlatiyor).
      if (!canSpeak('composer')) {
        // Ayni pencerede baska bir yuzey devraldi. Acik oturumu KAPATIYORUZ:
        // sessizce donmek onu yarim birakir ve hicbir sey bitirmezdi.
        streamRef.current?.session?.finish()
        streamRef.current = null

        // Ve cevabi TUKET: devreden yuzey onu okuyor, burasi bir daha
        // talep etmemeli. Bu satir olmadan cevap kuyrukta kaliyor ve sahiplik
        // birakildigi anda ESKI bir cevap sesli okunuyordu.
        declineCurrent()

        return
      }

      const reply = pendingReply()

      // YEDEK YOL: akis bu cevap icin hic ses uretmedi.
      //
      // Buranin planlayicidan ONCE gelmesi sart: ``planReplySpeech`` acik
      // oturum gormeyince ``open`` doner ve ayni akisi bastan acardi -- yani
      // ses uretmeyen yol sonsuza kadar kendini tekrar ederdi.
      if (fallbackRef.current) {
        if (!reply || reply.id !== fallbackRef.current) {
          // Cevap degisti: bekleyen yedek artik gecersiz.
          fallbackRef.current = null
        } else {
          // Metin hala akiyorsa bekle: yarim cevabi okumak, kalanini hic
          // okumamak olurdu.
          if (reply.pending || $voicePlayback.get().status !== 'idle') {
            return
          }

          fallbackRef.current = null
          markSpoken()

          // ``messageId`` VERILIYOR: pencere ici tekillestirme burada da
          // gecerli. Kayit ``startSpeechStream`` tarafindan zaten birakildi
          // (ses uretilmedi), o yuzden bu cagri gecebiliyor.
          void playSpeechText(reply.text, { messageId: reply.id, source: 'read-aloud' }).catch((error: unknown) =>
            notifyError(error, latest.current.failureLabel)
          )

          return
        }
      }

      const live = streamRef.current

      // Karar tablosu AYRI ve saf: bkz. ``lib/reply-speech-plan.ts``.
      const action = planReplySpeech({
        declined: Boolean(reply && declinedRef.current.has(reply.id)),
        live: live ? { id: live.id, sent: live.sent } : null,
        playbackIdle: $voicePlayback.get().status === 'idle',
        reply
      })

      if (action.kind === 'wait') {
        return
      }

      if (action.kind === 'retire') {
        // Cevap degisti: eski seridi birakma.
        setSpokenSubtitle('')
        live?.session?.finish()
        streamRef.current = null

        return
      }

      if (action.kind === 'open') {
        const id = action.id
        const entry: LiveStream = { id, sent: 0, session: null }

        streamRef.current = entry

        // Ayni sohbet birkac pencerede acikken cevabi TEK biri seslendirir.
        // Talep ANA SURECTE cozuluyor (``electron/event-dedupe.ts``).
        //
        // Anahtar TURU gosteriyor, mesaji degil: burasi turun SON mesajinin
        // kimligini, centik ise ILK mesajinkini kullaniyordu ve bir tur
        // birden cok gorunur mesaj urettiginde ikisi de kendi talebini
        // kazanip ayni cevabi iki kez okuyordu.
        void ownsAmbientCue(`speak:${turnSpeechKey($messages.get()) ?? id}`, SPEECH_CLAIM_TTL_MS)
          .then(owns => {
            if (!owns) {
              rememberDeclined(declinedRef.current, id)

              if (streamRef.current === entry) {
                streamRef.current = null
              }

              return null
            }

            // ALT YAZIYI YAYINLA: çentik artık konuşmuyor, gösteriyor.
            //
            // Çentik ayrı bir ``BrowserWindow`` ve kendi ``$messages``i ana
            // pencerenin bir tur gerisinde; oradan karar vermek şeritte ESKİ
            // cevabın görünmesine yol açıyordu. Konuşan taraf kim ise alt
            // yazıyı da o yayınlıyor (bkz. ``active-session.ts``).
            return startSpeechStream({
              messageId: id,
              onSentence: sentence => setSpokenSubtitle(spokenSubtitle(sentence, 0)),
              onSentenceProgress: (sentence, ratio) =>
                setSpokenSubtitle(spokenSubtitle(sentence, ratio)),
              source: 'read-aloud'
            })
          })
          .then(session => {
            if (streamRef.current !== entry) {
              // Bu arada cevap degisti: acilan oturumu ORTADA birakma.
              session?.finish()

              return
            }

            entry.session = session

            if (!session) {
              // Akis yok (eski arka uc / saglayici parcali API sunmuyor).
              // Cevap tamamlaninca tek seferlik yoldan okunuyor: bu satir bir
              // yorum olarak VARDI ama karsiligi hic yazilmamisti, yani
              // ozellik acikken hicbir ses cikmiyordu.
              streamRef.current = null
              fallbackRef.current = id
              speakLatest()

              return
            }

            // Akis ACILDI ama ses uretmeyebilir (sentez dustu, motor soguk
            // kaldi). ``done`` -> 'fallback' tam olarak bunu bildiriyor ve
            // ``startSpeechStream`` o durumda seslendirme kaydini birakiyor,
            // yani asagidaki tek seferlik cagri gecebiliyor.
            void session.done.then(outcome => {
              if (outcome !== 'fallback') {
                return
              }

              if (streamRef.current === entry) {
                streamRef.current = null
              }

              fallbackRef.current = id
              speakLatest()
            })

            // Acilis gecikmis olabilir; o ana kadar birikmis metni HEMEN
            // yolla, yoksa bas taraf kaybolur.
            speakLatest()
          })
          .catch((error: unknown) => {
            if (streamRef.current === entry) {
              streamRef.current = null
            }

            notifyError(error, latest.current.failureLabel)
          })

        return
      }

      if (!live?.session) {
        // Oturum henuz acilmadi: ``open`` dalindaki geri cagri tekrar cagiracak.
        return
      }

      if (action.kind === 'append') {
        live.session.append(action.text)
        live.sent = action.sent

        return
      }

      // action.kind === 'finish'
      live.session.finish()
      streamRef.current = null
      markSpoken()
      // ŞERİDİ temizle: çentik bunu okuyor ve boşalmazsa orada asılı kalır
      // (durum da ``speaking``de takılırdı -- bkz. ``$mainTurnBusy``).
      setSpokenSubtitle('')
    }

    // Re-check on a reply completing ($messages) and on the prior clip ending
    // ($voicePlayback → idle), which frees us to read the next held reply.
    const stops = [$messages.subscribe(speakLatest), $voicePlayback.listen(speakLatest)]

    return () => {
      stops.forEach(f => f())
      // Oturum degisti ya da ozellik kapandi: acik akisi ORTADA birakma.
      streamRef.current?.session?.finish()
      streamRef.current = null
      fallbackRef.current = null
    }
  }, [$messages, enabled, sessionId])
}
