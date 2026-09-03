/**
 * Ses modeli uçlarına HTTP istemcisi.
 *
 * Neden RPC değil de HTTP
 * -----------------------
 * Masaüstünün geri kalanı ağ geçidiyle WebSocket RPC üzerinden konuşuyor.
 * Kurulum işi buna uymuyor: dakikalarca sürüyor ve panel bu sırada kapanıp
 * açılabiliyor. Durum sunucuda bir iş nesnesinde durduğu için basit bir HTTP
 * yoklaması, paneli yeniden açan kullanıcıya süren kurulumu olduğu gibi
 * gösterir — soket kopsa bile ilerleme kaybolmaz.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { getApiRequestProfile } from '@/hermes'

export interface VoiceJob {
  detail: string
  device: 'cpu' | 'cuda'
  elapsed: number
  entry_id: string
  error: string
  id: string
  percent: number
  stage: string
  state: 'running' | 'done' | 'failed' | 'cancelled'
}

/**
 * Motora ozel, ayarlanabilir tek bir sayi.
 *
 * Bildirilen: "ayarlardan ses modellerinin exaggeration gibi ayarlarini
 * yapamiyoruz." Degerler yapilandirmada duruyordu ve motor onlari okuyordu;
 * eksik olan YALNIZCA arayuz yoluydu.
 */
export interface VoiceKnob {
  id: string
  label: string
  min: number
  max: number
  step: number
  default: number
  /** Sayinin kendisi hicbir sey anlatmiyor; NE YAPTIGI. */
  help: string
  /** Motorun SU AN kullandigi deger (ayarli degilse varsayilan). */
  value: number
}

export interface VoiceItem {
  /** Su an SECILI olan saglayici mi? */
  active: boolean
  /** Calisma aygiti: auto | cpu | cuda. */
  device: 'auto' | 'cpu' | 'cuda'
  /** Secili ses kimligi. */
  voice: string
  /** Bu motorun secilebilir sesleri. */
  voices: { id: string; label: string }[]
  /** Bu motorun ayarlanabilir sayilari (bos = yok). */
  knobs: VoiceKnob[]
  /** Motor GERCEKTEN CUDA calistirabiliyor mu? Yapilandirmada "cuda"
   *  yazmasindan AYRI: calisma zamani eksikse sessizce CPU'ya duser. */
  cuda_ready: boolean
  /** Buyuk model + CPU = dakikalarca bekleme. Bos = uyari yok. */
  cpu_warning: string
  /** Bu motor ses klonlamayi destekliyor mu? */
  clone_capable: boolean
  /** Secili klon dosyasinin adi ("" = kapali). */
  clone: string
  /** Bu motora ozel klonlama aciklamasi (bos = klonlama yok). */
  clone_help: string
  assets_installed: boolean
  /**
   * Paket yerinde ama motor ICE AKTARILAMIYOR -- sebebi ve caresi.
   *
   * ``installed`` bunun icin false YAPILMIYOR: yeniden kurmak duzeltmiyor,
   * o yuzden panelde "Install" degil SEBEP gosterilmeli. Olculdu: f5-tts bu
   * makinede kurulu gorunuyor, ``import torchcodec`` paylasilan FFmpeg
   * DLL'lerini bulamadigi icin dusuyor ve kullanici klon yukleyip hicbir sey
   * duymuyordu.
   */
  engine_error: string
  /** Kurulu VE gercekten calisiyor. Klonlama ve otomatik secim buna bakiyor. */
  usable: boolean
  cuda_available: boolean
  devices: ('cpu' | 'cuda')[]
  engine_installed: boolean
  id: string
  installed: boolean
  job: VoiceJob | null
  kind: 'tts' | 'stt'
  /** ``tts.provider`` yapilandirmasina YAZILAN ad -- katalog kimliginden
   *  AYRI (``qwen3-tts`` indirilir, ``qwen3`` secilir). Sunucu bu alani
   *  zaten gonderiyordu; arayuzde tanimli degildi. */
  provider_id: string
  label: string
  recommended: boolean
  size_label: string
  summary: string
}

export interface VoiceClone {
  bytes: number
  id: string
  label: string
  path: string
}

