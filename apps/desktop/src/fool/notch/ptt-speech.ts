/**
 * Bas-konuşta GERÇEKTEN konuşuldu mu — saf, DOM'suz, sınanabilir.
 *
 * Neden gerekiyor
 * ---------------
 * Araya girme tuşa BASILDIĞI anda çalışıyordu: ``begin()`` daha mikrofon
 * açılmadan oynatmayı kesip turu durduruyordu. Yani sağ Ctrl'ye yanlışlıkla
 * dokunmak -- ya da ne diyeceğine karar vermeden basmak -- modelin cevabını
 * öldürüyordu ve geri dönüşü yoktu.
 *
 * Kullanıcının istediği kural birebir: tuşa basılması yetmez, o tuş basılıyken
 * GERÇEKTEN konuşulduğu anlaşıldığında kesilsin.
 *
 * Neden tek bir örnek yetmez
 * --------------------------
 * Klavyenin kendi tıkırtısı, bir öksürük, sandalyenin gıcırtısı -- hepsi tek
 * bir tikte eşiği geçebiliyor. Karar, eşiğin ÜSTÜNDE geçirilen süreye bakıyor.
 *
 * Neden oynatma sırasında eşik daha yüksek
 * ----------------------------------------
 * Model konuşurken mikrofon hoparlörü duyuyor. Yankı bastırma aynı
 * uygulamanın kendi oynatmasını Windows'ta güvenilir biçimde kesmiyor (aynı
 * gerekçe ``lib/voice-barge-in.ts``de de yazılı ve oradaki sayılarla aynı
 * ölçekteyiz). Sessiz eşiği oynatma sırasında kullanmak, modelin kendi sesini
 * "kullanıcı konuşuyor" sanmak olurdu.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

/** Sessiz ortamda konuşma sayılan seviye. Sesli döngünün ``silenceLevel``i. */
export const PTT_SPEECH_LEVEL = 0.075

/**
 * Oynatma sürerken konuşma sayılan seviye.
 *
 * ``lib/voice-barge-in.ts``deki ``PLAYBACK_MIN_TRIGGER_LEVEL`` ile aynı:
 * hoparlör sızıntısının tek başına tetikleyemeyeceği, ama konuşmanın rahatça
 * ulaştığı bir yer.
 */
export const PTT_SPEECH_LEVEL_PLAYING = 0.14

/** Eşiğin üstünde bu kadar süre kalınca konuşma sayılıyor. */
export const PTT_SPEECH_SUSTAIN_MS = 140

export interface PttSpeechState {
  /** Eşiğin üstüne ilk çıkılan an (``null`` = altındayız). */
  aboveSince: null | number
  /** Bu basış için karar VERİLDİ mi? Bir kez tetikleniyor. */
  fired: boolean
}

export const createPttSpeechState = (): PttSpeechState => ({ aboveSince: null, fired: false })

export interface LevelSample {
  level: number
  now: number
  /** Seslendirme şu an çalıyor mu? Eşiği bu belirliyor. */
  playing: boolean
}

/**
 * Bir seviye örneği işle.
 *
 * ``true`` = konuşma BAŞLADI (çağıran araya girmeyi şimdi uygulasın). Basış
 * başına yalnızca bir kez ``true`` döner.
 */
export function observeLevel(state: PttSpeechState, { level, now, playing }: LevelSample): boolean {
  if (state.fired) {
    return false
  }

  const threshold = playing ? PTT_SPEECH_LEVEL_PLAYING : PTT_SPEECH_LEVEL

  if (level < threshold) {
    state.aboveSince = null

    return false
  }

  state.aboveSince ??= now

  if (now - state.aboveSince < PTT_SPEECH_SUSTAIN_MS) {
    return false
  }

  state.fired = true

  return true
}
