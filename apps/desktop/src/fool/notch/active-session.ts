/**
 * Sesin gideceği oturum — PENCERELER ARASI.
 *
 * Ölçülen hata
 * ------------
 * Çentik ``$activeSessionId``i okuyordu ama o düz bir atom ve çentik AYRI bir
 * ``BrowserWindow``: kendi deposunda o değer hiç dolmuyor, ``null`` kalıyor.
 * Ses ``session_id: null`` ile gidiyor, ağ geçidi onu kendi seçtiği bir
 * oturuma düşürüyor.
 *
 * Kullanıcının gördüğü buydu: "mesajlar ilk önce bots kısmında gözüküyor
 * ancak ana sessiona hemen düşmüyor, bundan dolayı ses gecikiyor." Mesaj
 * yanlış oturuma gidiyor ve ana sohbete ancak eşitlenince düşüyor.
 *
 * Aynı tuzağa daha önce bas-konuş bağlaması ve dinleme kipi de düştü; çözüm
 * yine ``sharedAtom`` -- yazan pencerenin değerini diğeri de duyuyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { sharedAtom } from '../cross-window-atom'

/**
 * Ana pencerenin AÇIK sohbeti. ``''`` = henüz yok.
 *
 * Ana pencere yazıyor, çentik okuyor. Çentiğin kendi ``$activeSessionId``i
 * hiçbir zaman dolmuyor, o yüzden burası tek kaynak.
 */
export const $voiceSessionId = sharedAtom<string>('fool.desktop.voice.sessionId', '', {
  decode: raw => raw,
  encode: value => value
})

/** Oturum kimliğinin gelmesi için beklenecek en uzun süre. */
const WAIT_MS = 3_000

/** YENİ bir oturum açılması için beklenecek süre -- kurmak okumaktan uzun. */
const OPEN_WAIT_MS = 12_000

/**
 * Oturum kimliğini BEKLEYEREK oku (``''`` = süre doldu).
 *
 * Ölçülen yarış: köprü ana pencerede kuruluyor ve değeri oradan yayınlıyor.
 * Kullanıcı Ctrl+Alt+V'ye ana pencere daha oturumunu açmadan basarsa çentik
 * ``''`` okuyup HEMEN hata veriyordu -- kullanıcı cümlesini söylüyor, cümle
 * çöpe gidiyor ve çentikte tek satırlık bir hata kalıyordu.
 *
 * Bekleme kısa: 3 saniye, ve kullanıcı zaten konuşuyor olacağı için bedeli
 * görünmüyor. Süre dolarsa çağıran gerçekten söyleyecek bir şey biliyor
 * demektir; sonsuza kadar beklemek mikrofonu açık bırakmak olurdu.
 *
 * Değer ZATEN varsa hiç beklenmiyor -- normal yol bu.
 */
export function waitForVoiceSession(timeoutMs: number = WAIT_MS): Promise<string> {
  const current = $voiceSessionId.get()

  if (current) {
    return Promise.resolve(current)
  }

  return new Promise<string>(resolve => {
    let done = false

    const finish = (value: string) => {
      if (done) {
        return
      }

      done = true
      unsubscribe()
      clearTimeout(timer)
      resolve(value)
    }

    const timer = setTimeout(() => finish($voiceSessionId.get()), timeoutMs)

    // ``listen`` DEGIL ``subscribe``: ikincisi mevcut degeri de hemen veriyor,
    // yani abonelik kurulurken gelen bir yazi kacmiyor.
    const unsubscribe = $voiceSessionId.subscribe(value => {
      if (value) {
        finish(value)
      }
    })
  })
}