/**
 * Konusma dili AYARSIZKEN yabanci dil seslendirildi.
 *
 * Tek dilli bir motor Turkceyi Ingilizce fonetigiyle okuyor (``Merhaba`` ->
 * ``Mehabal``): ses cikiyor, hata yok, kullanici yalnizca bozuk telaffuz
 * duyuyor. Ilk kurulumda SORULMUYOR -- uyari sorun gercekten ortaya ciktigi
 * anda beliriyor.
 */
export interface SpeechLanguageHint {
  /** Gozlenen isaretin adi (``turkish``, ``cyrillic``, ...) -- dil TAHMINI degil. */
  signal: string
  message: string
}

/** Secili motor OLCULMUS olarak yavassa gosterilecek ipucu. */
export interface SlowEngineHint {
  alternative: string
  alternative_ms: number
  message: string
  selected: string
  selected_ms: number
}

export interface VoiceCatalog {
  active: { stt: string; tts: string }
  cuda_available: boolean
  items: VoiceItem[]
  /** ``null`` = secili motor yeterince hizli ya da hic olculmemis. */
  slow_engine?: null | SlowEngineHint
  /** ``null`` = konusma dili ayarli, uyari kapatilmis ya da hic gerekmedi. */
  speech_language_hint?: null | SpeechLanguageHint
  voice_dir: string
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  // Masaustu KOPRUSU uzerinden -- ham ``fetch`` DEGIL.
  //
  // Ilk yazimda ``fetch(conn.baseUrl + path)`` kullanildi ve panel her zaman
  // bos geldi: istek sessizce basarisiz oluyordu (koken/kimlik dogrulama
  // renderer'dan cozulemiyor). Uygulamanin geri kalani zaten bu koprudan
  // geciyor; ayri bir yol acmak, calisan tek yolu atlamak demekti.
  const desktop = window.foolDesktop

  if (!desktop?.api) {
    // Metin KULLANICIYA gorunuyor: ``voice-settings.tsx`` yakaladigi hatanin
    // mesajini oldugu gibi gosteriyor. Kaynak yorumlari Turkce (bilerek), ama
    // urunun icindeki metin uygulamanin diliyle olmali.
    throw new Error('Desktop bridge unavailable — voice settings need the desktop app')
  }

  // AKTIF PROFILE gidiyor.
  //
  // Olculen hata: bu cagrilar profil kapsami TASIMIYORDU, yani butun ses
  // ayarlari paneli her zaman BIRINCIL arka uca yaziyordu -- oysa oynatma ve
  // yaziya dokme ``profileScoped()`` kullaniyor ve AKTIF profile gidiyor.
  //
  // Iki yuzey iki ayri arka uca bakinca panel yalan soyluyor: kullanici
  // ``persona`` profili acikken motoru "Chatterbox" secmis gorunuyor
  // (birincil profilin config'i oyle), ama konusma o profilin kendi
  // config'inden okunuyor ve orada hala ``kokoro`` yaziyor. Ekranda cikan
  // hata da yanlis motoru sucluyor: "Kokoro kurulu degil" -- kullanicinin
  // hicbir zaman secmedigi motor.
  //
  // Ayni sey kurulan motorlar, aygit secimi ve YUKLENEN KLONLAR icin de
  // gecerliydi: hepsi yanlis profile gidiyordu.
  const profile = getApiRequestProfile()

  return desktop.api<T>({
    ...(body === undefined ? {} : { body }),
    ...(profile ? { profile } : {}),
    method: body === undefined ? 'GET' : 'POST',
    path,
    // Kurulum baslatma cagrisi ag gecidinde is nesnesi yaratana kadar
    // bekliyor; varsayilan 15 sn kisa kalabiliyor.
    timeoutMs: 60_000
  })
}

export interface VoicePreview {
  ok: boolean
  provider: string
  entry_id: string
  /** Sentez GERCEKTEN ne kadar surdu. */
  elapsed_ms: number
  bytes: number
  mime: string
  audio_base64: string
}

/** ``/api/fool/voice/language`` cevabi. */
export interface LanguageSettings {
  /** Cevabin YAZILDIGI dil, ya da ``auto`` (kullanicinin diline uy). */
  reply_language: string
  /** SESLENDIRILEN dil, ya da ``same`` (cevabin dilinde konus). */
  speech_language: string
  languages?: { code: string; name: string }[]
}

