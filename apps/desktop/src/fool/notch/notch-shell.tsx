/**
 * macOS tarzı ses notch'u.
 *
 * Biçim
 * -----
 * Ekranın üst kenarına YAPIŞIK, yatayda ortalı, yalnızca ALT köşeleri yuvarlak
 * bir kabuk — ekrana oyulmuş bir çentik gibi. Üst köşeler bilerek düz: yuvarlak
 * olsalardı çentik değil, havada duran bir hap gibi görünürdü.
 *
 * Pencere HİÇ yeniden boyutlanmıyor
 * ---------------------------------
 * Açılıp kapanırken OS penceresini büyütmek Windows'ta kare atlatıyor ve saydam
 * çerçevesiz pencerede kenarlar titriyor. Pencere her zaman en büyük ölçüde
 * duruyor (bkz. ``electron/fool-notch.ts``); animasyon tamamen burada, yay
 * fiziğiyle oluyor. Pencerenin geri kalanı saydam ve fareyi geçiriyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { useStore } from '@nanostores/react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'

import { onGatewayEvent } from '@/contrib/events'
import { Mic } from '@/lib/icons'

import { voiceApi } from '../voice-api'

import { useNotchClickThrough } from './click-through'
import { MAX_IDLE_ROUNDS, nextIdleRounds, shouldRearmListening } from './hands-free'
import { $listenMode } from './listen-mode'
import { liquidPourStyle, NotchEdgeWaves, NotchLiquidStyles, useLiquidPhase } from './notch-liquid'
import { formatPttBindingLabel, parsePttBinding } from './ptt-binding'
import { $pttCode } from './ptt-store'
import {
  createPushToTalkState,
  onBlur as ptOnBlur,
  onKeyDown as ptOnKeyDown,
  onKeyUp as ptOnKeyUp
} from './push-to-talk'
import { type NotchStatus, useNotchVoice } from './use-notch-voice'
import { useWakeTurnFlag } from './use-wake-turn-flag'

const COLLAPSED_WIDTH = 104
const COLLAPSED_HEIGHT = 22
const EXPANDED_WIDTH = 300
const EXPANDED_HEIGHT = 92

/**
 * ALT YAZI kipi: çentik yatay olarak uzuyor.
 *
 * Kullanıcının kararı: "modelin cevabı için notch büyük şekilde açılmak
 * yerine mikrofon simgesi kaybolsun ve notch yatay olarak genişlesin, alt yazı
 * monitörün en üst kenarının tamamına kadar genişleyebilsin -- böylece modelin
 * cevabı tamamen sığar çoğu zaman."
 *
 * Yükseklik BÜYÜMÜYOR, tam tersine kısalıyor: dikey büyüme ekranın tepesinden
 * aşağı sarkan bir kutu demekti; istenen ince ve uzun bir şerit.
 */
const SUBTITLE_HEIGHT = 46

/** Kenarlarda bırakılan pay -- şerit ekranın köşelerine yapışmasın. */
const SUBTITLE_MARGIN = 24

/**
 * Bir karakterin kabaca kapladığı genişlik (0,82rem gövde yazısı).
 *
 * Şerit CÜMLE KADAR geniş oluyor: kullanıcının kararı "alt yazı cümle kadar
 * genişlemeli, eğer cümle uzunsa geniş kısaysa ona göre uzunlukta olmalı ki
 * her seferinde çok yer işgal etmesin."
 *
 * ÖLÇÜM DEĞİL TAHMİN, bilinçli: alt yazı ses saatiyle birlikte kare başına
 * güncelleniyor ve her karede ``scrollWidth`` okumak yerleşimi yeniden
 * hesaplatırdı. Tahmin CÖMERT (gerçek ortalamanın biraz üstünde): fazla
 * genişlik yalnızca birkaç piksel boşluk demek, dar kalmak ise metnin
 * kırpılması.
 */
const SUBTITLE_CHAR_PX = 7.2

/** Şeridin inebileceği en dar hâl -- tek kelimelik bir cevapta bile okunur. */
const SUBTITLE_MIN_WIDTH = 180

/** Tur bittikten sonra yazının ekranda kalma süresi. */
const LINGER_MS = 6000