/**
 * "Sesin gidecegi bir sohbet ACILSIN" istegi — PENCERELER ARASI.
 *
 * Olculen davranis: kullanici intro ekranindayken bas-konusa basiyor,
 * konusuyor, ve centik "No chat is open yet — open one in the main window"
 * diyor. Mesaj DOGRU: acik oturum gercekten yok. Yanlis olan davranis --
 * bas-konusun butun amaci once pencereye gidip sohbet acmadan konusabilmek.
 *
 * Oturumu ACAN taraf ana pencere (arka uc oturumunu o kuruyor), isteyen taraf
 * centik. Aradaki kanal, oturum kimliginin kendisiyle ayni yerden geciyor:
 * paylasilan atom. Deger bir SAYAC, cunku istenen sey bir durum degil bir
 * OLAY -- ust uste iki istek ayirt edilebilmeli.
 */
export const $voiceSessionWanted = sharedAtom<string>('fool.desktop.voice.sessionWanted', '', {
  decode: raw => raw,
  encode: value => value
})

/** Ana pencereden yeni bir oturum iste. */
export function requestVoiceSession(): void {
  $voiceSessionWanted.set(String(Date.now()))
}

/**
 * Oturum kimligini bekle; YOKSA once bir tane ISTE.
 *
 * Bekleme suresi acikca daha uzun: yeni bir arka uc oturumu kurmak, var olani
 * okumaktan uzun suruyor.
 */
export async function waitForVoiceSessionOrOpen(
  timeoutMs: number = WAIT_MS,
  openTimeoutMs: number = OPEN_WAIT_MS
): Promise<string> {
  const existing = await waitForVoiceSession(timeoutMs)

  if (existing) {
    return existing
  }

  requestVoiceSession()

  return waitForVoiceSession(openTimeoutMs)
}

/**
 * "Şunu GÖNDER" — çentikten ana pencereye.
 *
 * Neden çentik kendisi göndermiyor
 * --------------------------------
 * Gönderiyordu, ve ölçülen bedeli şuydu: çentik ağ geçidine DOĞRUDAN
 * ``prompt.submit`` atıyordu, yani composer'ın gönderim boru hattını
 * atlıyordu. O boru hattı gönderir göndermez ekrana İYİMSER bir kullanıcı
 * balonu koyuyor (``use-prompt-actions/submit.ts::optimisticId``). Çentikten
 * konuşunca o balon hiç çizilmiyordu: kullanıcı konuşuyor, mesaj gerçekten
 * gidiyor, ama ekranda HİÇBİR ŞEY olmuyor ve model düşünürken (ölçüldü: tek
 * turda 172,9 sn) uygulama tamamen ölü görünüyor.
 *
 * Kullanıcının bildirdiği: "dediklerim algılandığı anda söylediklerim sohbete
 * aktarılmıyor... uygulamanın tüm amacının işlevsiz olmasına sebep oluyor."
 *
 * Ve istediği: "çentik aynı akışın birebir aynısı, sadece atanan tuş ile
 * bas-konuş hâli olmalı."
 *
 * Bu yüzden çentik artık bir GİRDİ AYGITI: metni yazıyor, gönderimi ana
 * pencere yapıyor -- iyimser balonu, oturum hedeflemesi, araya girme mandalı
 * ve geri kalan her şeyle birlikte. Quick Entry penceresi aynı kararı çoktan
 * vermişti: "One submit pipeline, no bespoke RPC."
 *
 * Değer bir SAYAÇ taşıyor (``id``): aynı cümleyi iki kez söylemek ayırt
 * edilebilmeli, yoksa ikincisi "değişmedi" sayılıp yutulurdu.
 */
export interface VoiceSubmitRequest {
  id: string
  text: string
  /** Model sözünü kesti mi? Ana pencere bunu tura iliştiriyor. */
  interrupted?: boolean
}

export const $voiceSubmitWanted = sharedAtom<string>('fool.desktop.voice.submitWanted', '', {
  decode: raw => raw,
  encode: value => value
})

/** Ana pencereden bu metni GÖNDERMESİNİ iste. */
export function requestVoiceSubmit(text: string, interrupted?: boolean): void {
  const payload: VoiceSubmitRequest = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    text,
    ...(interrupted ? { interrupted } : {})
  }

  $voiceSubmitWanted.set(JSON.stringify(payload))
}