export const voiceApi = {
  cancel: (jobId: string) => call<{ cancelled: boolean }>('/api/fool/voice/cancel', { job_id: jobId }),
  /** Cevap dili + konusma dili, ve secilebilir diller. */
  language: () => call<LanguageSettings>('/api/fool/voice/language'),
  /** Yalnizca DEGISENI gonder: iki alani birden gondermek, bir acilir listeyi
   *  degistirirken digerini sessizce sifirlardi. */
  setLanguage: (patch: { reply_language?: string; speech_language?: string }) =>
    call<{ ok: boolean } & LanguageSettings>('/api/fool/voice/language', patch),
  catalog: () => call<VoiceCatalog>('/api/fool/voice/catalog'),
  /** Konusma dili uyarisini KALICI olarak kapat. Oturum icinde tutmak, panel
   *  her acildiginda uyariyi geri getirir ve dugmeyi anlamsiz kilardi. */
  dismissSpeechLanguageHint: () =>
    call<{ ok: boolean }>('/api/fool/voice/speech-language-hint/dismiss', {}),
  install: (entryId: string, device: 'cpu' | 'cuda') =>
    call<VoiceJob>('/api/fool/voice/install', { device, entry_id: entryId }),
  job: (jobId: string) => call<VoiceJob>(`/api/fool/voice/job/${jobId}`),
  select: (entryId: string) => call<{ ok: boolean }>('/api/fool/voice/select', { entry_id: entryId }),
  setDevice: (entryId: string, device: 'auto' | 'cpu' | 'cuda') =>
    call<{ ok: boolean }>('/api/fool/voice/device', { device, entry_id: entryId }),
  setVoice: (entryId: string, voice: string) =>
    call<{ ok: boolean }>('/api/fool/voice/voice', { entry_id: entryId, voice }),
  setKnob: (entryId: string, knobId: string, value: number) =>
    call<{ ok: boolean; id: string; value: number }>('/api/fool/voice/knob', {
      entry_id: entryId,
      knob_id: knobId,
      value
    }),
  installCuda: (entryId: string) => call<VoiceJob>('/api/fool/voice/cuda', { entry_id: entryId }),
  /** Konusma tanima modelini arka planda yukle. Sesli oturum ACILDIGI anda
   *  cagriliyor: olculdu, isitmasiz ilk transkripsiyon 6,94 sn, isitilmis
   *  0,66 sn. O sure kullanicinin konusmakla gecirdigi zamana gizleniyor. */
  /** STT ve TTS modellerini arka planda yukle; HEMEN donuyor.
   *
   *  Adi eskiden ``warmStt``ti ve yalnizca tanimayi isitiyordu. Seslendirme
   *  disarida kalinca Friend penceresi ilk cumlede soguk yuklemeyi oduyordu
   *  (kokoro 24 sn, styletts2 67 sn) -- kullaniciya "dakikalarca model
   *  uyandiriliyor" olarak gorunen sey buydu. */
  warmVoice: () =>
    call<{ stt: { status: string }; tts: { status: string } }>('/api/fool/voice/warm', {}),
  /** Kip basina secili seslendirme saglayicilari. */
  /** Bir kipin sesini kaydet. Bos saglayici = genel ayara don. */
  /** Kisa bir cumle seslendir. ``elapsed_ms`` panelde gosteriliyor: motorun
   *  GERCEKTEN CUDA'da kosup kosmadiginin tek durust kaniti. */
  preview: (entryId: string) =>
    call<VoicePreview>('/api/fool/voice/preview', { entry_id: entryId }),
  clones: () => call<{ clones: VoiceClone[] }>('/api/fool/voice/clones'),
  uploadClone: (filename: string, dataBase64: string) =>
    call<{ id: string; label: string }>('/api/fool/voice/clones/upload', {
      data_base64: dataBase64,
      filename
    }),
  selectClone: (entryId: string, cloneId: string) =>
    call<{ ok: boolean }>('/api/fool/voice/clones/select', { clone_id: cloneId, entry_id: entryId }),
  deleteClone: (cloneId: string) =>
    call<{ ok: boolean }>('/api/fool/voice/clones/delete', { clone_id: cloneId })
}
