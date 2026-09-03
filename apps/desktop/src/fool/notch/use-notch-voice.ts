/**
 * Notch'un ses akışı: bas → konuş → bırak → gönder → dinle.
 *
 * Neden mevcut ``useVoiceConversation`` kullanılmıyor
 * ---------------------------------------------------
 * O kanca farklı bir etkileşim modeli: sesle uyanıyor, sessizliği kendi
 * saptayıp kaydı kendi kapatıyor ve cevaptan sonra kendini yeniden kuruyor
 * (VAD döngüsü). Bas-konuş bunun tam tersi — kaydın ne zaman başlayıp
 * biteceğine KULLANICI karar veriyor. İkisini tek kancaya sıkıştırmak, sessizlik
 * saptayıcısının kullanıcı hâlâ tuşu basılı tutarken kaydı kapatması demek
 * olurdu: cümlenin ortasında kesilen bir kayıt.
 *
 * Paylaşılan parçalar yine de ortak: mikrofon kaydedicisi, transkripsiyon ucu,
 * gönderim RPC'si ve "hangi baloncuk henüz seslendirilmedi" seçicisi. Yeniden
 * yazılan tek şey akışın kendisi.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { useMicRecorder } from '@/app/chat/composer/hooks/use-mic-recorder'
import { useGatewayRequest } from '@/app/gateway/hooks/use-gateway-request'
import { blobToDataUrl } from '@/app/session/hooks/use-prompt-actions/utils'
import { transcribeAudio } from '@/hermes'
import { useI18n } from '@/i18n'
import { monitorSpeechDuringPlayback } from '@/lib/voice-barge-in'
import {
  interruptVoicePlayback,
  playSpeechText,
  takeVoicePlaybackInterrupted
} from '@/lib/voice-playback'
import { isVoiceStopCommand } from '@/lib/voice-stop-word'
import { $busy, $messages } from '@/store/session'
import { $voicePlayback } from '@/store/voice-playback'

import { voiceApi } from '../voice-api'
import { claimVoice, releaseVoice } from '../voice-owner'
import { $voiceWarm } from '../voice-warm'

import { $mainTurnBusy, $spokenSubtitle, $voiceSessionId, requestVoiceSubmit, setNotchVoiceActive, setSpokenSubtitle, waitForVoiceSessionOrOpen } from './active-session'
import {
  type BargeGate,
  claimBarge,
  createBargeGate,
  forceClaimBarge,
  isPlayingPhase,
  releaseBarge,
  shouldMonitorBargeIn
} from './barge-in'
import {
  type BeginActivation,
  listenOptionsFor,
  modeForActivation
} from './hands-free'
import { interruptThenSubmit, shouldInterruptTurn } from './interrupt'
import { $listenMode } from './listen-mode'
import { createPttSpeechState, observeLevel } from './ptt-speech'
import {
  createFillerState,
  FILL_AFTER_MS,
  resetTurn,
  shouldFill,
  takeFiller
} from './thinking-filler'

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

export type NotchStatus = 'idle' | 'listening' | 'transcribing' | 'thinking' | 'speaking'

/** Uyandirma onayi. KISA olmasi sart: dinleme bu ses bitene kadar baslamiyor. */
export const WAKE_ACK_TEXT = "I'm listening"

/**
 * Ses için beklenecek en uzun süre.
 *
 * Oynatma katmanının kendi bekçileri var (ilk-ses ve duraklama sınırları); bu
 * yalnızca takılı bir oynatmanın çentiği sonsuza kadar açık bırakmaması için.
 */
const TURN_AUDIO_CAP_MS = 120_000

export interface NotchVoice {
  /** Son hata — notch'ta kısa bir satır olarak gösteriliyor. */
  error: null | string
  /** Araya girme yakalaması sürüyor mu? Yeniden açma kararını besliyor. */
  capturing: boolean
  /** Son turda hiç konuşma duyuldu mu? Sessiz tur sayacını besliyor. */
  heardSpeech: boolean
  /** Mikrofon seviyesi 0..1; dalga formunu bu besliyor. */
  level: number
  /** Ajanın son cevabı -- notch onu GÖSTERİYOR, sadece okumuyor. */
  reply: string
  /** Uyandirma turu: onay sesi + tek seferlik sessizlik-bitisli yakalama. */
  beginWakeTurn: () => Promise<void>
  /** Kullanıcının son söylediği (yazıya dökülmüş) metin. */
  transcript: string
  status: NotchStatus
  /**
   * Kaydı aç. ``'key'`` tuşa basıldı (bas-konuş), ``'auto'`` eller serbest
   * döngüsü kendiliğinden açtı (sessizlik kaydı bitirir).
   */
  begin: (activation?: BeginActivation) => void
  /** Tuş bırakıldı — kaydı kapat, yaz, gönder. */
  commit: () => void
  /** İptal: kaydı at, hiçbir şey gönderme. */
  cancel: () => void
  /** Notch oturumu kapandı — arkadaş oturumunu unut. */
  endSession: () => void
}

interface NotchVoiceOptions {
  /**
   * Kullanıcı "dur" dedi (ya da "boşver", "hoşça kal"...).
   *
   * ``useVoiceConversation`` ile AYNI ad ve AYNI anlam. Sohbet kipi bu
   * sözcükleri bir tur olarak GÖNDERMİYOR, konuşmayı bitiriyor; notch
   * göndermeye devam ediyordu, yani "dur" demek modele "dur" yazmaktı ve
   * konuşma hiç bitmiyordu. Kullanıcının istediği "notch bu conversation
   * modun birebir aynısı olmalı" tam olarak bu tür farklar.
   */
  onStopWord?: () => void
}