/** İsteği çöz. Bozuk değer ``null`` -- yarım bir yazı gönderim tetiklememeli. */
export function parseVoiceSubmit(raw: unknown): null | VoiceSubmitRequest {
  if (typeof raw !== 'string' || !raw.trim()) {
    return null
  }

  try {
    const parsed = JSON.parse(raw) as VoiceSubmitRequest

    return parsed && typeof parsed.id === 'string' && typeof parsed.text === 'string' && parsed.text.trim()
      ? parsed
      : null
  } catch {
    return null
  }
}

/**
 * Uyandırma turu SÜRÜYOR mu — PENCERELER ARASI.
 *
 * Ölçülen hata
 * ------------
 * Uyandırma sözcüğü bir kez çalışıyor, sonra ölüyordu. Kullanıcının bildirdiği
 * birebir: "ilk hey hermesten sonra notch açıkken bir daha hey hermes demem
 * bir işe yaramıyor" ve "wake word dinlemesi açılıp kapanana ya da notch
 * açılıp kapanana kadar tekrardan wake word çalışmıyor."
 *
 * Sebep tek bir cümlede: SAPTAMA dinleyiciyi DURAKLATIYOR ve saptamayı tüketen
 * yüzey geri açmayı BORÇLANIYOR. Sunucu ``wake.detected``i yayınlamadan hemen
 * önce ``pause_listening`` çağırıyor (``tui_gateway/server.py::_on_detect``);
 * kendi geri açması yalnızca SUNUCU tarafındaki ses döngüsünün geri
 * çağrılarında (``_on_transcript`` / ``_on_silent`` / ``_on_status`` idle).
 * Masaüstü yakalamayı tarayıcı tarafında yapıyor, o döngü hiç koşmuyor.
 *
 * Composer'ın konuşma kipi borcu ödüyordu (``use-composer-voice``
 * ``resumeWakeIfPaused`` → ``resumeWakeAfterVoice``). Uyandırmayı çentiğe
 * yönlendirince o yol devre dışı kaldı ve borcu ödeyen kimse kalmadı.
 *
 * Neden bir ATOM, neden doğrudan çentikten geri açmıyoruz
 * ------------------------------------------------------
 * Kira ANA PENCEREDE: ``resumeWakeAfterVoice`` ``surface: 'gui'`` ile
 * uzlaştırıyor. Çentik AYRI bir ``BrowserWindow`` ve kendi isteğini atarsa
 * kirayı başka bir taşıyıcıya devretmiş olurdu -- dinleyici ana pencerenin
 * elinden çıkardı. Yani turu ÇENTİK biliyor, geri açmayı ANA PENCERE yapmalı;
 * arada bu atom var.
 *
 * Uyandırma turuna ÖZEL, her tura değil: bas-konuş dinleyiciyi hiç
 * duraklatmıyor, orada ödenecek bir borç yok.
 */
export const $wakeTurnActive = sharedAtom<string>('fool.desktop.voice.wakeTurn', '', {
  decode: raw => raw,
  encode: value => value
})

/** Uyandırma turunun sürüp sürmediğini yaz. */
export function setWakeTurnActive(active: boolean): void {
  $wakeTurnActive.set(active ? '1' : '')
}

/** Atomun ham değerinden tur durumu. */
export function wakeTurnIsActive(raw: unknown): boolean {
  return raw === '1'
}

/**
 * Çentiğin ses oturumu AÇIK mı — PENCERELER ARASI.
 *
 * Neden bir yarışı önceliğe çeviriyoruz
 * -------------------------------------
 * Cevabı kimin seslendireceği hakemle çözülüyor ve hakem doğru çalışıyor --
 * ama KİMİN ÖNCE talep ettiği bir yarıştı. İki sonucu vardı:
 *
 *   * Besteci kazandığında çentik akış açmıyor, yani cümle ilerleyişini hiç
 *     duymuyor ve ALT YAZI çıkmıyordu. Kullanıcının istediği "modelin
 *     söyledikleri eş zamanlı, alt yazı geçer gibi" tam da o sinyale bağlı.
 *   * Yarışın sonucu tura göre değişiyordu, yani davranış öngörülemezdi.
 *
 * Çentik AÇIKKEN sesin sahibi çentiktir: kullanıcı zaten ona bakıyor ve sesli
 * yüzey o. Bunu yazılı bir öncelik yapmak, hakemi de gereksiz bir yarıştan
 * kurtarıyor.
 */