/** Yay: hafif taşan ama salınmayan bir açılış. macOS'un çentik hissi bu. */
const SPRING = { damping: 26, mass: 0.9, stiffness: 380, type: 'spring' } as const

// Kullaniciya gorunen metinler Ingilizce -- uygulamanin varsayilan dili.
// (Yorumlar Turkce; bu ayrim depo kurali.)
const LABEL: Record<NotchStatus, string> = {
  idle: 'Listening — just talk',
  listening: 'Listening…',
  speaking: 'Replying',
  thinking: 'Thinking…',
  transcribing: 'Transcribing…'
}

/** Eller serbest kip kendini susturdugunda gosterilen satir. */
const pausedLabel = (key: string) => `Paused — press ${key} or say the wake word`

export function NotchShell() {
  // Uygulamanin global govde arkaplani bu pencerede de boyaniyor: notch'un
  // kendisi solsa bile arkasinda 460x220'lik opak bir dikdortgen kaliyordu
  // ("kocaman siyah kisim"). Pencere zaten saydam; govdeyi de saydam yapmak
  // gerekiyor ve bu YALNIZCA notch penceresinde olmali, o yuzden global
  // stylesheet yerine burada.
  useEffect(() => {
    const root = document.documentElement
    const { body } = document
    const previous = [root.style.background, body.style.background] as const

    root.style.background = 'transparent'
    body.style.background = 'transparent'

    return () => {
      root.style.background = previous[0]
      body.style.background = previous[1]
    }
  }, [])

  const [hovered, setHovered] = useState(false)
  // Oturum acik mi? Sag Ctrl yalnizca acikken dinliyor.
  const [sessionActive, setSessionActive] = useState(false)

  // Kullanici "dur" dedi.
  //
  // Sohbet kipiyle AYNI kanca secenegi ve ayni anlam: sozcuk bir tur olarak
  // gonderilmiyor, konusma bitiyor. Burada oturumu kapatmak sart -- eller
  // serbest kipte oturum acik kaldigi surece mikrofon her turdan sonra
  // kendini yeniden aciyor, yani "dur" demek hicbir seyi durdurmazdi.
  const voice = useNotchVoice({
    onStopWord: () => {
      setSessionActive(false)
      window.foolDesktop?.notch?.close?.()
    }
  })

  // Uyandirma turunun BITTIGINI ana pencereye bildiriyor; geri acmayi orasi
  // yapiyor (gerekce ``use-wake-turn-resume.ts``).
  const startWakeTurn = useWakeTurnFlag(voice.status)

  // Hangi kisayolun kayitli oldugu makineye gore degisiyor (aday
  // merdiveni), o yuzden SABIT yazmak yerine ana surece soruluyor.
  const [shortcut, setShortcut] = useState<null | string>(null)

  useEffect(() => {
    void window.foolDesktop?.notch?.shortcut?.().then(r => setShortcut(r?.shortcut ?? null))
  }, [])
  const shellRef = useRef<HTMLDivElement | null>(null)

  // Fare uzerine gelince centik TAMAMEN kayboluyor ve masaustunu birakiyor.
  //
  // Neden `pointerenter` degil de pencere duzeyinde konum: notch penceresi
  // `setIgnoreMouseEvents(true, { forward: true })` ile calisiyor -- tiklamalar
  // altta kalana gidiyor, renderer yalnizca ILETILEN hareket olaylarini
  // goruyor. O kipte enter/leave guvenilir atesle(n)miyor; konumu olcmek
  // ise her zaman dogru.
  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      const box = shellRef.current?.getBoundingClientRect()

      if (!box) {
        return
      }

      // Kucuk bir pay: centigin hemen kenarinda titremesin.
      const pad = 8

      const inside =
        event.clientX >= box.left - pad && event.clientX <= box.right + pad && event.clientY <= box.bottom + pad

      setHovered(inside)
    }

    window.addEventListener('mousemove', onMove)

    return () => window.removeEventListener('mousemove', onMove)
  }, [])

  // Wake word de kisayolla AYNI seyi yapiyor: oturumu acar.
  //
  // Kullanicinin istedigi buydu ve mantikli: "hey fool" demek ile Ctrl+Alt+V
  // basmak ayni niyet -- konusmaya baslamak. Ikisini farkli davranislara
  // baglamak, hangisini kullandigina gore farkli bir uygulama demek olurdu.
  useEffect(
    () =>
      onGatewayEvent('wake.detected', () => {
        setSessionActive(true)
        void window.foolDesktop?.notch?.open?.()
      }),
    []
  )

  // Oturum acikken centik ODAGI KORUMALI.
  //
  // Bildirilen kiriklik tam buydu: ilk istem gonderildikten sonra sag Ctrl
  // artik algilanmiyordu. Sebebi centigin odagi kaybetmesi -- odaklanmamis
  // bir pencere hicbir tus olayi almaz, yani bas-konus sessizce oluyordu.
  //
  // Tur bittiginde (durum 'idle'e dondugunde) odak geri aliniyor. Suren bir
  // tur sirasinda dokunulmuyor: kullanici o esnada baska bir uygulamada
  // calisiyor olabilir ve odagi calmak sinir bozucu olurdu.
  useEffect(() => {
    if (!sessionActive || voice.status !== 'idle') {
      return
    }

    const timer = setTimeout(() => {
      void window.foolDesktop?.notch?.open?.()
    }, 150)

    return () => clearTimeout(timer)
  }, [sessionActive, voice.status])

  // Tur bittikten SONRA da bir süre açık kal.
  //
  // Neden: durum `idle`'a döndüğü anda daraltmak, kullanıcının az önce ne
  // söylediğini ekrandan siliyordu — yanlış anlaşılmayı fark etme şansı
  // kalmıyordu. Konuşma bitti diye kanıtı da kaldırmak yanlış.
  const [lingering, setLingering] = useState(false)

  useEffect(() => {
    if (voice.status !== 'idle') {
      setLingering(true)

      return
    }

    if (!voice.transcript) {
      setLingering(false)

      return
    }

    const timer = setTimeout(() => setLingering(false), LINGER_MS)

    return () => clearTimeout(timer)
  }, [voice.status, voice.transcript])

  const expanded = voice.status !== 'idle' || lingering

  /**
   * ALT YAZI kipi: model konuşuyor ve söylediği ekranda akıyor.
   *
   * Mikrofon simgesi bu kipte GİZLENİYOR (kullanıcının kararı): konuşan model,
   * dinleyen kullanıcı değil -- ve şeritte her piksel metne gidiyor.
   */
  const subtitleMode = Boolean(voice.reply)

  // Acilis/kapanis GECISI -- kendiliginden sonuyor.
  const liquidPhase = useLiquidPhase(sessionActive)

  // Şerit pencerenin enine yayılıyor. Pencere ekran genişliğinde açılıyor
  // (``electron/fool-notch.ts``), ama BURADA ölçülüyor: kullanıcının
  // yakınlaştırma ayarı yüzünden CSS pikseli fiziksel pikselden farklı ve
  // pencere ölçüsünü sabit yazmak çentiği kenardan kesiyordu.
  const [subtitleWidth, setSubtitleWidth] = useState(EXPANDED_WIDTH)

  useEffect(() => {
    const measure = () => setSubtitleWidth(Math.max(EXPANDED_WIDTH, window.innerWidth - SUBTITLE_MARGIN))

    measure()
    window.addEventListener('resize', measure)

    return () => window.removeEventListener('resize', measure)
  }, [])

  // Oturum açılınca konuşma tanımayı ISIT.
  //
  // Ölçüldü (12,18 sn gerçek konuşma, Whisper large-v3-turbo float16):
  // ısıtmasız ilk transkripsiyon 6,94 sn, ısıtılmış 0,66 sn. O altı saniye
  // modelin VRAM'e yüklenmesi ve kullanıcı ilk cümlesini söylerken arka
  // planda ödenebiliyor.
  //
  // Boşta-boşaltma paylaşılan kartta 300 sn olduğu için (fool/gpu_budget.py)
  // maliyet her uzun aradan sonra geri geliyordu; oturumu her açışta ısıtmak
  // tam o durumu kapsıyor.
  //
  // Hata YUTULUYOR: ısıtma bir iyileştirme, bir gereklilik değil. Ağ geçidi
  // henüz ayakta değilse oturum yine açılmalı.
  useEffect(() => {
    if (!sessionActive) {
      return
    }

    void voiceApi.warmVoice().catch(() => undefined)
  }, [sessionActive])

  // Eller serbest tur alma: oturum açıkken tur biter bitmez mikrofon
  // kendiliğinden açılıyor. Kullanıcı hiçbir şeye dokunmadan cevap veriyor —
  // bas-konuş telsiz gibiydi, bu konuşma gibi.
  //
  // Sağ Ctrl yine çalışıyor ve o kayıt BAS-KONUŞ kuralıyla işliyor: gürültülü
  // ortamda kullanıcı kaydın sınırını kendi çizmek isteyebilir.
  const [idleRounds, setIdleRounds] = useState(0)

  // Dinleme kipi Friend penceresiyle ORTAK depo (bkz. ``listen-mode.ts``):
  // iki yuzey ayni mikrofonu kullaniyor ve ayri tutmak kullaniciya iki ayri
  // hakikat sunardi.
  const rearmListenMode = useStore($listenMode)

  // Kullanıcı konuştuysa sayaç sıfırlanır; birikmiş sayaç onu bir sonraki
  // sessizlikte erken susturmamalı.
  useEffect(() => {
    if (voice.heardSpeech) {
      setIdleRounds(0)
    }
  }, [voice.heardSpeech])

  // Oturum her açıldığında sayaç sıfırdan başlıyor: kullanıcı az önce
  // kısayola bastı, orada olduğu kesin.
  useEffect(() => {
    if (sessionActive) {
      setIdleRounds(0)
    }
  }, [sessionActive])

  // Kullanicinin SECTIGI kip.
  //
  // Burada ``'hands-free'`` SABIT yaziliydi, yani ``$listenMode`` hic
  // okunmuyordu: bas-konus secili olsa bile notch her turdan sonra mikrofonu
  // kendiliginden aciyordu. Kullanicinin "ctrl alt v modu sadece push to
  // talkta calissin" demesinin sebebi buydu -- secim vardi ama hicbir sey
  // yapmiyordu.
  //
  // Bas-konusta ``shouldRearmListening`` ``false`` donuyor ve mikrofonu
  // yalnizca TUS aciyor.
  const rearm = shouldRearmListening({
    capturing: voice.capturing,
    idleRounds,
    mode: rearmListenMode,
    sessionActive,
    status: voice.status
  })

  useEffect(() => {
    if (!rearm) {
      return
    }

    // Kısa bir gecikme: oynatma kuyruğunun gerçekten boşalması için. Aynı
    // karede açmak hoparlörün son hecesini mikrofona yakalatıyordu.
    const timer = setTimeout(() => {
      voice.begin('auto')
      // Bu turda konuşma duyulmazsa kayıt boşta zaman aşımıyla kapanacak;
      // sayaç şimdiden artıyor ve ``heardSpeech`` gelirse sıfırlanıyor.
      setIdleRounds(previous => nextIdleRounds(previous, false))
    }, 250)

    return () => clearTimeout(timer)
    // ``voice`` her render'da yeni bir nesne; bağımlılığa almak efekti her
    // render'da yeniden kurar ve mikrofonu açıp kapatıp durur.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rearm])

  // Kip kendini susturduysa kullanıcıya SÖYLE. Sessizce durmak, notch açık
  // dururken hiçbir şeyin çalışmadığı izlenimi veriyordu.
  const paused = sessionActive && voice.status === 'idle' && idleRounds >= MAX_IDLE_ROUNDS

  // Ses tutamağı bir REF'te.
  //
  // Ölçülen hata: aşağıdaki tuş etkisi ``voice``a bağımlıydı ve ``voice`` her
  // render'da YENİ bir nesne (``useNotchVoice`` düz bir nesne döndürüyor).
  // Yani etki her render'da sökülüp yeniden kuruluyordu -- ve cevap akarken
  // ``setReply`` her token'da render tetikliyor, saniyede onlarca kez.
  //
  // Sökülen yalnızca yerel dinleyiciler değil: ``onPushToTalk`` da iptal edilip
  // yeniden abone oluyor. O boşluğa denk gelen bir tuş olayı KAYBOLUYOR --
  // yani sağ Ctrl ile araya girmenin en çok gerektiği anda, model konuşurken,
  // en kırılgan olduğu an.
  //
  // Ref render sırasında yazılıyor: geri çağrılar her zaman güncel tutamağı
  // görüyor ama etkinin kimliği sabit kalıyor.
  const voiceRef = useRef(voice)

  voiceRef.current = voice

  // Bas-konuş durumu bir ref'te: klavye olayları render döngüsünün dışında
  // geliyor ve state kullanmak her tuş olayında bir render daha demek olurdu.
  const ptt = useRef(createPushToTalkState())
  // Sag Ctrl her makinede yok: bazi dizustulerde fiziksel olarak bulunmuyor,
  // bazi kullanicilar onu IME degistirmeye baglamis. O makinelerde bas-konus
  // hic calismiyordu ve sebebi gorunmuyordu.
  const pttCode = useStore($pttCode)
  // Etiket AYRISTIRILARAK uretiliyor: ``pttCode`` artik ``Shift+ControlRight``
  // gibi bir kombo dizesi olabiliyor ve ham hali arayuz metni degil --
  // kullaniciya hangi tuslara basacagini soylemiyor.
  const pttLabel = formatPttBindingLabel(parsePttBinding(pttCode))

  // Tikla-gecir kapisi. Centik VARSAYILAN olarak gecirgen -- ekranin en ust
  // kenarinda duruyor ve oradaki sekmeleri, menuyu, pencere dugmelerini
  // yutmamali. Yalnizca imlec isaretli bir parcanin uzerindeyken katilasiyor.
  useNotchClickThrough()
  // Dinleme kipi Friend penceresiyle ORTAK: iki yuzey ayni mikrofonu
  // kullaniyor ve kipi ayri tutmak kullaniciya iki ayri hakikat sunardi.
  const listenMode = useStore($listenMode)

  useEffect(() => {
    const onDown = (event: KeyboardEvent) => {
      const action = ptOnKeyDown(ptt.current, event, Date.now(), pttCode)

      if (action?.type === 'start') {
        if (!sessionActive) {
          setSessionActive(true)
        }

        // Tuşun varsayılan davranışını yutuyoruz ki basılı tutuş başka bir
        // kısayolu tetiklemesin.
        event.preventDefault()
        voiceRef.current.begin()
      }
    }

    const onUp = (event: KeyboardEvent) => {
      const action = ptOnKeyUp(ptt.current, event, Date.now(), pttCode)

      if (action?.type === 'commit') {
        voiceRef.current.commit()
      } else if (action?.type === 'cancel') {
        voiceRef.current.cancel()
      }
    }

    // Odak kaybı bırakma sayılıyor: tuş hâlâ basılı olsa bile ``keyup`` artık
    // bize gelmeyecek, o olay odağı alan uygulamaya gider. Basılı saymaya devam
    // etmek mikrofonu sonsuza kadar açık bırakırdı.
    //
    // OTURUMU kapatmiyor: kullanici centige degil, calistigi uygulamaya
    // bakiyor olabilir. Oturum yalnizca kisayolla kapanir.
    const onWindowBlur = () => {
      if (ptOnBlur(ptt.current)) {
        voiceRef.current.cancel()
      }
    }

    // Global kisayol (notch ODAKTA DEGILKEN): tek dokunus dinlemeyi acar,
    // ikinci dokunus gonderir. Basili tutus burada kullanilamaz -- Electron'un
    // globalShortcut'i tus birakmayi bildirmiyor.
    // Ctrl+Alt+V bir OTURUM aciyor/kapatiyor -- tek seferlik dinleme degil.
    //
    // Onceki davranis su kirikligi uretiyordu: kisayol bir kez dinlemeyi
    // aciyor, ilk istem gonderildikten sonra centik odagi kaybediyor ve sag
    // Ctrl artik ALGILANMIYOR (odaklanmamis bir pencere tus olayi almaz).
    // Kullanici centigi acik gorup konusmaya calisiyor, hicbir sey olmuyor.
    //
    // Dogru model: kisayol oturumu ACAR, oturum boyunca sag Ctrl calisir,
    // ayni kisayol oturumu KAPATIR.
    const handleListenRequest = (request?: null | { mode?: string }) => {
      // Kisayol yalnizca centigi acmiyor, ARKADAS turunu de basliyor.
      // Kip oturum ACILIRKEN yaziliyor: arac kumesi ajan kurulurken donuyor,
      // Kisayol SALT BAS-KONUS aciyor.
      //
      // Kullanicinin istegi birebir: "ctrl alt v sadece notchu aktif etsin
      // ve aktif olduktan sonra sadece sag ctrlye basili tutarken sesimizi
      // algilasin." Eller serbest kendiliginden dinlemeye gecerdi.
      //
      // Efekt DEGIL burada: niyet geldigi anda uygulaniyor. Efekt bir render
      // geriden gelir ve o karede eller serbest mikrofonu zaten acmis olur.
      $listenMode.set('push-to-talk')

      // UYANDIRMA: centik acilir, TTS onay verir, ses biter bitmez dinlenir ve
      // kullanici susunca (1,25 sn sessizlik) mesaj gider.
      //
      // Kip yine ``push-to-talk`` kaliyor -- bilincli. ``shouldRearmListening``
      // yalnizca eller serbest kipte mikrofonu yeniden aciyor; uyandirma turu
      // TEK SEFERLIK olmali (kullanicinin karari: "sonrasinda ya tekrar wake
      // word ya sag Ctrl"). Kipi cevirseydik tur biter bitmez mikrofon
      // kendiliginden acilir ve oda sessiz degilse yanlis tur baslardi.
      if (request?.mode === 'wake') {
        setSessionActive(true)
        // Tur BASLADI. Saptama sunucuda dinleyiciyi duraklatti; bayrak inince
        // ana pencere geri aciyor. Bu olmadan uyandirma BIR KEZ calisiyordu.
        startWakeTurn()
        void voiceRef.current.beginWakeTurn()

        return
      }

      setSessionActive(previous => {
        if (previous) {
          // Kapatiliyor: suren bir kayit varsa atilir ve ARKADAS OTURUMU
          // unutulur -- bir sonraki acilis temiz bir oturum alsin.
          voiceRef.current.cancel()
          voiceRef.current.endSession()
          window.foolDesktop?.notch?.close?.()

          return false
        }

        // Oturum aciliyor: centigi one getir ve ODAGI al. Odak olmadan sag
        // Ctrl hicbir zaman ulasmaz.
        void window.foolDesktop?.notch?.open?.()

        return true
      })
    }

    const stopListenRequest = window.foolDesktop?.notch?.onListenRequest?.(handleListenRequest)

    // Montajda BEKLEYEN niyeti al.
    //
    // Yeni acilan bir pencerede ana surecin ``send``i buraya HIC ulasmiyor:
    // mesaj, renderer ``ipcRenderer.on`` cagirmadan once gidiyor ve dusuyor.
    // Kullanicinin gordugu buydu -- ilk Ctrl+Alt+V hicbir sey yapmiyor,
    // ikincisi aciyor. Ustune ac/kapa sayaci bir kayiyordu.
    void window.foolDesktop?.notch?.takeListenRequest?.().then(pending => {
      if (pending) {
        handleListenRequest(pending)
      }
    })

    // BASKA penceremizden iletilen tus. Centik odakta olmasa da bas-konus
    // calisiyor -- odaklanmamis bir pencere hicbir tus olayi almiyor ve
    // "bir kez calisip oluyor" hatasi tam olarak buydu.
    const stopForwarded = window.foolDesktop?.notch?.onPushToTalk?.(event => {
      // İletilen tuş GERÇEK bir ``KeyboardEvent`` DEĞİL: IPC'den düz bir
      // nesne olarak geliyor. ``onDown`` basılı tutuşun başka kısayolları
      // tetiklememesi için ``preventDefault()`` çağırıyor -- ve düz nesnede o
      // işlev yok.
      //
      // Ölçülen kırıklık (kullanıcının günlüğünden)::
      //
      //     [renderer console:notch] Uncaught Error:
      //     e.preventDefault is not a function
      //
      // İstisna ``preventDefault`` satırında atılıyor, yani hemen ardından
      // gelen ``voice.begin()`` HİÇ çalışmıyor: mikrofon açılmıyor ve çentik
      // ölü görünüyor. Kullanıcının bildirdiği "bir iki sağ Ctrl'den sonra
      // bir daha açılmıyor" tam olarak bu -- ilk cevap ana pencerede
      // çizilince odak oraya geçiyor ve tuş ARTIK iletilen yoldan geliyor.
      //
      // ``preventDefault`` burada no-op: iletilen olayın yutulacak bir
      // varsayılan davranışı zaten yok (bu pencere odakta değil, tuşu alan
      // pencere kendi tarafında hallediyor).
      //
      // ``code`` AYRISTIRILIYOR: ``pttCode`` artik ``Shift+ControlRight`` gibi
      // bir KOMBO dizesi olabiliyor ve onu oldugu gibi ``code`` diye vermek
      // hicbir olayla eslesmeyen bir tus uretirdi -- bas-konus odak disinda
      // sessizce olurdu. Degistiriciler GERCEK olaydan geliyor (ana surec
      // ilettiği icin), varsayimdan degil.
      const key = {
        altKey: event.altKey,
        code: parsePttBinding(pttCode).code,
        ctrlKey: event.ctrlKey,
        metaKey: event.metaKey,
        preventDefault: () => {},
        repeat: event.repeat,
        shiftKey: event.shiftKey
      } as unknown as KeyboardEvent

      if (event.type === 'down') {
        onDown(key)
      } else {
        onUp(key)
      }
    })

    window.addEventListener('keydown', onDown)
    window.addEventListener('keyup', onUp)
    window.addEventListener('blur', onWindowBlur)

    return () => {
      stopForwarded?.()
      stopListenRequest?.()
      window.removeEventListener('keydown', onDown)
      window.removeEventListener('keyup', onUp)
      window.removeEventListener('blur', onWindowBlur)
    }
    // ``pttCode`` bagimliliga giriyor: kullanici tusu yeniden bagladiginda
    // dinleyiciler ESKI koda bakmaya devam ederdi -- yani ayar kaydediliyor
    // ama hicbir sey degismiyor gibi gorunurdu.
    //
    // ``voice`` bagimlilikta DEGIL: her render'da yeni bir nesne ve etkiyi
    // surekli sokup takardi (gerekce ``voiceRef``in yaninda).
  }, [pttCode, sessionActive, startWakeTurn])

  return (
    <div className="relative flex h-screen w-screen flex-col items-center bg-transparent" data-fool-notch>
      {/* UST KENAR dalgalari -- yalnizca DINLERKEN ve konusma HENUZ
          algilanmamisken. Konusma algilaninca geri cekiliyorlar. */}
      <NotchLiquidStyles />
      <NotchEdgeWaves active={voice.status === 'listening' && !voice.heardSpeech} />
      {/* Akis SARMALAYICIDA: ``motion`` genislik/yukseklik animasyonu icin
          kendi ``transform``ini yaziyor ve CSS keyframe'i ayni ogeye koymak
          ikisini carpistiriyordu. */}
      <div style={liquidPourStyle(liquidPhase)}>
        <motion.div
          animate={{
            // TEK bir aktif geometri var ve o INCE + UZUN.
            //
            // Once iki ayri hal vardi: durum/dugme icin asagi dogru kalin bir
            // kutu, alt yazi icin ince bir serit. Kullanicinin karari: "asagiya
            // dogru kalin istemiyorum, ince ve uzun sekilde monitorun ustunde
            // olsun." Iki ayri sekil ayrica iki ayri animasyon gibi gorunuyordu.
            // GENISLEME yalnizca ALT YAZIYLA. Kullanicinin karari: "listening
            // sirasinda notch bu ufak halde kalmali, mikrofon butonu gitmeli ...
            // sadece alt yazidan alt yaziya genislemeli." Dinlerken genis serit
            // acmak ekranin tepesini bos yere kapatiyordu.
            height: subtitleMode ? SUBTITLE_HEIGHT : COLLAPSED_HEIGHT,
            // Genişlik pencereye göre KIRPILMAZ: kullanıcının yakınlaştırma
            // ayarı 110% iken pencere 460 fiziksel piksel ama yalnızca 418 CSS
            // pikseli; sabit 420 px istemek çentiği kenardan kesiyordu.
            opacity: hovered ? 0 : expanded || subtitleMode ? 1 : 0.72,
            // ALT YAZI kipinde ekranın enine yayılıyor: model konuşurken cevabın
            // tamamı tek satıra sığsın diye.
            width: subtitleMode
              ? Math.min(subtitleWidth, Math.max(SUBTITLE_MIN_WIDTH, voice.reply.length * SUBTITLE_CHAR_PX + 56))
              : COLLAPSED_WIDTH
          }}
          // Üst köşeler DÜZ, alt köşeler yuvarlak — ekrana oyulmuş çentik.
          //
          // Renkler TEMADAN geliyor, sabit siyah değil: uygulamanın vurgu rengi
          // değiştiğinde çentik de onunla değişmeli, yoksa ekranın tepesinde
          // temaya ait olmayan bir kara leke kalıyor.
          className="max-w-full overflow-hidden rounded-b-[18px] border-x border-b border-white/10 text-(--ui-text-primary) shadow-[0_8px_28px_rgba(0,0,0,0.28)] backdrop-blur-2xl backdrop-saturate-150"
          initial={false}
          // Fare üzerine gelince TAMAMEN görünmez: çentik ekranın en üstünde
          // duruyor ve oradaki sekmeleri/menüleri kapatmamalı. Görünmezken
          // fareyi de geçiriyor (pointer-events), yani altındaki şeye tıklanır.
          ref={shellRef}
          // Buzlu cam: SAF SIYAH degil. Arkaplan yariya kadar saydam ve
          // dinlerken vurgu rengiyle hafifce tonlaniyor, boylece centik
          // ekranin bir parcasi gibi duruyor -- uzerine yapistirilmis bir
          // kutu gibi degil.
          style={{
            background:
              voice.status === 'listening'
                ? 'color-mix(in srgb, var(--theme-primary) 18%, rgb(0 0 0 / 0.45))'
                : 'rgb(0 0 0 / 0.42)',
            pointerEvents: 'none'
          }}
          transition={hovered ? { duration: 0.18 } : SPRING}
        >
          <AnimatePresence initial={false} mode="wait">
            {/* ALT YAZI kipi: model konusurken serit yatay uzuyor ve icinde
              YALNIZCA metin var.

              Mikrofon, dalga formu ve kip dugmesi burada CIZILMIYOR --
              kullanicinin karari: "mikrofon simgesi kaybolsun ve notch yatay
              olarak genislesin". Ikisi de dogru: konusan model, dinleyen
              kullanici degil; ve seritte her piksel metne gidiyor. */}
            {subtitleMode ? (
              <motion.div
                animate={{ opacity: 1 }}
                className="flex h-full items-center justify-center px-6"
                exit={{ opacity: 0 }}
                initial={{ opacity: 0 }}
                key="subtitle"
                transition={{ duration: 0.12 }}
              >
                <div className="truncate text-center text-[0.82rem] leading-tight text-(--ui-text-primary)">
                  {voice.reply}
                </div>
              </motion.div>
            ) : (
              <motion.div
                animate={{ opacity: 1 }}
                className="flex h-full items-center justify-center gap-2 px-4"
                exit={{ opacity: 0 }}
                initial={{ opacity: 0 }}
                key="collapsed"
                transition={{ duration: 0.12 }}
              >
                {/* Kapali halde METIN YOK. Kisayolu surekli yazmak centigi
                  genisletiyor ve ekranin tepesinde gereksiz yer kapliyordu;
                  kullanici onu zaten bir kez ogreniyor. Kisayol yalnizca
                  uzerine gelindiginde ipucu olarak duruyor.

                  ETKINKEN MIKROFON YOK: kullanicinin karari "listening
                  sirasinda ... mikrofon butonu gitmeli". Geriye canli nokta
                  kaliyor -- seviyeye gore nefes alan tek bir isaret. */}
                {!expanded && <Mic className="size-3 text-(--theme-primary)" />}
                <span
                  className="rounded-full bg-(--theme-primary) transition-all duration-150"
                  style={{
                    height: expanded ? 5 + voice.level * 5 : 4,
                    opacity: expanded ? 0.55 + voice.level * 0.45 : 0.6,
                    width: expanded ? 5 + voice.level * 5 : 4
                  }}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </div>

      {/* Masaustundeki pet: cubuktan asagi damliyor ve orada duruyor.
          Centik penceresi 220 px, cubuk 22-92 px -- altta kalan alan saydam
          ve fare olaylarini geciriyor, yani masaustunu hic isgal etmiyor. */}
      {/* Kirmizi top KALDIRILDI. Akan sey artik centigin KENDISI -- ona
          eslik eden ayri bir nesne degil (gerekce ``notch-liquid.tsx``). */}
    </div>
  )
}