export function useNotchVoice({ onStopWord }: NotchVoiceOptions = {}): NotchVoice {
  const { t } = useI18n()
  // Akan mesajlar: abonelik efekt icine gomulmuyor -- kod tabaninin kurali
  // reaktif degeri dogrudan okumak (ref'e aynalamak bir render geç kalir).
  const messages = useStore($messages)
  // Dinleme kipi: bas-konusta ses ile araya girme kapali (asagi bak).
  const listenMode = useStore($listenMode)
  // Mikrofon hata metinleri uygulamada ZATEN çevrili duruyor; sabit yazmak
  // notch'u tek dile çivilerdi.
  const { handle: mic, level } = useMicRecorder(t.notifications.voice)
  const { requestGateway } = useGatewayRequest()

  const [status, setStatus] = useState<NotchStatus>('idle')

  /**
   * Bu turu ÇENTİK mi seslendirecek — ana pencereye bildiriliyor.
   *
   * ``thinking`` = çentik az önce gönderdi ve cevabı bekliyor, yani o cevabı
   * KENDİSİ okuyacak. Önceliği daha ilk token gelmeden bildirmek yarışı
   * ortadan kaldırıyor: besteci çekiliyor, akışı çentik açıyor ve cümle
   * ilerleyişini duyduğu için ALT YAZI her seferinde çıkıyor.
   *
   * Kapsam DAR ve bilerek: "çentik penceresi açık" demek DEĞİL. Öyle
   * yayınlamıştım ve sonucu daha kötü bir hataydı -- besteci susuyor, çentiğin
   * durumu ``idle`` olduğu için o da konuşmuyor ve hiçbir ses çıkmıyordu.
   *
   * ``idle``de bırakılıyor: bırakmazsak bir kez üstlenilen tur, sonraki bütün
   * cevapları da sessize alırdı.
   */
  useEffect(() => {
    setNotchVoiceActive(status === 'thinking' || status === 'speaking')
  }, [status])

  useEffect(() => () => setNotchVoiceActive(false), [])
  // Oynatma geri cagriminin GUNCEL durumu gormesi icin. Kapanis
  // sirasindaki state degeri bayat olur ve yaris kaybedilir.
  const statusRef = useRef<NotchStatus>('idle')

  statusRef.current = status
  const [transcript, setTranscript] = useState('')
  // Ajanin cevabi. Notch artik sohbet yuzeyi: kullanici ne dendigini
  // GORMELI, yalnizca duymak gurultulu bir odada yetmiyor.
  // Konuşulan alt yazı ANA PENCEREDEN geliyor (paylaşılan atom): konuşan taraf
  // kim ise şeridi de o yayınlıyor.
  const reply = useStore($spokenSubtitle)

  // Ana penceredeki tur sürüyor mu.
  const mainBusy = useStore($mainTurnBusy) === '1'
  const [error, setError] = useState<null | string>(null)
  // Geri cagirim ref'te: ``submitAudio`` bagimliligina koymak, cagiran her
  // yeni fonksiyon verdiginde onu yeniden kurardi ve suren bir yakalamayi
  // koparirdi. (Reaktif deger DEGIL -- bir prop.)
  const onStopWordRef = useRef(onStopWord)

  onStopWordRef.current = onStopWord

  // Hangi baloncuğa kadar seslendirdiğimiz. Bu olmadan her cevap baştan
  // okunurdu.
  //
  // ``ref`` DEĞİL state: değeri akan mesajlardan türüyor, yani reaktif. Ref'e
  // aynalamak bir render geç kalır ve aynı baloncuk iki kez seslendirilebilir.
  /**
   * AÇILIŞTA var olan mesajlar SESLENDİRİLMİŞ sayılıyor.
   *
   * Ölçülen kırıklık: burası ``null`` başlıyordu, yani
   * ``collectUnspokenTurnSpeech`` çentik açılır açılmaz sohbetin SON cevabını
   * "henüz seslendirilmemiş" sayıyor, onu okuyor ve ekrana yazıyordu.
   * Kullanıcının gördüğü: çentik açık sohbetteki eski mesajı gösteriyor --
   * "bu kısıma sadece modelin anlık olarak seslendirdiği cevap gelmeli."
   *
   * Geçmişi okumak zaten yanlış: çentik bir sohbet penceresi değil, O ANIN
   * sesi. Açılışta duran her şey geçmiştir.
   *
   * MOUNT anında bir kez okunuyor (state başlatıcı), efektle değil: bir efekt
   * mesajlar her değiştiğinde koşar ve HENÜZ SESLENDİRİLMEMİŞ yeni bir cevabı
   * da "geçmiş" diye işaretleyip sesi tamamen susturabilirdi.
   */
  const [lastSpokenId, setLastSpokenId] = useState<null | string>(() => {
    const initial = $messages.get()

    return initial[initial.length - 1]?.id ?? null
  })

  // Bir kaydın atılacağını işaretler. `commit` ve `cancel` yarışabiliyor
  // (tuş bırakma ile odak kaybı aynı anda gelebilir); ilk gelen kazanır.
  const discardRef = useRef(false)
  // Suren akis oturumu ve o oturuma KADAR gonderilmis karakter sayisi.
  // Turu kimin kestigi. Tus ve ses ayni anda gelebiliyor; kapisiz birakmak
  // ayni cumleyi modele iki kez gonderiyordu.
  const bargeRef = useRef<BargeGate>(createBargeGate())
  // Baska bir yuzeyin ustlendigi cevaplar. Bu olmadan efekt her token'da
  // yeniden talep ederdi -- saniyede onlarca bosuna IPC.
  // Bu turun EN GUNCEL konusma metni.
  //
  // Yedek yol bunu okuyor, akisin acilisinda yakalanan ``pending`` nesnesini
  // DEGIL: o nesne oturum acilirken donduruluyor ve cevap o anda daha yeni
  // baslamis oluyor. Kapanista onu okumak, uzun bir cevabin yalnizca ilk
  // cumlesini seslendirmek demekti. Ustelik cevap tamamlaninca
  // ``lastSpokenId`` yaziliyor ve ``collectUnspokenTurnSpeech`` artik ``null``
  // donuyor -- yani metni geri okumanin baska yolu kalmiyor.
  // Akis bu cevap icin HIC ses uretmedi: kimlik burada bekliyor ve cevap
  // TAMAMLANINCA tek seferlik yoldan okunuyor.
  // Yedek yol metin AKARKEN kurulduysa efektin bir kez daha kosmasi gerekiyor:
  // cevap zaten tamamlanmissa yeni bir ``messages`` tiki gelmeyebilir.
  // Araya girme yakalamasi SURUYOR mu? Izleyici, durum 'listening'e dondugu
  // an sokulup atilirsa yakaladigi cumleyi teslim edemeden olur -- yani
  // kullanicinin araya girerken soyledigi sey kaybolur. Bu bayrak izleyiciyi
  // teslimat bitene kadar ayakta tutuyor.
  const [capturing, setCapturing] = useState(false)
  // Son turda konuşma duyuldu mu? Boşta zaman aşımıyla kapanan bir kayıt
  // "kullanıcı orada değil" demek; sessiz tur sayacı bunu sayıyor.
  const [heardSpeech, setHeardSpeech] = useState(false)
  // Doldurma durumu ref'te: klavye/zamanlayici yollarindan okunuyor ve
  // state'e tasimak her turda gereksiz render demekti.
  const fillerRef = useRef(createFillerState())
  // Bu turda cevaptan metin geldi mi? Geldiyse sessizlik bitti.
  const speechStartedRef = useRef(false)
  // Metin bitti ama SES sürüyor: tur, oynatma boşa düşene kadar ayakta.
  const awaitingPlaybackRef = useRef(false)
  // Bu basışta konuşma duyuldu mu? Araya girme kararını bu taşıyor.
  const speechGateRef = useRef(createPttSpeechState())
  // Sesli arkadasin KENDI oturumu. Bugune kadar masaustu sohbet panelinin
  // oturumu kullaniliyordu ve o oturum ``desktop`` kapsaminda kuruluyor:
  // olculdu, 21 takim / 73 arac / 8 tanesi makineye dokunuyor. Yani "hava
  // nasil?" diyen arkadas ``terminal_run`` ve ``computer_use``a sahipti.
  // ``onSilence`` geri çağrımı ``commit``ten ÖNCE kuruluyor; ref olmadan
  // tanımlanmamış bir değere kapanır.
  const commitRef = useRef<() => void>(() => undefined)

  // Suren turu ag gecidinde DURDUR.
  //
  // Oynatmayi kesmek yetmiyordu: model cevabi uretmeye devam ediyor, kalan
  // tokenlar geliyor ve ``collectUnspokenTurnSpeech`` onlari YENI tur
  // bittikten sonra seslendiriyor -- kullanici sozunu kesti, ajan biraz sonra
  // kaldigi yerden devam ediyor. Composer tarafi bu dikisi zaten kullaniyordu
  // (``use-voice-conversation.ts``), notch hic kullanmiyordu.
  const haltTurn = useCallback(async () => {
    if (!shouldInterruptTurn(statusRef.current)) {
      return
    }

    // Durdurma YALNIZCA arkadas oturumuna gidiyor.
    //
    // Burada ``?? $voiceSessionId.get()`` vardi ve hemen ustundeki yorumun
    // yasaklad|g| seyi yap|yordu: arkadas oturumu henuz acilmamisken
    // bas-konusa basmak, kullanicinin SOHBET PANELINDE suren isini
    // kesiyordu. Yorum ile kod ayrismisti.
    //
    // Durduracak bir sey yoksa dogru davranis hicbir sey yapmamak.
    const sessionId = $voiceSessionId.get()

    if (!sessionId) {
      return
    }

    await requestGateway('session.interrupt', { session_id: sessionId })
  }, [requestGateway])

  //
  // ÖN ISITMA: oturum, kullanıcı KONUŞMAYA BAŞLARKEN çözülüyor.
  //
  // Ölçülen kırıklık: akış sırayla koşuyordu -- kayıt biter, yazıya dökülür
  // (saniyeler), SONRA oturum çözülür ve oturum yoksa ana pencereden bir tane
  // istenip 12 saniyeye kadar beklenirdi. Kullanıcının gördüğü: "transcribing
  // biter bitmez modele cevap gitmiyor, arada bir boşluk var" -- ve o boşlukta
  // ana pencere yeni bir sohbet açtığı için başka bir oturumun mesajı bir an
  // görünüp kayboluyordu.
  //
  // Oysa oturumu açmak için konuşmanın BİTMESİNİ beklemek gerekmiyor: kullanıcı
  // konuşurken açılabilir. Yazıya dökme bittiğinde oturum çoktan hazır oluyor
  // ve boşluk kapanıyor.
  const sessionPromiseRef = useRef<null | Promise<string>>(null)

  /** Oturumu ŞİMDİ istemeye başla (beklemeden). Konuşma başlarken çağrılıyor. */
  const prewarmSession = useCallback(() => {
    if (!sessionPromiseRef.current) {
      // Hata YUTULUYOR: burası ateşle-unut. Gerçek hata ``resolveSessionId``
      // beklerken yeniden yüzeye çıkıyor.
      sessionPromiseRef.current = waitForVoiceSessionOrOpen().catch(() => '')
    }
  }, [])

  const resolveSessionId = useCallback(async () => {
    // Ön ısıtma varsa ONU bekle -- ikinci bir istek ikinci bir oturum açardı.
    const pending = sessionPromiseRef.current ?? waitForVoiceSessionOrOpen()
    sessionPromiseRef.current = null

    return pending
  }, [])

  const begin = useCallback((activation: BeginActivation = 'key') => {
    // Motor ISINMADAN bas-konus acilmiyor.
    //
    // Istenen: "sadece isinma hazir oldugunda notch bas konusu calissin, o
    // zamana kadar notchta TTS isiniyor gibi bilgi yazsin."
    //
    // Sebebi olculdu: soguk motorda ilk cumle 36,8 sn suruyor. Mikrofonu o
    // sirada acmak, kullanicinin konusup dakikalarca sessizlik dinlemesi
    // demek -- ve konustugu cumle o sure boyunca hicbir yere gitmiyor.
    //
    // ``failed`` ENGELLEMIYOR: isinmayi bekleyemedigimiz icin kullaniciyi
    // susturmak, isinmamis bir motorla konusmasina izin vermekten kotu.
    if (activation !== 'auto' && $voiceWarm.get() === 'warming') {
      // Metin KULLANICIYA gorunuyor.
      setError('Warming up the voice — one moment')
      setStatus('idle')

      return
    }

    setError(null)
    // Oturumu ŞİMDİ açtırmaya başla: kullanıcı konuşurken hazır olsun.
    prewarmSession()
    discardRef.current = false
    // Tuşa basmak açık bir niyet: sesle başlamış bir yakalama varsa devral.
    // Kapıyı ilk gelene bırakmak tuşu sessizce yutardı — mikrofon açılmaz,
    // kullanıcı boşluğa konuşurdu.
    forceClaimBarge(bargeRef.current, 'key')
    // Kullanici notch'ta konusmaya basladi: sesin sahibi o (Friend
    // penceresi acik degilse).
    claimVoice('notch')
    setCapturing(false)
    setHeardSpeech(false)

    // ŞERİT DİNLEME BAŞLARKEN temizleniyor, yazıya dökme bitince DEĞİL.
    //
    // Ölçülen hata: temizlik ``setTranscript``in yanındaydı, yani ancak
    // konuşma yazıya dökülünce oluyordu. Kullanıcı sağ Ctrl'ye bastığında
    // önceki cevabın şeridi hâlâ duruyor: ``subtitleMode`` açık kaldığı için
    // çentik geniş kalıyor ve dinleme arkaplanı yüzünden küçülmeden kırmızıya
    // dönüyordu. Kullanıcının bildirdiği birebir buydu.
    setSpokenSubtitle('')
    setStatus('listening')

    // Motoru KULLANICI KONUŞURKEN ısıt.
    //
    // Isıtma bugüne kadar yalnızca çentik oturumu AÇILIRKEN çağrılıyordu.
    // Motor boşta 300 sn sonra boşaltıldığı için (kullanıcının kendi isteği)
    // her uzun aradan sonra soğuk bedel geri geliyordu: ölçüldü, kokoro
    // soğuk 29,43 sn / sıcak 1,07 sn.
    //
    // Zamanlayıcıyla sıcak tutmak YANLIŞ cevap olurdu -- kullanıcı motorun
    // 5 dakika sonra kapanmasını açıkça istedi. Doğru an bu: mikrofon
    // açılıyor, kullanıcı konuşmaya başlıyor ve yükleme o saniyelerin
    // arkasına gizleniyor. Cevap akmaya başladığında motor ayakta oluyor.
    //
    // Çağrı UCUZ ve korumalı: uç nokta hemen dönüyor ve ``tts_warmup.warm``
    // zaten ısınıyorsa yeni iş başlatmıyor.
    void voiceApi.warmVoice().catch(() => undefined)
    // Bekleyen "sesi bekle" bayrağı düşüyor: kullanıcı yeni bir tur açtı.
    awaitingPlaybackRef.current = false

    // ARAYA GİRME BURADA DEĞİL.
    //
    // Eskiden ``stopVoicePlayback()`` ve ``haltTurn()`` tam burada, tuşa
    // BASILDIĞI anda çağrılıyordu. Yani sağ Ctrl'ye yanlışlıkla dokunmak --
    // ya da ne söyleyeceğine karar vermeden basmak -- modelin cevabını
    // öldürüyordu, üstelik geri dönüşü olmadan.
    //
    // Kullanıcının istediği kural: tuşa basılması yetmez, o tuş basılıyken
    // GERÇEKTEN konuşulduğu anlaşıldığında kesilsin. Karar aşağıdaki
    // ``onLevel`` geri çağrısında, eşik ve süre kuralı ``./ptt-speech.ts``de.
    speechGateRef.current = createPttSpeechState()

    // Eller serbest kipte kaydın sınırını sessizlik çiziyor; bas-konuşta
    // KULLANICI çiziyor. İkisine aynı ayarı vermek, tuş hâlâ basılıyken
    // kaydın kapanması demekti — cümlenin ortasında kesilen bir kayıt.
    const options = listenOptionsFor(modeForActivation(activation))

    const onLevel = (level: number) => {
      const speaking = observeLevel(speechGateRef.current, {
        level,
        now: Date.now(),
        // Eşik oynatma sırasında yükseliyor: hoparlör sızıntısı tek başına
        // araya girme sayılmamalı.
        playing: $voicePlayback.get().status !== 'idle'
      })

      if (!speaking) {
        return
      }

      setHeardSpeech(true)
      // ŞİMDİ araya giriliyor: akış oturumu kapanıyor, ses kesiliyor ve süren
      // tur durduruluyor -- yoksa eski cevabın kalanı yeni turdan sonra
      // konuşulur.
      // Susturmak ve MODELE SOYLEMEK tek is: bkz. ``interruptVoicePlayback``.
      // Burada yalnizca susturuluyordu, yani centikte sozunu kestiginizde
      // model bunu hic ogrenmiyor ve cumlesini bitirmis gibi devam ediyordu.
      interruptVoicePlayback()
      void haltTurn().catch(() => undefined)
    }

    void mic
      .start({
        ...(options ?? {}),
        onLevel,
        ...(options
          ? {
              onSilence: () => {
                // Sessizlik turu bitirdi: konuşma duyulmuştu, yoksa
                // ``onSilence`` değil boşta zaman aşımı çalışırdı.
                setHeardSpeech(true)
                commitRef.current()
              }
            }
          : {})
      })
      .catch((cause: unknown) => {
        setStatus('idle')
        setError(cause instanceof Error ? cause.message : String(cause))
      })
  }, [haltTurn, mic, prewarmSession])

  /**
   * Notch kapandı — mikrofonu bırak ama SOHBETİ BİTİRME.
   *
   * Eskiden burada ``forgetCompanionSession`` vardı ve notch'u kapatmak
   * hafızayı siliyordu. Ölçüldü (kullanıcının ``state.db``si): 14 Friend
   * oturumu, ortalama 4,6 mesaj -- masaüstü sohbetinde 28,3. Yeni bir sohbet
   * artık açık bir eylem (bkz. ``friend-session.ts``).
   */
  const endSession = useCallback(() => {
    releaseVoice('notch')
  }, [])

  const cancel = useCallback(() => {
    discardRef.current = true
    void mic.stop()
    releaseBarge(bargeRef.current)
    setCapturing(false)
    setStatus('idle')
  }, [mic])

  /**
   * Sesin gittiği oturum: KULLANICININ AÇIK SOHBETİ.
   *
   * Arada hiçbir şey yok. Önce sesin kendi ``companion``/``friend`` kapsamı
   * vardı ve ayrı bir oturum açıyordu; Friend/Jarvis kipleri kaldırıldığı
   * için o ayrım da kalktı. Kullanıcının isteği birebir: "direkt olarak
   * chatten konuşabilelim, hiçbir aracı olmadan sesimiz direkt modele
   * gitsin."
   *
   * Sonucu açıkça yazılmalı: ses artık sohbet panelinin kapsamında koşuyor
   * (``desktop`` -- terminal, dosya, kod dahil). Bunu ayıran mekanizma
   * kiplerdi ve kipler kullanıcının kararıyla kaldırıldı.
   */
  // Oturum YOKSA ana pencereden bir tane ISTIYOR (bkz. ``active-session.ts``).
  // Eskiden burasi bos donuyordu ve kullanici, ekranda acik bir sohbet olmadigi
  // icin, konustugu cumleyi kaybediyordu.



  // Yazıya dök ve gönder. İKİ giriş yolu paylaşıyor: tuşla biten kayıt ve
  // araya girerken yakalanan cümle. Ayrı yazmak, ikisinden birinin canlı
  // oturum kimliği gibi bir ayrıntıyı kaçırması demekti.
  const submitAudio = useCallback(
    async (audio: Blob) => {
      const dataUrl = await blobToDataUrl(audio)

      // KENDI SINIRI: bas-konus klibi kisa, bekleme de kisa olmali.
      //
      // Olculdu (``hermes.ts``): yaziya dokme isteginin zaman asimi TABANI
      // 180 SANIYE (tavan 600). O sure uzun bir bulut kaydi icin makul, iki
      // saniyelik bir bas-konus klibi icin felaket: motor mesgulse -- ornegin
      // suren bir tur arkasinda kuyruga girmisse -- centik uc dakika boyunca
      // "Transcribing..." yazip sessiz kaliyor. Kullanicinin bildirdigi
      // "transcribingde takili kaldi" bu.
      //
      // Paylasilan sabit DEGISTIRILMEDI: ayni deger besteci diktesini de
      // besliyor ve orada uzun kayit normal. Sinir yalnizca bu yuzeyde.
      const TRANSCRIBE_LIMIT_MS = 45_000

      const result = await Promise.race([
        transcribeAudio(dataUrl, audio.type),
        new Promise<never>((_resolve, reject) =>
          setTimeout(
            () =>
              reject(
                new Error(
                  'Transcription is taking too long — the engine may be busy with the current answer'
                )
              ),
            TRANSCRIBE_LIMIT_MS
          )
        )
      ])

      const text = (result.transcript ?? '').trim()

      if (!text) {
        // Sessiz kayıt. Boş metin göndermek ajanı boşluğa cevap vermeye
        // zorlardı; sessizce başa dönmek doğru.
        setStatus('idle')
        releaseBarge(bargeRef.current)

        return
      }

      // "Dur" bir TUR DEGIL.
      //
      // Sohbet kipi bunu zaten boyle ele aliyordu; notch metni oldugu gibi
      // gonderiyordu, yani konusmayi bitirmenin sesli yolu yoktu ve model
      // "dur" diye bir mesaj aliyordu. Esleme YALNIZCA butun cumle bir
      // durdurma ifadesiyken tutuyor, o yuzden "stop the container" gercek
      // bir istek olarak gecmeye devam ediyor.
      if (isVoiceStopCommand(text)) {
        interruptVoicePlayback()
        void haltTurn().catch(() => undefined)
        releaseBarge(bargeRef.current)
        setCapturing(false)
        setStatus('idle')
        onStopWordRef.current?.()

        return
      }

      setTranscript(text)
      setSpokenSubtitle('')
      // Yeni tur: doldurma hakki yenileniyor, sessizlik sayaci sifirlaniyor.
      resetTurn(fillerRef.current)
      speechStartedRef.current = false
      setStatus('thinking')
      // Yeni tur başladı: bir sonraki araya girme kapıyı yeniden talep
      // edebilmeli.
      releaseBarge(bargeRef.current)

      // CANLI oturum kimligi -- saklanan kimlik DEGIL. Ikisi ayri ad uzayi:
      // saklanan kimlik diske yazilan kayit, canli kimlik ag gecidinin
      // bellekteki oturumu. Saklanani gondermek ag gecidinde hicbir seye
      // denk gelmiyor ve mesaj sessizce kayboluyor -- ilk yazimda tam bu
      // oldu, kullanici "soyledigim seyler modele gitmiyor" dedi.
      // OTURUM COZUMLEMESI BURADAN KALKTI ve gecikmenin asil kaynagi oydu.
      //
      // Burada ``waitForVoiceSessionOrOpen()`` bekleniyordu: acik oturum yoksa
      // ana pencereden bir tane isteniyor ve 12 SANIYEYE kadar bekleniyordu --
      // konusma bittikten SONRA. Kullanicinin gordugu "transcribing biter
      // bitmez modele cevap gitmiyor, arada bir bosluk var" buydu, ve o boslukta
      // yeni bir sohbet acildigi icin baska bir oturumun mesaji bir an gorunup
      // kayboluyordu.
      //
      // Artik gerek yok: gonderimi ana pencere yapiyor ve o, oturumu zaten
      // kendi acan taraf (``createBackendSessionForSend`` gonderim yolunun
      // icinde). Centik yalnizca metni yaziyor.

      // Sozunu KESTIYSE model bunu ogrenmeli.
      //
      // Mandal araya girme yollarinda kuruluyor ve besteci gonderimi onu
      // zaten tuketiyor (``use-prompt-actions/submit.ts``). Notch ag gecidine
      // DOGRUDAN gidiyor, yani o yoldan gecmiyor: tuketilmezse bayrak orada
      // asili kalir ve KULLANICININ YAZDIGI bir sonraki mesaj, hicbir seyin
      // kesilmedigi bir anda "sozunu kestim" diye isaretlenirdi.
      const interrupted = takeVoicePlaybackInterrupted()

      // ANA PENCERE gonderiyor, centik degil.
      //
      // Burada ``prompt.submit`` vardi ve composer'in gonderim boru hattini
      // atliyordu: o boru hatti gonderir gondermez ekrana IYIMSER bir kullanici
      // balonu koyuyor, centikten konusunca o balon hic cizilmiyordu. Mesaj
      // gercekten gidiyordu (gunlukte ``tui prompt accepted``) ama ekranda
      // hicbir sey olmuyor ve model dusunurken (olculdu: 172,9 sn) uygulama
      // olu gorunuyordu.
      //
      // Istenen: "centik ayni akisin birebir aynisi, sadece atanan tus ile
      // bas-konus hali olmali." Artik centik metni YAZIYOR, gonderimi ana
      // pencere yapiyor (``use-voice-submit-requests``).
      requestVoiceSubmit(text, interrupted)
    },
    [haltTurn]
  )

  const commit = useCallback(() => {
    setStatus('transcribing')

    void (async () => {
      try {
        const recording = await mic.stop()

        if (!recording || discardRef.current) {
          setStatus('idle')
          releaseBarge(bargeRef.current)

          return
        }

        await submitAudio(recording.audio)
      } catch (cause) {
        setStatus('idle')
        releaseBarge(bargeRef.current)
        setError(cause instanceof Error ? cause.message : String(cause))
      }
    })()
  }, [mic, submitAudio])

  // Cevabı AKARKEN seslendir.
  //
  // Neden akış: baloncuğun bitmesini beklemek, uzun bir cevapta kullanıcıyı
  // sessizce bekletiyordu — model 20 saniye yazıyor, ses ancak sonunda
  // başlıyor. ``startSpeechStream`` metni parça parça alıp konuşmayı hemen
  // başlatıyor, yani bekleme süresi ortadan kalkıyor.
  //
  // SESLENDİRME ARTIK BURADA DEĞİL.
  //
  // Çentik hem konuşuyor hem gösteriyordu ve ikisini de KENDİ ``$messages``
  // listesinden karar vererek yapıyordu. ``$messages`` düz bir ``atom``, yani
  // PENCERE BAŞINA: çentik ayrı bir ``BrowserWindow`` ve listesi ana
  // pencerenin bir tur gerisinde kalıyor.
  //
  // Ölçüldü: kullanıcının ekranında şeritte BİR ÖNCEKİ cevap yazıyordu ve son
  // cevap hiç seslendirilmemişti; günlükte bütün oturumda tek bir sentez
  // vardı, o da uyandırma onayı.
  //
  // Karar ``active-session.ts``de yazılı olanın aynısı: çentik bir GİRDİ
  // AYGITI. Gönderimi ana pencere yapıyordu, artık seslendirmeyi de o yapıyor
  // ve konuşulan alt yazıyı ``$spokenSubtitle`` ile buraya veriyor. Böylece
  // "kim konuşacak" sorusu tamamen ortadan kalkıyor -- tek konuşan var.

  // Metin bitti, ses sürüyor: turu SESİN sonunda bitir.
  //
  // Bu bekleyiş olmadan çentik model konuşurken kapanıyor, araya girme
  // izleyicisi sökülüyor ve ne sesle ne tuşla araya girilebiliyordu --
  // gerekçenin tamamı ``./turn-end.ts``de.
  //
  // ``awaitingPlaybackRef`` reaktif bir değerin AYNASI değil: "bu tur sesi
  // bekliyor" diyen imperatif bir bayrak, ve tek yazarı bir üstteki efekt.
  // Reaktif olan değer (``$voicePlayback``) geri çağrının içinde DOĞRUDAN
  // okunuyor, ki kuralın koruduğu şey de bu.
  // eslint-disable-next-line no-restricted-syntax -- yukarıdaki gerekçe
  useEffect(() => {
    if (!awaitingPlaybackRef.current) {
      return undefined
    }

    const finish = () => {
      if (!awaitingPlaybackRef.current) {
        return
      }

      awaitingPlaybackRef.current = false

      if (statusRef.current === 'speaking') {
        setStatus('idle')
      }
    }

    // Oynatma zaten boşsa (ses bu arada bitti) hemen kapat.
    if ($voicePlayback.get().status === 'idle') {
      finish()

      return undefined
    }

    const stop = $voicePlayback.listen(state => {
      if (state.status === 'idle') {
        finish()
      }
    })

    // Emniyet kemeri: oynatma katmanının kendi bekçileri var ama takılı bir
    // oynatma çentiği sonsuza kadar açık bırakmasın.
    const cap = setTimeout(finish, TURN_AUDIO_CAP_MS)

    return () => {
      stop()
      clearTimeout(cap)
    }
  }, [status])

  // Araya girme: kullanıcı TUŞA BASMADAN konuşmaya başlayınca da sus.
  //
  // ``lib/voice-barge-in.ts`` bu işi zaten yapabiliyordu ama notch onu hiç
  // çağırmıyordu; araya girmenin tek yolu sağ Ctrl'ye basmaktı. İnsanla
  // konuşurken kimse araya girmek için düğmeye basmaz.
  //
  // İzleyici ``thinking`` evresinde DE açık: model cevabı üretirken 1-3
  // saniye tam sessizlik oluyor ve kullanıcı çoğu zaman tam o boşlukta
  // fikrini değiştirip konuşuyor. Yalnızca oynatma sırasında izlemek o araya
  // girmeyi tamamen kaçırıyordu.
  //
  // İzleyici ÖN KAYIT tutuyor: tetiklendiği anda yeni bir kaydedici açmak
  // "dur, aslında—" cümlesinin ilk hecelerini yer. Bu yüzden yakalanan ses
  // doğrudan gönderim yoluna veriliyor, kullanıcıdan tekrar istenmiyor.
  // BAS-KONUS kipinde SES ile araya girme YOK.
  //
  // Olculen kiriklik: izleyici dinleme kipine BAKMADAN calisiyordu -- model
  // dusunurken ya da konusurken mikrofonu dinliyor ve ses algilayinca tusa
  // basilmadan yakalayip gonderiyordu. Kullanicinin bildirdigi: "notch acikken
  // basmadan konusursak bile algiliyor."
  //
  // Kural onun koydugu ve dogrusu da bu: "notch direkt olarak conversation
  // modu olmamali, conversation modunun bas-konus hali olmali." Bas-konusta
  // TEK giris tustur; kesmek de tusla olur.
  //
  // ``capturing`` KALIYOR: eller serbest kipte baslamis bir yakalama surerken
  // izleyici kapanirsa cumlenin gerisi kaybolur.
  const handsFree = listenMode === 'hands-free'
  const monitorActive = (handsFree && shouldMonitorBargeIn(status)) || capturing

  // Buradaki ref'ler reaktif bir degerin AYNASI degil: ``statusRef`` render
  // sirasinda yaziliyor (efekt icinde degil) ve ``bargeRef`` imperatif bir
  // tutamac -- araya girme kapisinin durumu.
  // State'e tasimak izleyiciyi her durum degisiminde sokup atardi; o da her
  // seferinde yeni bir ``getUserMedia`` akisi ve sifirlanan gurultu tabani
  // demek.
   
  useEffect(() => {
    if (!monitorActive) {
      return
    }

    // Durum ``thinking`` <-> ``speaking`` arasında gidip gelirken izleyici
    // YENİDEN kurulmamalı: her kurulum yeni bir ``getUserMedia`` akışı açar
    // ve gürültü tabanı kalibrasyonunu sıfırlar. Bu yüzden efekt tek bir
    // boolean'a bağlı ve güncel durum ``statusRef`` üzerinden okunuyor.
    const stop = monitorSpeechDuringPlayback({
      isPlaying: () => isPlayingPhase(statusRef.current),
      onSpeech: () => {
        if (!claimBarge(bargeRef.current, 'voice')) {
          // Kullanıcı aynı anda tuşa da bastı; o yol kaydı zaten yönetiyor.
          return
        }

        // Akış oturumu da kapatılmalı, yoksa gelen metin arkada
        // seslendirilmeye devam eder.
        interruptVoicePlayback()
        // Durdurma HEMEN gidiyor, yakalamanın bitmesi beklenmiyor: kullanıcı
        // konuşurken model saniyelerce üretmeye devam ederdi ve o metin
        // bağlama girerdi.
        void haltTurn().catch(() => undefined)
        setCapturing(true)
        setStatus('listening')
      },
      onUtterance: audio => {
        if (bargeRef.current.claimedBy !== 'voice') {
          // Tuş devraldı — yakalanan sesi göndermek çift gönderim olurdu.
          setCapturing(false)

          return
        }

        setCapturing(false)

        if (!audio) {
          // Yakalama yoksa kullanıcıyı sessizliğe düşürme: başa dön.
          releaseBarge(bargeRef.current)
          setStatus('idle')

          return
        }

        setStatus('transcribing')
        // Sıra garanti: gönderim, durdurma çözülmeden başlamıyor. Ters
        // sırada çalıştırmak yeni istemi MEŞGUL bir oturuma yollamaktı.
        // Durdurma düşerse cümle YİNE gönderiliyor -- ağ hatasını yutup
        // kullanıcının konuşmasını çöpe atmak daha kötü bir sonuç.
        void interruptThenSubmit({
          interrupt: haltTurn,
          onInterruptError: () => undefined,
          // Turun YATISMASINI bekle. Sohbet kipi bunu baslangictan beri
          // yapiyordu, centik yapmiyordu: uretim ortasinda araya girince yeni
          // cumle hala mesgul bir oturuma gidiyordu. Kural artik ortak
          // (``./interrupt.ts``), yani ikisi ayrisamiyor.
          //
          // ``$busy`` centik penceresinde hic dolmuyorsa bekleme ANINDA
          // donuyor -- yani en kotu hal bugunku davranis.
          settle: { busy: () => $busy.get() },
          submit: () => submitAudio(audio)
        }).catch((cause: unknown) => {
          setStatus('idle')
          releaseBarge(bargeRef.current)
          setError(cause instanceof Error ? cause.message : String(cause))
        })
      }
    })

    return stop
  }, [haltTurn, monitorActive, submitAudio])

  // Dusunme sessizligini doldur.
  //
  // Kullanici konusmayi bitiriyor, model cevabi uretmeye basliyor ve arada
  // 1-3 saniye TAM sessizlik oluyor. Ekranda "Thinking..." yaziyor ama
  // kullanici cogu zaman ekrana bakmiyor -- notch'un butun amaci bu. Kulakta
  // hicbir sey yok ve konusma olmus gibi duyuluyor: kullanici ya tekrar
  // konusuyor (araya girme sayiliyor) ya da bekleyip bekleyemeyecegini
  // bilemiyor.
  //
  // Her bosluk DOLDURULMUYOR: kisa bir duraklama insan konusmasinda zaten
  // var ve her turda "hmm" demek bir sure sonra bir tik gibi duyuluyor.
  // Kural dar -- yalnizca esigi gecen bosluk, tur basina bir kez, arka
  // arkaya ayni sozcuk olmadan (bkz. thinking-filler.ts).
  //
   
  // tutamac (doldurma durumu, akis oturumu), reaktif deger aynasi degil
  useEffect(() => {
    if (status !== 'thinking') {
      return
    }

    const timer = setTimeout(() => {
      const allowed = shouldFill(fillerRef.current, {
        elapsedMs: FILL_AFTER_MS,
        enabled: true,
        hasSpeechStarted: speechStartedRef.current,
        // Araya girme surerken doldurmak, kullanicinin ustune konusmak olur.
        interrupted: bargeRef.current.claimedBy === 'voice'
      })

      if (!allowed) {
        return
      }

      // Tek seferlik oynatma kullaniliyor, akis oturumu DEGIL: akis oturumu
      // turun cevabina ait ve doldurma sozcugunu oraya yazmak onu cevabin
      // basina yapistirirdi.
      void playSpeechText(takeFiller(fillerRef.current), {
        source: 'voice-conversation'
      }).catch(() => undefined)
    }, FILL_AFTER_MS)

    return () => clearTimeout(timer)
  }, [status])

  commitRef.current = commit

  /**
   * UYANDIRMA turu — wake word duyuldu.
   *
   * İstenen sıra birebir: "wake word notchu aktifleştirir, TTS 'I'm listening'
   * diye ses üretir ve bu ses biter bitmez dinlemeye başlar, kullanıcı
   * söyleyeceklerini bitirdiğinde oluşan o 1 saniyelik sessizliği algıladığında
   * mesajı gönderir."
   *
   * Neden ``begin('auto')``
   * -----------------------
   * ``'auto'`` mikrofonu ELLER SERBEST ayarlarıyla açıyor
   * (``listenOptionsFor`` -> ``HANDS_FREE_VAD``): 1,25 sn sessizlik kaydı
   * kapatıp turu gönderiyor. "Kullanıcı susana kadar basılı tutulmuş bas-konuş"
   * tam olarak bu -- yeni bir yakalama yolu yazmaya gerek yok.
   *
   * Neden ``$listenMode`` DEĞİŞMİYOR
   * --------------------------------
   * Kip ``push-to-talk`` kalıyor ve bu bilinçli. ``shouldRearmListening``
   * yalnızca kip eller serbestken mikrofonu yeniden açıyor; uyandırma turu ise
   * TEK SEFERLİK olmalı -- kullanıcının kararı: "sonrasında ya tekrar wake
   * word ya sağ Ctrl." Kipi çevirseydik tur biter bitmez mikrofon kendiliğinden
   * açılır ve oda sessiz değilse yanlış tur başlardı.
   *
   * Onay sesi BİTMEDEN dinleme başlamıyor: hoparlörden çıkan "I'm listening"
   * açık bir mikrofona kullanıcı konuşması gibi düşer ve ajan kendi onayına
   * cevap verirdi. Windows'ta yankı bastırma aynı uygulamanın kendi oynatmasını
   * güvenilir biçimde kesmiyor (bkz. ``hands-free.ts``).
   */
  /**
   * ``thinking``den ÇIKIŞ -- artık ana pencereden geliyor.
   *
   * Ölçülen hata: seslendirme çentikten alınınca ``speaking`` geçişi de onunla
   * gitti, ama ``idle``a dönüş hâlâ onu bekliyordu. Çentik ``thinking``de
   * sonsuza kadar takılı kalıyordu -- kullanıcının bildirdiği "notch takılı
   * kaldı cevap gelmesine rağmen".
   *
   * İki sinyal birden gerekiyor ve ikisi de ana pencereden:
   *
   *   * ŞERİT doluyorsa model konuşuyor -> ``speaking``.
   *   * Tur bitti (``$mainTurnBusy`` düştü) ve şerit boş -> ``idle``.
   *
   * Otomatik okuma KAPALIYKEN şerit hiç dolmuyor; o durumda turun bitmesi tek
   * başına çıkış için yeterli, yoksa ses kapalı olan kullanıcıda çentik
   * kalıcı olarak takılırdı.
   */
  useEffect(() => {
    if (status !== 'thinking' && status !== 'speaking') {
      return
    }

    if (reply) {
      if (status !== 'speaking') {
        setStatus('speaking')
      }

      return
    }

    if (!mainBusy) {
      setStatus('idle')
    }
  }, [mainBusy, reply, status])

  const beginWakeTurn = useCallback(async () => {
    setError(null)
    setStatus('speaking')

    // Onay METNİ seçili TTS motorundan geçiyor: kullanıcı hangi sesi seçtiyse
    // uyandırma da onunla konuşuyor. Sabit bir ses dosyası, seçilen sesle
    // alakasız bir "bip" olurdu.
    try {
      await playSpeechText(WAKE_ACK_TEXT, { messageId: null, source: 'voice-conversation' })
    } catch {
      // Onay DUYULMASA da dinleme başlamalı: kullanıcı wake word'ü söyledi ve
      // konuşmayı bekliyor. Sesin gelmemesi turu düşürmemeli.
    }

    begin('auto')
  }, [begin])

  return {
    begin,
    beginWakeTurn,
    cancel,
    capturing,
    commit,
    endSession,
    error,
    heardSpeech,
    level,
    reply,
    status,
    transcript
  }
}