export const $notchVoiceActive = sharedAtom<string>('fool.desktop.voice.notchActive', '', {
  decode: raw => raw,
  encode: value => value
})

/** Çentik oturumunun açık olup olmadığını yaz. */
export function setNotchVoiceActive(active: boolean): void {
  $notchVoiceActive.set(active ? '1' : '')
}

/** Çentik oturumu açık mı. */
export function notchVoiceIsActive(): boolean {
  return $notchVoiceActive.get() === '1'
}

/**
 * KONUŞULAN alt yazı — PENCERELER ARASI.
 *
 * Ölçülen hata
 * ------------
 * Çentik hem konuşuyor hem gösteriyordu ve ikisini de KENDİ ``$messages``inden
 * karar vererek yapıyordu. Ama ``$messages`` düz bir ``atom``, yani PENCERE
 * BAŞINA: çentik ayrı bir ``BrowserWindow`` ve listesi ana pencerenin bir tur
 * gerisinde kalıyor.
 *
 * Sonucu kullanıcının ekran görüntüsünde: şeritte BİR ÖNCEKİ cevap yazıyor ve
 * son cevap hiç seslendirilmiyor. Günlükte de doğrulandı -- bütün oturumda tek
 * bir sentez vardı, o da uyandırma onayı.
 *
 * Karar, ``$voiceSubmitWanted`` başlığındakiyle aynı: çentik bir GİRDİ
 * AYGITI. Gönderimi ana pencere yapıyordu; artık SESLENDİRMEYİ de o yapıyor.
 * Çentik yalnızca gösteriyor -- konuşulan metni buradan okuyarak.
 *
 * Böylece "kim konuşacak" sorusu tamamen ortadan kalkıyor: tek konuşan var.
 */
export const $spokenSubtitle = sharedAtom<string>('fool.desktop.voice.subtitle', '', {
  decode: raw => raw,
  encode: value => value
})

/** Konuşulan alt yazıyı yaz (boş dize = şerit temizlensin). */
export function setSpokenSubtitle(text: string): void {
  $spokenSubtitle.set(text)
}

/**
 * Ana penceredeki tur SÜRÜYOR mu — PENCERELER ARASI.
 *
 * Ölçülen hata
 * ------------
 * Seslendirme çentikten alınıp ana pencereye verildiğinde, çentiğin durum
 * makinesindeki ``speaking`` geçişi de onunla birlikte gitti. Ama ``idle``a
 * dönüş hâlâ onu bekliyordu::
 *
 *     if (statusRef.current === 'speaking') { setStatus('idle') }
 *
 * Sonuç: çentik ``thinking``de sonsuza kadar takılı kalıyor. Kullanıcının
 * bildirdiği "notch takılı kaldı cevap gelmesine rağmen" birebir bu.
 *
 * Çentik turun bittiğini kendi başına bilemez: ``$messages`` ve ``$busy`` düz
 * atomlar, yani pencere başına ve çentiğinki güvenilir değil -- zaten
 * seslendirmenin oradan alınma sebebi de buydu. Turu BİLEN taraf ana pencere,
 * o yüzden bildiren de o.
 */
export const $mainTurnBusy = sharedAtom<string>('fool.desktop.voice.turnBusy', '', {
  decode: raw => raw,
  encode: value => value
})

/** Ana penceredeki turun sürüp sürmediğini yaz. */
export function setMainTurnBusy(busy: boolean): void {
  $mainTurnBusy.set(busy ? '1' : '')
}
